# ADR-031 — Loop agéntico de tool-calls

- Status: Accepted (2026-05-29)
- Módulos: `src/atlas/core/inference_hub.py`, `src/atlas/core/orchestrator.py`

## Contexto

`InferenceHub.infer` era **single-shot**: una sola `litellm.completion` con
`[system, user]` y sin `tools`. Consecuencias:

1. **Alucinación factual.** Las preguntas que no matcheaban el routing por
   keywords (`_execute_task`) caían a inferencia LOCAL_SAFE y el modelo
   inventaba datos (el caso de los commits falsos por Telegram).
2. **Block memory a medias (ADR-030).** El modelo no podía auto-editar sus
   bloques de core memory porque no tenía forma de llamar a una herramienta;
   solo quedaba la mutación humana (CLI/API).

Ambos problemas tienen la misma raíz: falta un loop de tool-calls.

## Decisión

Añadir un loop agéntico que expone herramientas al modelo vía la API estándar
de tool-calling de LiteLLM (formato OpenAI), ejecuta las que pida —auditadas—,
reinyecta los resultados y vuelve a llamar hasta respuesta final.

| # | Decisión | Elección | Razón |
|---|----------|----------|-------|
| 1 | Dónde vive el loop | Orchestrator (`_execute_local_safe_via_inference`) | Posee tools, audit, permisos, PII, blocks. InferenceHub sigue siendo router puro |
| 2 | Transporte de tools | `InferenceRequest.tools/messages/tool_choice`; `InferenceResponse.tool_calls/finish_reason` | Backward-compat: sin `tools` → comportamiento idéntico |
| 3 | Tools v1 | Lectura: git_log/status/diff, list_workspace, atlas_status, read_memory_blocks. Escritura: edit/append_memory_block | Grounding + auto-edición de blocks. Mutantes de host (browser/editor) siguen por AWAITING_APPROVAL |
| 4 | Auditoría | Cada tool-call → `tool.invoked` en Merkle; las git/fs/block ya auto-auditan | Regla 1 |
| 5 | Cota | `max_iters=5`; al exceder devuelve lo último | Evita loops infinitos / quema de cuota |
| 6 | PII | Resultados de tool redactados antes de reinyectar | Coherente con el pipeline |
| 7 | Activación | **Always-on** para LOCAL_SAFE; degrada a single-shot si el modelo no pide tools | El loop no cambia nada cuando no hay tool_calls (stub/tests incluidos) |
| 8 | Deps | Ninguna nueva (LiteLLM ya soporta `tools=`) | Regla 6 |
| 9 | Presión de bloque | `BlockLimitExceeded` se devuelve como texto de error al modelo, no como excepción | Mecanismo MemGPT: el modelo resume/acorta en vez de fallar |

## Compatibilidad

La primera llamada del loop conserva `prompt` + `context` (render de bloques
incluido), así que el comportamiento previo —y los tests que inspeccionan
`request.context`/`request.prompt` o asumen `infer` llamado una sola vez— se
mantiene intacto: si el modelo no devuelve `tool_calls` (caso stub/mock), hay una
única iteración y el resultado es el de siempre (`inference_hub.complete`).

## Consecuencias

- Las preguntas factuales se contestan con datos reales (git/fs/status) en vez
  de inventarse.
- El modelo puede mantener su propia core memory (ADR-030 fase 2 completa).
- `task.result` añade `iterations` y `tools_used` para trazabilidad.

## Fuera de alcance

- Tools mutantes de host dentro del loop (requiere HITL inline).
- Selección dinámica de qué subconjunto de tools exponer según la intención.

## Tests

`tests/test_orchestrator_pipeline_d.py::TestAgenticLoop` — ejecución de tool +
respuesta final, auto-edición de block, presión por límite (no-crash), tope de
iteraciones. Los tests previos del path de inferencia siguen verdes sin cambios.
