# MEMORY_OS — Atlas OS sobre la memoria real

## Principio

"Memory is the product". PERO la memoria canónica YA existe y está gobernada
por **ADR-057** (tres capas: SqliteMemoryIndex = registro/retrieval canónico
con Merkle+crypto-shred+benchmark; KuzuVectorStore = nicho Gate D; BlockMemory
= core memory). El OS **no crea una cuarta memoria autoritativa**: representa
las existentes y añade UNA capa de importación con provenance.

## Lo construido (Fase 8)

- **Lectura real**: `GET /memory/summary` — sqlite READ-ONLY sobre
  `~/atlas-mcp/memory.db` (jamás instancia SqliteMemoryIndex en el bridge: el
  constructor carga el embedder ~500MB). Verificado en vivo: 338 registros.
- **Import de conversaciones externas**: `POST /memory/import`
  (`src/atlas/api/conversation_import.py`):
  - raw SIEMPRE preservado antes de extraer (`$ATLAS_HOME/os_imports/raw/`),
    idempotente por sha256 del contenido;
  - extracción por reglas auditables (`rules_v1`): decision / failure /
    procedural; registros conformes a `schemas/memory.schema.json` con
    `provenance{source, raw_ref}` y `trust=user_stated`;
  - capa `os_import_v1` (JSONL propio) — la ingesta al índice canónico es
    cableado futuro vía `knowledge_ingest` (OPEN_QUESTIONS), no se finge.
- **Memory Vault UI**: resumen real + eventos memory.* de la sesión.

## Reglas heredadas que ESTE frente no puede violar

1. Los resúmenes no reemplazan la verdad raw (por eso raw-first en el import).
2. Toda memoria con provenance; externa marca trust/risk.
3. Contradicciones como objetos de primera clase: campo `contradicts` ya está
   en el schema; la detección es trabajo futuro (ver mem-2 en el backlog del
   operador: invalidación por contradicción CON gate de auditoría).

## Tests

`tests/test_os_memory_import.py` — raw preservado, conformidad data-driven
contra el JSON Schema, idempotencia, eventos reales sin Merkle inventado.
