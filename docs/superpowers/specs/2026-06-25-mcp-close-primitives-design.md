# Diseño — Cierre de primitivos MCP del tronco

Brainstorming 2026-06-25. El usuario decidió cerrar el MCP (6 primitivos + Tasks) antes de pasar al workflow
Dynamic (SP-E). El audit (`docs/design/mcp_six_primitives_audit.md`) dejó abiertos #3–#5 + extensiones. Honesto:
cada primitivo lleva un consumidor real y testeable; los client-features (Elicitation/Sampling/Roots) se
exponen como capacidad lista — su consumidor PLENO es el workflow (SP-E).

## Hechos (mcp 1.28 en .venv, decide-with-facts)
- Completion: `@server.completion()` (handler async ref/argument/context). ✓
- Logging: `ctx.info/debug/warning/error` (notifications/message). ✓ — `set_logging_level` NO lo maneja FastMCP.
- Progress: `ctx.report_progress(progress, total, message)`. ✓
- Elicitation: `ctx.elicit(message, schema: BaseModel) -> ElicitationResult` (.action/.data). ✓
- Sampling: NO hay `ctx.sample`; sí `ctx.session.create_message(messages, max_tokens=...)`. ✓
- Roots: `ctx.session.list_roots() -> ListRootsResult(.roots)`. ✓
- Test harness: `mcp.shared.memory.create_connected_server_and_client_session` con callbacks
  sampling/list_roots/logging/elicitation → ejercita todo como cliente real.
- Tasks: tipos presentes en `mcp.types` (CreateTaskResult/GetTaskRequest/…); soporte high-level por evaluar.

## Unidades (`src/atlas/mcp/trunk_capabilities.py`, registradas desde build_trunk_server)
- `register_discovery_capabilities(server, catalog, skill_store)`:
  - **Completion**: autocompleta nombres de skills (PromptReference) y kind/name del template
    `catalog://item/{kind}/{name}` (ResourceTemplateReference), filtrando por lo tecleado. Consumidor real.
  - **trunk_selfcheck** (tool): cobertura del catálogo por estado emitiendo **Logging** + **Progress** en etapas.
- `register_workflow_capabilities(server)` — capacidad lista, consumidor = SP-E:
  - **trunk_confirm** (Elicitation): confirmación humana estructurada (sí/no) = hook HITL.
  - **trunk_reason** (Sampling): pide completion al modelo del cliente = base del regulador de tokens (SP-B).
  - **trunk_list_roots** (Roots): ámbitos de filesystem concedidos por el cliente.

## Pendiente (lote C, los dos difíciles)
- **push-subscriptions** del catálogo (`resources/updated`): FastMCP high-level no lo expone → low-level Server
  (`subscribe_resource`) + watcher de mtime. Item `catalog-resources-live-subscriptions`.
- **Tasks** (extensión async): evaluar soporte high-level; si no, entregar assessment honesto + defer
  (wire-before-claim — no fingir una extensión sin consumidor ni soporte).

## DoD
Tests por primitivo (harness in-memory) verdes + mypy strict + ledger/backlog en el mismo commit. No se declara
"workflow" — los client-features son capacidad; el consumidor pleno llega con SP-E.
