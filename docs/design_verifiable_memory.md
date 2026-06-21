# Diseño rápido — Capa de memoria verificable (para planificar encima)

<!-- Doc interno de diseño (nombres internos OK). 2026-06-20. Borrador para iterar.
     Plan→DISEÑO; construir es la fase siguiente. Mientras arXiv tarda (días). -->

## Objetivo

Convertir el `LessonStore` actual (JSON + Merkle) en una **memoria rápida, consultable y
clasificada** SIN perder la **verificabilidad** — y montar encima las 4 capas-moat. El moat NO
es el storage (commodity); es procedencia verificable + abstracción + olvido + transferencia.

## Principio de arquitectura (no romper)

```
CORE (verificable)          Cadena Merkle = fuente de verdad de la procedencia (append-only)
   │
ÍNDICE (rápido/consultable) SQLite + FTS5 + sqlite-vec = vista materializada para recall
   │
PLUGINS (intercambiables)   Embedder, mutador, maestro, Garak/PyRIT
```
Regla: si borras un plugin, el CORE sigue. SQLite es **índice derivado**, reconstruible desde la
cadena; la cadena nunca se "edita". "Olvidar" = dejar de surfacing en el índice, NO borrar del log.

## Modelo de datos (esquema SQLite — borrador)

```sql
-- Lección (deriva de un evento; enlaza a su hoja Merkle = procedencia verificable)
lessons(
  id TEXT PRIMARY KEY,
  merkle_leaf_index INTEGER,      -- enlace al CORE (procedencia)
  merkle_leaf_hash  TEXT,
  source_event_ref  TEXT,         -- de qué ataque/entrada de log salió (lineage)
  pattern_id        TEXT,         -- abstracción (FK -> patterns); NULL si aún sin abstraer
  avoid_text        TEXT,         -- ejemplo crudo (lo que vimos)
  stance            TEXT,         -- avoid|allow
  status            TEXT,         -- active|superseded|retired   (olvido)
  created_at_ns     INTEGER,
  evidence_verdict  TEXT          -- pass (ley de entrada)
)
-- Patrón abstracto (la UNIDAD de aprendizaje real, no el ejemplo)
patterns(
  id TEXT PRIMARY KEY,
  label       TEXT,               -- "instruction-hierarchy reassignment", "role-reframing"...
  family      TEXT,               -- familia de ataque (para held-out en transferencia)
  centroid    BLOB,               -- embedding representativo
  n_examples  INTEGER,
  created_at_ns INTEGER
)
-- Aristas de lineage/relación (grafo en tablas; sin Neo4j)
edges(src TEXT, dst TEXT, kind TEXT)   -- kind: derived_from | generalizes | supersedes | variant_of
-- Índices: FTS5 sobre avoid_text/label ; sqlite-vec sobre embeddings (centroid / por lección)
```

Marida CORE+índice: al `add()` de una lección → (1) se ancla en Merkle (ya existe), (2) se inserta
fila en SQLite con `merkle_leaf_*`. Verificación: cualquier fila se puede probar contra la cadena.

## Las 4 capas-moat (mapeadas a componentes)

1. **Procedencia + lineage verificable** — `merkle_leaf_*` + `edges(derived_from)`. Permite
   responder "qué aprendí, cuándo, de qué ataque, y pruébalo". Nadie en el campo lo tiene.
2. **Abstracción (patrones, no ejemplos)** — `patterns` + clustering/teacher que asigna `pattern_id`.
   El recall opera sobre **patrones** (centroid), no sobre el string crudo. Componente:
   `PatternAbstractor` (plugin: embeddings + clustering, o maestro que etiqueta la clase).
3. **Olvido principiado / curación** — `status` (active/superseded/retired) + política de poda:
   dedup, supersede (un patrón mejor reemplaza a otro), decaimiento por desuso. La cadena guarda
   el histórico inmutable; el índice solo surfacea lo `active`. Componente: `Curator`.
4. **Transferencia medida** — extiende `generalization_curve` con held-out por `family`.

## Experimento de transferencia (la prueba decisiva)

```
1. Taxonomía: agrupa ataques (Garak) en FAMILIAS (dan, encoding, latentinjection, promptinject…).
2. Split: entrena (siembra patrones) con familias A,B  →  HELD-OUT familias C,D (nunca vistas).
3. Abstrae: las semillas se guardan como PATRONES (clase), no como ejemplos.
4. Mide sobre C,D:
   - recall (¿reconoce variantes de familias nunca sembradas?)  -> TRANSFERENCIA real
   - control de FP sobre tráfico benigno (mismo umbral)
   - curva recall vs distancia + punto de ruptura
   - todo anclado en cadena (procedencia de cada lección/patrón)
5. Criterio:
   ÉXITO  -> recall alto en C,D con FP bajo = generaliza = "genera conocimiento"
   FRACASO -> recall colapsa en C,D = solo memoriza = "enciclopedia" (y se dice)
```
Honesto: con embedder real (HF) ya validamos near-duplicate; esto sube el listón a **familias
nunca vistas**, que es lo difícil. Esperar caída con la distancia es normal; lo que importa es
si hay señal NO trivial en held-out con FP controlado.

## ARQUITECTURA: MOTOR genérico vs INQUILINO (decidido 2026-06-21)

No son lo mismo: hay UN motor agnóstico de dominio y N inquilinos tipados encima.
- **MOTOR (sustrato verificable, MemPalace):** `record.py` (`MemoryRecord`/`GenericRecord`),
  `memory_index.py` (`SqliteMemoryIndex`), `memory_abstractor.py` (`MemoryAbstractor`). Solo sabe
  de `record_id` + `text` + `created_at` (+ `record_type` para 1d). NO conoce lecciones, stances ni
  Garak. Probado en dominio no-seguridad (`tests/test_memory_motor.py`).
- **INQUILINO ciberseguridad (memoria inmune):** `lesson_index.py` (`SqliteLessonIndex`) y
  `pattern_abstractor.py` (`PatternAbstractor`) — vistas delgadas que adaptan `Lesson`→`MemoryRecord`
  vía `lesson_to_record` y delegan en el motor. API histórica intacta (60 tests del inquilino verdes
  sin tocarlos). Garak SOLO importa aquí (mide este inquilino), no es identidad del motor.
Regla: el motor nunca importa nada de seguridad; los inquilinos componen el motor, no al revés.
Taxonomía (analytic/empirical/episodic) vive en el motor (`record_type`); las lecciones son `empirical`.

## CHECKLIST DE CONSTRUCCIÓN (fuente única de verdad — marcar al cerrar cada una)

Orden lógico, una a una, valor>coste o no entra. Cada fase: TDD, suite verde, mypy strict,
límites honestos declarados. No saltar de fase con la anterior en rojo.

- [x] **1a — Índice SQLite persistente con enlace Merkle.** *(HECHO 2026-06-21; suite 2008 verde,
  mypy strict limpio; sin commit aún.)* `src/atlas/memory/lesson_index.py` (`SqliteLessonIndex`) +
  `tests/test_sqlite_lesson_index.py` (11 tests). `sqlite3` de stdlib, vectores como BLOB float64,
  coseno REUTILIZANDO `_cosine_similarity` de `lesson_recaller` → **paridad de scores exacta**
  (testeada vs in-memory). Persiste (sobrevive reabrir), reconstruible vía `rebuild_from(store)`,
  columnas `merkle_leaf_hash/_index` (nullable; cimiento moat-1, se pueblan vía `upsert`).
  CABLEADO (2026-06-21, suite 2013 verde): protocolo `Recaller` (`index()`+`recall()`) en
  `lesson_recaller.py`; `SqliteLessonIndex` lo cumple (acepta `store=`, `index()`=`rebuild_from`);
  `TeacherDebate` ahora tipa `Recaller` → el índice persistente es drop-in del in-memory, probado
  end-to-end (corrobora prior + acepta novel sobre SQLite).
  LÍMITE HONESTO: NO `sqlite-vec` (regla 6; velocidad no es el cuello a escala laptop). El loop
  inmune (`TeacherDebate`/`GatedLessonRecorder`) SIGUE sin ensamblarse en producción (solo en
  tests) — eso es independiente de 1a y es un pendiente de "enjambre ocioso", no de la memoria.
  Siguiente: 1b (`PatternAbstractor`), donde empieza la transferencia real.
- [x] **1b — `PatternAbstractor`** *(HECHO 2026-06-21; suite 2024 verde, mypy strict; sin commit.)*
  `src/atlas/memory/pattern_abstractor.py` + `tests/test_pattern_abstractor.py` (11 tests).
  Clustering DETERMINISTA por umbral de coseno (greedy aglomerativo 1 pasada, sin deps); recall
  sobre el CENTROIDE del patrón (no el string); ids direccionados por contenido (hash de miembros);
  label = ejemplo más cercano al centroide (representante auditable); `assignment()` da el lineage
  lesson→pattern. Reutiliza `_cosine_similarity` (misma noción de similitud en todo el subsistema).
  LÍMITE HONESTO: clustering de 1 pasada depende de orden+umbral; agrupa reformulaciones/vecinos,
  NO descubre la estructura "real" de familias ni prueba transferencia. `family` queda como campo
  vacío para 1c. Maestro LLM como etiquetador = mejora futura, no entró. **La prueba de si esto
  GENERALIZA es 1c (held-out), no este módulo.**
- [x] **REFACTOR motor/inquilino** *(HECHO 2026-06-21; suite 2029 verde, mypy strict; sin commit.)*
  Extraído el motor genérico (`record.py`+`memory_index.py`+`memory_abstractor.py`); seguridad pasa a
  inquilino delgado. `tests/test_memory_motor.py` (5 tests) demuestra agnosticidad en dominio
  no-seguridad (recetas). 60 tests del inquilino intactos = refactor behavior-preserving.
- [x] **1c-seguridad — CERRADA 2026-06-21** (ver detalle abajo). **1c-motor CERRADA.**
- [x] **1c — DOS ejes (separados 2026-06-21; ambos cerrados):**
  - **1c-seguridad** *(HECHO 2026-06-21, primer corte; `scripts/redteam/transfer_experiment.py`
    + `docs/immune_transfer_experiment.md`):* held-out por familia (train: instruction_override,
    persona_jailbreak; held-out: exfiltration, encoding_evasion), anclado en Merkle. RESULTADO
    HONESTO: léxico = MEMORIZA (0% transferencia, vocabulario disjunto). Semántico (MiniLM,
    umbral calibrado 0.60 con sanidad 100%) = transferencia PARCIAL REAL: **heldout_recall 33%
    con benign_fp 0%** → no es enciclopedia pura ni generalización resuelta. CONFOUNDS declarados:
    umbral clustering==recall (techo optimista), semillas ilustrativas (no Garak real aún),
    conjuntos pequeños.
    PULIDO 2026-06-21 (a): confound clustering==recall RESUELTO (umbrales separados en
    `MemoryAbstractor`, testeado).
    PULIDO 2026-06-21 (b) — TEST BENIGNO FRONTERIZO, hallazgo que CORRIGE el corte anterior:
    el "transfer con 0% FP" era artefacto de un benigno FÁCIL. Con benigno fronterizo (legítimo
    que roza el tema), el FP sube en paralelo al heldout (recall 0.60: heldout 50% / borderline
    33%; recall 0.62: heldout 17% < borderline 33%, margen NEGATIVO). VEREDICTO HONESTO: el
    detector reconoce PROXIMIDAD TEMÁTICA, no "ataque-idad"; señal de intención REAL pero DÉBIL
    (~17-33 pts de margen en umbrales laxos); NO hay punto de operación usable (transferencia alta
    Y FP fronterizo bajo no coexisten). Refuerza la dirección: no apostar a DETECCIÓN, sino a
    ATRIBUCIÓN+CONTENCIÓN ([[adaptive-defense-reframe]]).
    GARAK REAL 2026-06-21 (c) — CIERRE: corpus real (probes promptinject.HijackHateHumans +
    phrasing.PastTense train; web_injection.MarkdownURIImageExfil + snowball.Primes held-out)
    CONFIRMA el hallazgo, más crudo: mejor margen heldout−borderline = +10 pts (recall 0.65:
    27% heldout / 17% borderline); resto ~0 o negativo. Sanidad 100% siempre (near-duplicates
    fiables). Veredicto firme: coseno-a-centroide reconoce PROXIMIDAD TEMÁTICA, no intención; el
    valor real = reconocimiento auditable de variantes, NO detección de familias nuevas. 1c-seguridad
    CERRADA. Futuro NO prometido para subir señal: contrastive intención-vs-tema + drift+contenido + IC.
  - [x] **1c-motor — CERRADA 2026-06-21** (suite 2048 verde): `tests/test_motor_versioned_knowledge.py`
    (2) demuestra el valor genérico en dominio NO-seguridad (hechos de empresa que cambian): recall
    refleja la verdad VIGENTE tras supersesión, la historia es recuperable y PROBABLE en cadena
    (qué cambió y cuándo). El eje genérico no es detección (frontera dura) sino conocimiento
    versionado con procedencia — donde el sustrato gana limpio. Transferencia/abstracción genérica
    ya cubierta por `test_memory_motor.py`. **CHECKLIST 1a–1d COMPLETA.**
- [x] **1d — olvido principiado SOLO sobre el índice; la cadena Merkle nunca borra (a+b+tipo-1).**
  - [x] **1d-a — Validez temporal + supersesión + retiro auditables** *(HECHO 2026-06-21; suite
    2039 verde, mypy strict)* en `SqliteMemoryIndex` (motor genérico) + `tests/test_memory_temporal.py`
    (7 tests). Columnas `valid_from_ns`/`valid_until_ns` (NULL=vigente) + `supersedes` (lineage);
    migración suave para esquemas previos. `recall`/`recall_all` solo surfacean VIGENTES por defecto
    (`include_superseded=` para auditar). `supersede(old→new)` caduca la vieja (NO la borra) y entra
    la nueva con lineage; `retire(id)` = olvido sin reemplazo. Cada transición se ancla en Merkle
    (`memory.superseded`/`memory.retired`) si se pasa logger → se PRUEBA qué era vigente y cuándo
    caducó. Ataca staleness #1 + contradicciones (lo que el campo admite no resolver).
    LÍMITE: resolución de conflictos por reglas de autoridad (fuente/recencia/evidencia) aún manual
    (quien llama decide supersede); el motor registra, no arbitra. Tenant (SqliteLessonIndex) aún no
    expone supersede/retire (delega recall); cablear si se necesita.
  - [x] **1d-b — Tiers (hot/warm/cold/pending) + democión medible** *(HECHO 2026-06-21; suite 2046
    verde, mypy strict)* en `SqliteMemoryIndex` + `tests/test_memory_tiers.py` (7). Columnas `tier`,
    `last_access_ns`, `access_count`. `touch(id)` = acceso → promociona a hot (RECUPERABLE) + cuenta
    uso. `apply_decay(now, warm/cold/pending_after_ns)` demota memorias VIGENTES por ocio (now −
    último acceso) en buckets ascendentes, reproducible, logueado en Merkle (`memory.decay`).
    `pending` = SUELO/grace: NO auto-retira (el retiro sigue siendo decisión aparte, 1d-a). Solo
    afecta a vigentes. `tier_counts()`/`tier()`/`access_count()`.
    LÍMITE: los umbrales de ocio son POLÍTICA (parámetros), no aprendidos; "medible" = por
    recencia/uso, no arbitrario.
  - [x] **Deudas tipo-1 CERRADAS 2026-06-21** *(suite 2059 verde, mypy strict;
    `tests/test_memory_lifecycle.py` 6 tests)*: (1) `apply_decay(retire_after_ns=...)` retira tras el
    grace (pending→retire explícito, auditado; la cadena nunca borra); (2) `auto_touch=True` +
    `now_ns` opcional en recall → el uso real revive memorias sin tocar manual; (3) el tenant
    `SqliteLessonIndex` expone supersede/retire/touch/apply_decay/tier(_counts)/active_count. Test de
    CICLO DE VIDA completo (acceso→pending→revive→grace→retire) anclado en cadena. Quedan solo el
    tipo-3 (muro intención-vs-tema) y multihilo (sin consumidor aún).

Notas de estado se anotan inline al cerrar cada casilla (fecha + commit + límite honesto).

## PRINCIPIO DE PRIORIZACIÓN (registrado 2026-06-21 — la lógica que ordena las fases)

No todo "pendiente" es igual; el orden de ataque se deriva de su NATURALEZA
(ver `feedback-debt-closure-workflow`):
- **Tipo-2 (fundacional/correctitud) PRIMERO** — si apilas encima, la corrupción se hereda
  (p.ej. auditoría pre-merge). No diferir.
- **Tipo-1 (construir-encima) por dependencia** — independientes en paralelo; lo que depende, después.
- **Tipo-3 (muro/límite real) aparte** — se rodea o se acepta; no es "tarea que se termina".
Regla de registro: ninguna priorización vive solo en la conversación; se escribe aquí (fuente única).

**Mapa de fases:**
- **FASE 1 — Sustrato verificable (1a–1d): COMPLETA** (núcleo + ciclo de vida + auditoría).
- **MURO 1c — intención-vs-tema:** tipo-3. ATACADO 2026-06-21 (`docs/immune_intent_vs_topic_contrastive.md`
  + `tests/test_contrastive_margin.py`): contrastive por prototipos (margen sim_ataque−sim_benigno)
  **duplica/triplica la separación** (gap heldout−borderline +17→+25..57) → el muro se MOVIÓ, no cayó:
  borderline_fp se queda ~33%, no es detector usable a FP bajo. Disciplina: un 0% de FP a margin 0.05
  con n=5 era SUERTE de muestra; con n=15 → ~33%. Confirma: separación parcial medible, no clasificador
  de intención; el eje ganador sigue siendo atribución+contención.
- **FASE 2 — Huecos abiertos del campo de memoria ("la otra checklist"):** ver abajo.

## FASE 2 — Huecos abiertos (la otra checklist; de `project-osmosis-future-roadmap`)

Huecos que el campo de memoria (Mem0/Zep/Letta/MemPalace) admite no resolver. Orden propuesto
por valor×naturaleza (no es ley; ver `feedback-roadmap-is-guide-not-law`).

- [ ] **2.1 — Multi-hop** (encadenar N memorias para responder; lo que el usuario recordó). Tipo-1.
- [ ] **2.2 — PII / crypto-shredding** (olvido REAL del contenido: borrar clave → dato cifrado
  irrecuperable, sin romper Merkle). Tipo-1/2 FUNDACIONAL + **GAP-1 crítico EU AI Act**. Encaja con
  `retire` ya existente (hoy olvida del índice; esto olvida el contenido).
- [ ] **2.3 — Evaluación honesta** (benchmark anti-trampa; ya DISEÑADA en hilo-B, falta construir). Tipo-1.
- [ ] **2.4 — Envenenamiento de memoria** (extender el write-gating `LessonVerifier` al motor genérico).
  Tipo-1; PARCIAL (existe en el tenant de seguridad).
- [ ] **2.5 — Fuga entre usuarios / tenancy** (namespacing). Tipo-1.
- [ ] **2.6 — Personalización vs contaminación.** Tipo-3-ish (política/límite).
- [x] **2.7 — Cold-start.** Tipo-3 epistémico — RESUELTO conceptualmente (procedencia bootstrap ≠
  verdad; arrancar en dominio de muro bajo). No requiere código; ver memoria.

## Adiciones tras inteligencia competitiva (2026-06-20) — atacar los huecos abiertos del campo

El campo (MemGPT/Letta, Zep, Mem0, MemPalace) ADMITE no resolver: (1) **staleness/validez
temporal** (el #1), (2) **contradicciones**, (3) **consolidación/qué conservar**, (4) provenance
parcial, (5) seguridad/write-gating. Nuestro sustrato verificable los ataca con tres piezas:

### A) Validez temporal auditable + supersesión (ataca staleness #1 y contradicciones)
- `lessons` añade: `valid_from_ns`, `valid_until_ns` (NULL = vigente AHORA), y arista
  `edges(kind='supersedes')` cuando una lección/patrón reemplaza a otro.
- Recall por defecto solo surfacea lo **vigente** (`valid_until_ns IS NULL`).
- Cuando llega info que contradice un prior: NO se borra — se crea la nueva, se marca la vieja
  con `valid_until_ns = now` y `supersedes`, **con registro en la cadena** (cuándo y por qué dejó
  de valer). → Se puede **PROBAR qué memoria es vigente y cuándo caducó.** Eso es lo que nadie tiene.
- Conflictos: reglas de autoridad explícitas (fuente, recencia, evidencia) → la resolución queda
  **auditable** en la cadena, no es una caja negra.

### B) Niveles de memoria (hot/warm/cold/pending) con promoción/democión (ataca consolidación/olvido)
- `lessons.tier` ∈ {hot, warm, cold, pending} + `last_access_ns`, `access_count`.
- Democión por señales MEDIBLES (poco uso/recencia) → auditable, no juicio arbitrario.
- **Recuperable:** si algo en cold/pending se vuelve a necesitar, sube de nivel.
- `pending` = grace period antes de retirar del ÍNDICE; **la cadena Merkle nunca borra** → "olvidar"
  = no surfacear, nunca perder. Resuelve "¿quién audita el olvido?": las transiciones de tier se
  registran y son reversibles.
- (Estructura inspirada en MemGPT/cache hierarchy; la novedad = suelo verificable + democión auditable.)

### C) Conversor A↔B (formato rápido ↔ humano-auditable)
- Canónico = registro **estructurado y completo** (renderizable a prosa humana) → auditable.
- Índice = embeddings (**lossy, derivado**, para recall rápido). NO se intenta invertir el embedding.
- `Renderer` determinista: estructurado→prosa (humano) y prosa→estructurado (ingesta). Da velocidad
  (vectores) SIN perder verificabilidad (canónico inspeccionable). Resuelve la tensión opaco-vs-auditable.

### Mapeo hueco-del-campo → mecanismo nuestro
| Hueco abierto (admitido por el campo) | Nuestra pieza |
|---|---|
| Staleness / validez temporal (#1) | A) valid_from/until + supersesión en cadena |
| Contradicciones / conflicto | A) reglas de autoridad auditables |
| Consolidación / cajón de sastre | abstracción (patrones) + B) niveles |
| Olvido sin perder / "¿quién audita?" | B) democión medible + suelo Merkle inmutable |
| Provenance/lineage | merkle_leaf_* + edges(derived_from) |
| Seguridad / write-gating | LessonVerifier ("ley de entrada") ya existente |

## Decisiones abiertas (a cerrar antes de construir)

- ¿`sqlite-vec` vs LanceDB? → empezar `sqlite-vec` (marida con SQL relacional + Merkle); LanceDB
  solo si la escala vectorial domina. Decidir con un micro-benchmark si hace falta (regla 6: dep).
- ¿Abstracción por clustering (0 coste, determinista) o por maestro LLM (mejor etiqueta, coste/ToS)?
  → clustering primero (barato, auditable), maestro como mejora opcional.
- ¿Cómo definir "familia" para el held-out sin filtrado circular? → usar la taxonomía de probes de
  Garak como ground-truth de familia (externa, no nuestra) para evitar trampa.

## Límites honestos (declarar siempre)

- Cubre reformulación y, ojalá, algo de transferencia entre familias afines; NO familias
  radicalmente nuevas. Embedder = enabler, no magia.
- "Olvidar" es sobre el índice; la cadena es inmutable (eso es una feature, no un bug).
- El storage no es la novedad; la verificabilidad + transferencia medida sí.
