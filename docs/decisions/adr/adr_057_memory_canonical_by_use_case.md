# ADR-057 — Memoria: canónico por caso de uso (no fusionar, no puentear todavía)

- Estado: aceptado (2026-07-10)
- Contexto: campaña x10; exploración fresca de los sistemas de memoria
  (evidencia en este doc) + veredicto del Cónclave del programa de memoria
  (MEDIR primero; decay no).

## Decisión

Atlas tiene TRES capas de memoria y cada una es canónica para su caso de uso.
No se fusionan ni se puentean hoy:

1. **SqliteMemoryIndex** (`src/atlas/memory/memory_index.py`, BD
   `~/atlas-mcp/memory.db`, fastembed dim=384) = **memoria de registro y
   retrieval**. Canónica para: decisiones (MemoryDecisionSink), lecciones
   persistentes (SqliteLessonIndex), conocimiento ingerido
   (knowledge_ingest), recall del tronco MCP (MemoryTrunk). Es la ÚNICA capa
   con procedencia Merkle, crypto-shred y benchmark (eval_longmemeval /
   eval_memory_benchmark corren exclusivamente contra ella).
2. **KuzuVectorStore** (`src/atlas/memory/vector_store.py`, BD
   `workspace/memory/kuzu/atlas.kuzu`) = **índice semántico nicho del Gate D**
   (patterns/failures/evidence para distiller/error-registry/pattern-store).
   Se mantiene, no se fusiona. Hecho verificado 2026-07-10: el directorio
   `workspace/memory/kuzu` NI EXISTE en esta máquina — sus consumidores no
   han generado datos reales todavía.
3. **BlockMemory** (`src/atlas/memory/block_memory.py`) = **core memory**
   (bloques siempre-en-contexto estilo Letta/MemGPT), complemento declarado
   del archival, sin solape con las otras dos.

**No-decisión explícita**: el puente Sqlite↔Kuzu queda DIFERIDO. Trigger de
re-litigio cuantitativo: cuando `KuzuVectorStore.count()` supere ~100 filas
reales de producción (hoy: 0 — la BD no existe), se reabre la pregunta con
datos. Construirlo hoy sería puentear un lado vacío (wire-before-claim).

Nota: el grafo del proyecto (`project_graph.kuzu`, tools graph_*) NO es
memoria — es estructura de código regenerable; queda fuera de este ADR.

## Qué se arregló para poder decidir con datos

- La medición no era reproducible: el dataset LongMemEval_S (265MiB, HF
  `xiaowu0162/longmemeval-cleaned`, MIT) exigía descarga manual sin
  documentar → `scripts/fetch_longmemeval.py` (idempotente por tamaño).
- `BenchmarkGate` estaba sin cablear en el batcher (TODO histórico) y con
  bug latente (`BenchmarkResult.to_dict()` inexistente, tragado por un
  except → señal siempre None). Cableado + tri-estado `skipped` accionable.

## Apéndice — baseline reproducible (esta máquina, 2026-07-10)

Comando:

```bash
.venv/bin/python scripts/fetch_longmemeval.py
ATLAS_EMBEDDER=fastembed .venv/bin/python scripts/eval_longmemeval.py \
  --n 500 --mode all --k 5 --seed 42
```

Hallazgo del camino (2026-07-10): el eval construía el índice SIN embedder
(default stub de la clase) — TERCERA aparición de la clase de bug "embedder
ignora el env". Los históricos 0.294/0.356 eran el stub; con el fix el
número real es reproducible.

Resultados (Recall@5, seed=42, fastembed dim=384, esta máquina):

- Humo n=50: **0.9400** overall (cosine=hybrid=temporal; coherente con el
  histórico 0.934). Con stub (control): 0.35 — la separación semántica es
  real, no artefacto.
- Full n=500: PENDIENTE-EN-CURSO al firmar este ADR (corrida larga en CPU;
  se anota aquí al terminar sin cambiar la decisión — el humo ya valida la
  reproducibilidad).
- Anomalía anotada: modo multihop = 0.0 en este dataset con ambos
  embedders (pre-existente, independiente del embedder; investigar aparte
  si multihop entra en el camino de producción).

Histórico de referencia (docs/design/atlas_synthesis_2026-06-26.md): cosine
0.294 / hybrid 0.356 (stub); R@5=0.934 fastembed híbrido.
