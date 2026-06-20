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

## Fases de construcción (cuando toque; una a una)

- **1a.** `LessonStore` respaldado por SQLite (FTS5+sqlite-vec) manteniendo el Merkle. Recall vía
  SQLite (sustituye el escaneo lineal actual de `LessonRecaller`). Tests: paridad con el actual.
- **1b.** `PatternAbstractor` (ejemplos → patrones/familias). Recall sobre patrones.
- **1c.** Experimento de transferencia (held-out por familia) + reporte/curva.
- **1d.** `Curator` (olvido: dedup/supersede/decay), solo sobre el índice.

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
