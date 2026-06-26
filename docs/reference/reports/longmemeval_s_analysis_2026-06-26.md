# LongMemEval_S — Análisis de retrieval (2026-06-26)

Benchmark: [xiaowu0162/longmemeval-cleaned](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned)
Embedder: `ATLAS_EMBEDDER=fastembed` (paraphrase-multilingual-MiniLM-L12-v2, dim=384)
Métrica: Recall@k binario (1.0 si la sesión de respuesta aparece en top-k)

## Resultados n=500

### k=5

| Tipo (n) | cosine | hybrid | temporal |
|---|---|---|---|
| knowledge-update (78) | 0.256 | **0.513** | 0.256 |
| multi-session (133) | 0.301 | 0.308 | 0.301 |
| single-session-assistant (56) | 0.518 | 0.518 | 0.518 |
| single-session-preference (30) | 0.100 | **0.200** | 0.100 |
| single-session-user (70) | 0.257 | **0.357** | 0.257 |
| temporal-reasoning (133) | 0.278 | 0.278 | 0.278 |
| **OVERALL** | **0.294** | **0.356** | **0.294** |

### k=10 (6 modos)

| Tipo (n) | cosine | hybrid | temporal | temporal_aof | multihop | hybrid_multihop |
|---|---|---|---|---|---|---|
| knowledge-update (78) | 0.487 | **0.705** | 0.487 | 0.487 | 0.000 | **0.705** |
| multi-session (133) | 0.481 | 0.481 | 0.481 | 0.481 | 0.000 | 0.481 |
| single-session-assistant (56) | 0.661 | 0.661 | 0.661 | 0.661 | 0.196 | 0.643 |
| single-session-preference (30) | 0.133 | **0.233** | 0.133 | 0.133 | 0.000 | **0.233** |
| single-session-user (70) | 0.429 | **0.514** | 0.429 | 0.429 | 0.000 | **0.514** |
| temporal-reasoning (133) | 0.511 | 0.511 | 0.511 | 0.511 | 0.015 | 0.511 |
| **OVERALL** | **0.482** | **0.534** | **0.482** | **0.482** | **0.026** | **0.532** |

## Diagnóstico por modo

**hybrid (+21% k=5, +11% k=10 sobre cosine)**
El BM25 gana donde los embeddings fallan: entidades nombradas, IDs, tokens exactos.
Efecto más fuerte en `knowledge-update` (×2 en k=5, +45% en k=10).

**temporal = cosine**: sin `as_of`, el filtro válido-hasta no discrimina (todos los registros
son válidos en t=ahora).

**temporal_aof = cosine**: TODAS las sesiones haystack son anteriores a `question_date` →
el filtro `as_of=question_date` no excluye nada. Para discriminar habría que usar la fecha
de la sesión como corte (¿qué estaba activo EN LA ÉPOCA de la pregunta?), pero LongMemEval
no está diseñado para eso: las sesiones SON el pasado, la pregunta es siempre posterior.

**multihop = 0**: `recall_multihop` devuelve máximo `hops=2` resultados (cadena, no
búsqueda amplia) → Recall@10 trivialmente acotado a 2. No es el modo correcto para este
eval. multihop está diseñado para seguir cadenas de conocimiento, no para búsqueda de
sesiones relevantes.

**hybrid_multihop ≈ hybrid**: los 2 resultados de multihop añaden ruido marginal.

## Gaps vs SOTA

SOTA papers reportan ~0.60-0.70 Recall@5 en sistemas completos (con LLM + chunking + reranking).
Atlas hybrid k=10 = 0.534. Gaps concentrados en:

1. **multi-session (0.481)**: preguntas que requieren razonamiento entre sesiones (A + B → respuesta).
   Atlas no tiene cross-session linking. Solución: grafo temporal (kuzu, ADR-040 scope) o
   chunking + reranking con LLM.

2. **temporal-reasoning (0.511 k=10)**: preguntas tipo "¿cuándo empecé X?" que requieren
   encontrar la primera mención, no solo la más similar. Solución: indexar timestamps de sesión
   + query de rango temporal sobre el grafo.

3. **single-session-preference (0.233 k=10)**: preguntas sobre preferencias personales
   (alimentación, hobbies) que se expresan indirectamente. Solución: user-modeling / memory_class
   "preference" con scoring diferenciado.

## Próximos pasos

1. k=20 para ver el techo de recall puro (sin razonamiento).
2. Reranker: dado top-20, LLM-as-judge que ordena por relevancia a la pregunta.
3. Grafo kuzu: cross-session links para multi-session.
4. Chunking sub-sesión: sesiones largas pueden fragmentarse (hoy = 1 record/sesión).

Datos brutos: `longmemeval_s_baseline_2026-06-26.json` (k=5) y
`longmemeval_s_k10_all_modes_2026-06-26.json` (k=10, 6 modos).
