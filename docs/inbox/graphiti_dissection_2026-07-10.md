---
status: propuesto
fecha: 2026-07-10
autor: disección adopt-real (agente delegado)
fuente: https://github.com/getzep/graphiti (clon efímero /tmp/graphiti-dissect, borrado al terminar)
---

# Disección adopt-real: Graphiti (Zep)

Metodología: clon `--depth 1` de solo lectura, sin `pip install` ni ejecución de código ni tests
del repo ajeno. Todas las rutas `fichero:línea` de evidencia son del clon (no de atlas-core) salvo
que se diga "NUESTRO".

Contexto nuestro ya construido (para no re-vender lo que ya tenemos):
- `src/atlas/core/graphs.py` — grafo bitemporal de código (FileVersion + IMPORTS + EVOLVES_TO por
  commit, MERGE idempotente en Kuzu, `git ls-tree`/`git show` sin checkout).
- `src/atlas/memory/memory_index.py` — `SqliteMemoryIndex`: recall coseno + `recall_lexical` FTS5 +
  `recall_temporal` + `recall_multihop` + `rrf_fuse`, `supersede`/`retire` con
  `valid_from_ns`/`valid_until_ns`, crypto-shred, tiers por ocio.
- `src/atlas/memory/obsidian_to_kuzu.py` — loader UNWIND+MERGE batcheado (16x más rápido que
  `conn.execute()` por fila, medido en vivo el 2026-07-09).

---

## 1. Esquema temporal de aristas

Graphiti usa **tres** campos temporales por arista `EntityEdge`, no solo `valid_from`/`valid_until`
como nosotros:

- `graphiti_core/edges.py:271-282` — `EntityEdge`:
  - `expired_at: datetime | None` — "cuándo se invalidó el NODO" (comentario del propio código, aunque
    aplica a la arista): es el timestamp de **cuándo el sistema decidió** que la arista dejó de ser
    vigente (tiempo de sistema/ingesta).
  - `valid_at: datetime | None` — cuándo el hecho *empezó a ser verdad en el mundo* (tiempo del hecho).
  - `invalid_at: datetime | None` — cuándo el hecho *dejó de ser verdad en el mundo* (tiempo del hecho).
  - `reference_time: datetime | None` — el timestamp del episodio/fuente que produjo la arista (para
    resolver referencias relativas tipo "ayer").

  Es decir: separan explícitamente **tiempo del hecho** (`valid_at`/`invalid_at`, bitemporal real) de
  **tiempo de sistema** (`expired_at`, cuándo lo supimos/decidimos). Nuestro `valid_from_ns`/
  `valid_until_ns` en `memory_index.py:122-123` es solo tiempo de sistema (cuándo se hizo
  `supersede`/`retire`) — no tenemos el equivalente a `valid_at`/`invalid_at` como tiempo-del-hecho
  extraído del contenido.

- El esquema persiste igual en **Kuzu** (el motor que ya usamos): `graphiti_core/models/edges/edge_db_queries.py:96-98,161-163,202-204,217-219`
  guarda `expired_at`, `valid_at`, `invalid_at` como propiedades de la relación `RelatesToNode_` (Kuzu
  no soporta propiedades ricas en aristas N:M directas, así que modelan la relación como un nodo
  intermedio — un patrón distinto al nuestro, donde `IMPORTS`/`EVOLVES_TO` sí son aristas Kuzu nativas
  con propiedades, `graphs.py:158-159`).

- El contrato de extracción pide estos campos directamente al LLM en ISO 8601:
  `graphiti_core/prompts/extract_edges.py:40-47` (`Edge.valid_at`, `Edge.invalid_at`).

**Veredicto**: esto SÍ aporta sobre lo nuestro. Tiempo-del-hecho vs tiempo-de-sistema es una distinción
real que no tenemos — hoy `valid_from_ns` en nuestro índice es siempre "cuándo until/upsert se llamó",
no "cuándo el hecho pasó a ser cierto en el mundo real" (que puede ser anterior si la memoria describe
un evento pasado). Para el grafo de código (`graphs.py`) es menos relevante porque el "hecho" y el
"tiempo de sistema" coinciden (el commit_sha ES la vigencia).

---

## 2. Invalidación por contradicción

Esto es lo que preguntabas explícitamente: **¿LLM o heurística?** Respuesta: **ambos, en dos etapas**.

**Etapa 1 — clasificación semántica por LLM** (esto SÍ automatiza lo que nuestro `supersede()` no hace:
nosotros exigimos que el llamador ya sepa qué memoria vieja reemplazar; Graphiti decide solo cuál es
la vieja).

- `graphiti_core/prompts/dedupe_edges.py:24-32` — modelo de respuesta `EdgeDuplicate`:
  ```python
  class EdgeDuplicate(BaseModel):
      duplicate_facts: list[int]      # solo de EXISTING FACTS
      contradicted_facts: list[int]   # de EXISTING FACTS o INVALIDATION CANDIDATES
  ```
- `graphiti_core/prompts/dedupe_edges.py:43-100` — prompt `resolve_edge`: recibe dos listas indexadas
  contiguas (`EXISTING FACTS` = candidatos duplicados por mismos endpoints; `FACT INVALIDATION
  CANDIDATES` = candidatos de contradicción más amplios) y un `NEW FACT`. Pide al LLM devolver los
  índices duplicados y los contradichos. Ejemplos en el prompt (líneas 85-97) enseñan la distinción:
  "Alice trabaja como ingeniera" → "Alice trabaja como ingeniera senior" es **contradicción**, no
  duplicado; "Bob corrió 5 millas el martes" vs "Bob corrió 3 millas el miércoles" no es ni una cosa
  ni la otra (eventos distintos).

**Etapa 2 — resolución temporal determinista** (heurística pura, sin LLM) sobre los candidatos que el
LLM marcó como contradichos:

- `graphiti_core/utils/maintenance/edge_operations.py:538-573` — `resolve_edge_contradictions()`:
  compara `edge.valid_at`/`edge.invalid_at` contra `resolved_edge.valid_at`/`invalid_at`. Si el edge
  viejo ya estaba invalidado antes de que el nuevo empezara a ser válido (o viceversa, sin solapar en
  el tiempo), **no** lo invalida — son hechos de ventanas temporales distintas, no una contradicción
  real. Si el viejo es estrictamente anterior al nuevo y ambos están vigentes, entonces sí: pone
  `edge.invalid_at = resolved_edge.valid_at` y `edge.expired_at = utc_now()`.
- `graphiti_core/utils/maintenance/edge_operations.py:820-844` — en `resolve_extracted_edge()`, ANTES
  de invalidar a otros, primero decide si el propio edge nuevo debe nacer ya expirado (si hay un
  candidato de invalidación con `valid_at` *posterior* al del nuevo edge, el nuevo edge nace inválido
  — información más reciente le gana). Solo entonces llama a `resolve_edge_contradictions` para
  invalidar a los viejos.

**Veredicto**: esto es el patrón más absorbible de los tres. Nuestro `supersede()` (`memory_index.py:565-605`)
requiere que el CALLER ya conozca `old_id` — es manual. Graphiti automatiza la DECISIÓN de "¿esto es
nuevo, duplicado, o contradice algo?" combinando (a) un LLM que compara texto semánticamente con
ejemplos few-shot explícitos anti-falsos-positivos ("NUNCA marques duplicados con diferencias en
números/fechas/calificadores clave") y (b) una regla temporal determinista de desempate que NO
requiere LLM. La heurística temporal por sí sola (sin LLM) ya es portable y barata.

---

## 3. Búsqueda híbrida

- `graphiti_core/search/search_utils.py:1780-1796` — `rrf()`: Reciprocal Rank Fusion, idéntico en
  espíritu a nuestro `rrf_fuse` (`memory_index.py:46-64`). Diferencia de parámetro: Graphiti usa
  `rank_const=1` por defecto; nosotros usamos `k=60` (el valor "canónico" de la literatura RRF
  original). Ambos son la misma fórmula `1/(k+rank)`; el valor de k solo cambia cuánto se aplana la
  cola. No hay diferencia estructural.
- `graphiti_core/search/search_config.py:53-77` — el reranker es **configurable por tipo de búsqueda**
  (`EdgeReranker`/`NodeReranker`/`EpisodeReranker`/`CommunityReranker`), con opciones:
  `rrf` (default), `node_distance` (distancia BFS al nodo-centro de la query, `search_utils.py:1798-1857`),
  `episode_mentions` (cuántos episodios mencionan el nodo, como proxy de importancia, `1860-1898`),
  `mmr` (Maximal Marginal Relevance para diversidad, `1901-1939`), y `cross_encoder` (reranker LLM
  aparte, mencionado en el enum pero no inspeccionado en detalle aquí).
- Fuentes fusionadas: BM25 (`edge_fulltext_search`/`node_fulltext_search`, líneas 185 y 579),
  similitud coseno de embeddings (`edge_similarity_search`/`node_similarity_search`, líneas 300 y 672),
  y BFS de grafo (`edge_bfs_search`/`node_bfs_search`, líneas 448 y 790) — tres fuentes, nosotros
  tenemos dos (coseno + FTS5 lexical) más `recall_temporal` y `recall_multihop`, que Graphiti no separa
  como "fuente" sino que resuelve con el reranker `node_distance`/BFS.

**Veredicto**: NO aporta nada nuevo sobre RRF — ya lo tenemos y es la misma fórmula. Lo único
mínimamente interesante es `maximal_marginal_relevance` (diversidad de resultados, penaliza
resultados redundantes entre sí) como reranker ALTERNATIVO a RRF, útil si algún día notamos que
`recall_all`/`recall_multihop` devuelve resultados casi-duplicados. Es opcional, no urgente — no
generamos item de backlog para esto porque no hay evidencia de que sea un problema real hoy
(especular no cuenta).

---

## 4. Extracción de entidades/relaciones con LLM

- `graphiti_core/prompts/extract_nodes.py:28-58` — contratos Pydantic: `ExtractedEntity` (name,
  `entity_type_id` de una lista cerrada, `episode_indices`), `ExtractedEntities` (lista), y
  `SummarizedEntity`/`SummarizedEntities` para resúmenes incrementales de entidades.
- `graphiti_core/prompts/extract_nodes.py:83-140` — el prompt de extracción es MUY restrictivo por
  diseño: lista explícita de qué NUNCA extraer (pronombres, conceptos abstractos, sustantivos
  genéricos sin calificar, fragmentos de oración) antes incluso de decir qué SÍ extraer. Es una técnica
  de prompt-engineering (negative constraints primero) más que una técnica arquitectónica.
- `graphiti_core/prompts/extract_edges.py:25-56` — contrato de aristas: `Edge` (source/target por
  nombre, `relation_type` en `SCREAMING_SNAKE_CASE`, `fact` en lenguaje natural, `valid_at`/
  `invalid_at` ISO 8601, `episode_indices`), envuelto en `ExtractedEdges`.
- **Cómo acotan el JSON** (la parte técnica reutilizable): `graphiti_core/llm_client/client.py:215-221`
  — NO usan function-calling/tool-use nativo del proveedor como mecanismo primario; serializan
  `response_model.model_json_schema()` (JSON Schema generado por Pydantic) y lo **inyectan como texto**
  al final del último mensaje ("Respond with a JSON object in the following format: {schema}"),
  agnóstico de proveedor. Luego parsean y validan contra el mismo modelo Pydantic
  (`_generate_response_with_retry`, con reintento si la validación falla — no inspeccionado a fondo el
  bucle de reintento, pero el patrón general es "schema-in-prompt + parse-and-validate + retry").

**Veredicto**: parcialmente absorbible. El patrón "negative constraints primero" en el prompt es una
técnica de prompting, no de arquitectura — barata de copiar si algún día extraemos entidades con LLM,
pero no tenemos ese caso de uso hoy (nuestro grafo de código es determinista vía AST, no LLM). El
patrón "JSON Schema de Pydantic inyectado en texto, agnóstico de proveedor" es el equivalente de bajo
nivel a lo que probablemente ya resolvemos vía tool-calling estructurado del proveedor en
`InferenceHub` — no tenemos evidencia de que necesitemos cambiar de mecanismo. No genero item de
backlog para este punto: no hay gap concreto, es una nota de referencia.

---

## Tabla comparativa

| Capacidad | Graphiti (ellos) | Atlas (nosotros) | ¿Gap real? |
|---|---|---|---|
| Vigencia temporal de arista | `valid_at`/`invalid_at` (tiempo del HECHO) + `expired_at` (tiempo de SISTEMA) — `graphiti_core/edges.py:271-282` | `valid_from_ns`/`valid_until_ns` (solo tiempo de sistema) — `src/atlas/memory/memory_index.py:122-123` | **Sí** — nos falta tiempo-del-hecho separado de tiempo-de-decisión |
| Invalidación por contradicción | LLM clasifica duplicado/contradicción + heurística temporal determinista decide quién expira — `graphiti_core/utils/maintenance/edge_operations.py:538-573`, `graphiti_core/prompts/dedupe_edges.py:24-100` | `supersede(old_id, new_record)` manual, el caller debe saber `old_id` — `src/atlas/memory/memory_index.py:565-605` | **Sí** — es justo el gap que preguntabas |
| Fusión híbrida de ranking | RRF (default) + node_distance + episode_mentions + MMR + cross_encoder, configurable por tipo — `graphiti_core/search/search_config.py:53-77` | `rrf_fuse` (coseno + FTS5 + temporal + multihop) — `src/atlas/memory/memory_index.py:46-64`, `768-1112` | No — mismo mecanismo, ya lo tenemos |
| Extracción de entidades/relaciones LLM | Pydantic model + JSON-schema-en-texto + prompt con negative constraints — `graphiti_core/prompts/extract_nodes.py`, `graphiti_core/prompts/extract_edges.py`, `graphiti_core/llm_client/client.py:215-221` | N/A (nuestro grafo de código es determinista vía AST, `src/atlas/core/graphs.py:77-129`); memoria usa embeddings, no extracción de entidades | Sin comparación directa — casos de uso distintos |
| Backend Kuzu | Soportado, aristas ricas modeladas como nodo intermedio `RelatesToNode_` — `graphiti_core/models/edges/edge_db_queries.py` | Aristas Kuzu nativas con propiedades (`IMPORTS`, `EVOLVES_TO`) — `src/atlas/core/graphs.py:158-159` | No — nuestro patrón es más simple porque no necesitamos el nodo intermedio (Kuzu si soporta propiedades en relaciones 1:1 declaradas así, lo que ya usamos) |

---

## Patrones absorbibles (máximo 3, honesto)

### 1. Separar tiempo-del-hecho (`valid_at`/`invalid_at`) de tiempo-de-sistema (`valid_from_ns`/`valid_until_ns`)

- **Qué es**: dos pares de timestamps en vez de uno. Hoy `valid_from_ns` en `SqliteMemoryIndex.upsert`
  siempre es "cuándo se llamó upsert/supersede", nunca "cuándo el hecho descrito pasó a ser cierto en
  el mundo". Si una memoria dice "el usuario decidió el 2026-06-01 que prefiere X" pero se ingiere el
  2026-07-10, hoy solo tenemos el 07-10.
- **Dónde encajaría**: `src/atlas/memory/record.py` (añadir campos opcionales `fact_valid_at`/
  `fact_invalid_at` a `MemoryRecord`) + `src/atlas/memory/memory_index.py` (columnas nuevas en
  `_SCHEMA`, migración idempotente al estilo de `_migrate_temporal`/`_migrate_class_ttl`, y opcionalmente
  extender `recall_temporal` para razonar sobre tiempo-del-hecho en vez de (o además de)
  `valid_from_ns`).
- **Coste**: S — mismo patrón de migración idempotente que ya existe 4 veces en el fichero
  (`_migrate_temporal`, `_migrate_shred`, `_migrate_tenant`, `_migrate_class_ttl`), campos opcionales
  con default NULL, no rompe compatibilidad.
- **¿Backlog?** Sí, mecánico.

```yaml
- id: mem-1-fact-time-vs-system-time
  title: "Separar tiempo-del-hecho de tiempo-de-sistema en el índice de memoria"
  why: >
    Graphiti (Zep) distingue valid_at/invalid_at (cuándo el hecho fue/dejó de ser cierto EN EL MUNDO)
    de expired_at (cuándo el SISTEMA decidió invalidarlo). Nuestro valid_from_ns/valid_until_ns en
    SqliteMemoryIndex es únicamente tiempo de sistema (cuándo se llamó upsert/supersede/retire) —
    perdemos la fecha real del hecho cuando una memoria describe algo pasado ingerido tarde.
    Disección: docs/inbox/graphiti_dissection_2026-07-10.md#1.
  targets:
    - "src/atlas/memory/record.py"
    - "src/atlas/memory/memory_index.py"
  acceptance: >
    MemoryRecord acepta fact_valid_at_ns/fact_invalid_at_ns opcionales (default None = comportamiento
    actual sin cambios); SqliteMemoryIndex persiste estas dos columnas nuevas vía migración idempotente
    (mismo patrón que _migrate_temporal); recall_temporal puede razonar opcionalmente sobre
    fact_valid_at_ns cuando está presente sin romper el comportamiento por defecto (valid_from_ns);
    test demuestra que una memoria con fact_valid_at_ns en el pasado, ingerida hoy, se recupera
    correctamente para consultas "as_of" ancladas al tiempo del hecho, no al de ingesta.
  priority: 3
  status: propuesto
  test_cmd: "pytest tests/test_memory_index.py tests/test_memory_index_multihop.py -x -q"
```

### 2. Auto-invalidación de contradicciones: LLM clasifica, heurística temporal decide

- **Qué es**: en vez de exigir que el caller conozca `old_id` para `supersede()`, un paso que (a)
  recupera candidatos por similitud (ya tenemos `recall_all`), (b) pide a un LLM clasificar
  duplicado/contradicción con few-shot anti-falsos-positivos (patrón exacto:
  `graphiti_core/prompts/dedupe_edges.py:43-100`), y (c) aplica la regla temporal determinista de
  `resolve_edge_contradictions` (sin LLM) para decidir cuál de los dos gana y cuál se marca superseded.
- **Dónde encajaría**: nueva función `src/atlas/memory/contradiction_resolver.py` (no meterlo dentro de
  `memory_index.py` — mezclaría el motor determinista con juicio LLM, que es exactamente la frontera
  que ya respetamos en otras partes del proyecto: el motor no debe requerir LLM para funcionar). La
  función llamaría a `SqliteMemoryIndex.recall_all` para candidatos y a `SqliteMemoryIndex.supersede`
  para aplicar el resultado — no toca el esquema del índice.
- **Coste**: M — requiere un cliente LLM (ya existe `InferenceHub`), un prompt nuevo con los ejemplos
  anti-falso-positivo, y la función de resolución temporal (la parte barata, ~30 líneas, portable
  directamente del patrón de `resolve_edge_contradictions`). El riesgo real es de producto, no técnico:
  decidir automáticamente que memoria A invalida a memoria B es una decisión con consecuencias (borrado
  lógico) — igual que el resto de nuestras políticas de "juicio real", debería pasar por un gate
  auditable (Merkle log, como ya hace `supersede` vía `_audit`), no aplicarse silenciosamente.
- **¿Backlog?** Sí, pero marcado explícitamente como requiriendo diseño de gating antes de implementar
  (no es un ítem mecánico puro).

```yaml
- id: mem-2-llm-contradiction-resolver
  title: "Resolución de contradicciones semi-automática (LLM clasifica, heurística decide)"
  why: >
    supersede() hoy exige que el caller ya sepa qué memoria vieja reemplaza la nueva — no hay
    detección automática de que dos memorias se contradicen. Graphiti resuelve esto en dos etapas:
    LLM clasifica duplicado/contradicción con ejemplos few-shot anti-falso-positivo, y una regla
    temporal determinista (sin LLM) decide cuál expira. La segunda mitad es portable sin LLM;
    la primera requiere un gate de auditoría porque decide un borrado lógico automáticamente.
    Disección: docs/inbox/graphiti_dissection_2026-07-10.md#2.
  targets:
    - "src/atlas/memory/contradiction_resolver.py"
  acceptance: >
    resolve_contradiction(index, candidate_record) recupera candidatos vía recall_all, clasifica
    con InferenceHub usando un prompt con >=3 ejemplos few-shot (duplicado exacto / contradicción por
    actualización / ni uno ni otro, siguiendo los ejemplos de dedupe_edges.py), aplica la regla
    temporal determinista SIN LLM para decidir expiración cuando hay solape temporal, y llama a
    supersede() solo tras pasar por un WriteGate/audit explícito (no aplica el borrado lógico
    silenciosamente). Test con memorias sintéticas demuestra: (a) contradicción real detectada y
    resuelta correctamente, (b) actualización de calificador (ej. "ingeniera" -> "ingeniera senior")
    NO se marca como duplicado sino como contradicción, (c) hechos en ventanas temporales distintas
    NO se invalidan mutuamente.
  priority: 3
  status: propuesto
  test_cmd: "pytest tests/test_memory_index.py -k contradiction -x -q"
```

### 3. MMR como reranker alternativo para diversidad de resultados

- **Qué es**: Maximal Marginal Relevance (`graphiti_core/search/search_utils.py:1901-1939`) — en vez de
  rankear solo por relevancia (RRF/coseno), penaliza resultados muy similares entre sí para diversificar
  el top-k. Fórmula: `mmr = lambda * sim(query, candidate) - (1-lambda) * max_sim(candidate, ya_elegidos)`.
- **Dónde encajaría**: `src/atlas/memory/memory_index.py`, como variante opcional de `recall_all`
  (parámetro `diversify: bool = False`).
- **Coste**: S — es una función pura de ~25 líneas sobre vectores ya calculados, no toca el esquema ni
  la persistencia.
- **¿Backlog?** No. No hay evidencia de que `recall_all`/`recall_multihop` produzcan hoy resultados
  redundantes que perjudiquen a nadie — sería especular sobre un problema que no hemos medido. Se deja
  aquí como nota de referencia, no como item: si el benchmark honesto (`scripts/eval_memory_benchmark.py`,
  ya existente) algún día muestra redundancia en el top-k, este es el patrón a copiar.

---

## Notas descartadas sin rodeos

- La fusión híbrida general de Graphiti (BM25+coseno+RRF) **no aporta nada nuevo**: es la misma
  fórmula RRF que `rrf_fuse` ya implementa, con una constante de suavizado distinta (1 vs 60) que no
  cambia la estructura.
- El mecanismo de "JSON schema en texto" para acotar salida LLM es una técnica de bajo nivel que
  probablemente ya resolvemos mejor vía tool-calling nativo del proveedor en `InferenceHub` — no hay
  evidencia de que necesitemos degradar a schema-en-texto.
- El patrón de extracción de entidades con negative-constraints-first es aplicable solo si algún día
  extraemos entidades de texto libre vía LLM; hoy nuestro grafo de código es determinista (AST) y
  nuestra memoria no hace extracción de entidades, así que no hay gancho de código real hoy — anotado
  como referencia, no como gap.

---

## Confirmación de limpieza

Clon en `/tmp/graphiti-dissect` borrado (`rm -rf /tmp/graphiti-dissect`) al terminar esta disección. No
se ejecutó código del repo ajeno, no se instaló ninguna dependencia suya, no se corrieron sus tests.
