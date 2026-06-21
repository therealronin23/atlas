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
- [~] **1c — DOS ejes (antes fundidos; separados 2026-06-21):**
  - **1c-seguridad** *(HECHO 2026-06-21, primer corte; `scripts/redteam/transfer_experiment.py`
    + `docs/immune_transfer_experiment.md`):* held-out por familia (train: instruction_override,
    persona_jailbreak; held-out: exfiltration, encoding_evasion), anclado en Merkle. RESULTADO
    HONESTO: léxico = MEMORIZA (0% transferencia, vocabulario disjunto). Semántico (MiniLM,
    umbral calibrado 0.60 con sanidad 100%) = transferencia PARCIAL REAL: **heldout_recall 33%
    con benign_fp 0%** → no es enciclopedia pura ni generalización resuelta. CONFOUNDS declarados:
    umbral clustering==recall (techo optimista), semillas ilustrativas (no Garak real aún),
    conjuntos pequeños.
    PULIDO 2026-06-21: confound clustering==recall RESUELTO (umbrales separados en
    `MemoryAbstractor`: `cluster_threshold` vs `recall_threshold`, testeado). Medida limpia
    (cluster 0.80 → 2 patrones, uno por familia): sanidad 100% con held-out 16.7%→66.7% según
    recall (0.62→0.58) y benign_fp 0% → la transferencia SOBREVIVE al quitar el confound (no era
    artefacto). PENDIENTE rigor: set benigno fronterizo (el 0% FP no está estresado) + corpus
    real de Garak + intervalos de confianza.
  - **1c-motor:** el sustrato sabe versionar/superseder/transferir en CUALQUIER dominio (sin
    Garak). Va con 1d (validez temporal) + un test de transferencia genérico. PENDIENTE.
- [ ] **1d — `Curator`** (olvido principiado: dedup/supersede/decay) SOLO sobre el índice; la cadena
  Merkle nunca borra. Incluye capa A (validez temporal `valid_from/until` + supersesión auditable)
  y capa B (tiers hot/warm/cold/pending con democión medible).

Notas de estado se anotan inline al cerrar cada casilla (fecha + commit + límite honesto).

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
