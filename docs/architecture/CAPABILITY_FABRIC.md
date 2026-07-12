# CAPABILITY_FABRIC — Atlas OS

## Autoridad existente

La capability fabric REAL de Atlas ya existe y es previa al OS:

- **MCP trunk** (`src/atlas/mcp/`): catálogo graduado por sectores,
  `trunk_invoke` (HITL) / `trunk_invoke_readonly` (fail-closed), adopción de
  servers externos untrusted-por-defecto con backoff persistente.
- **Tools nativas** (`src/atlas/tools/`) con niveles L-det/L0/L1/L2 y AST
  Guard para código generado.
- **Sandbox**: BwrapJail fail-closed (`LayeredIsolationSandbox`).

## Qué añade el OS

- `schemas/adapter.schema.json` (del pack, revisado): contrato neutro para
  describir CUALQUIER capacidad (local_cli/local_service/remote_api/mcp/
  importer/internal) con risk_profile, permisos requeridos, sandbox_required,
  memory/audit policy y failure_modes.
- La representación en UI (nodos tool/adapter en el Living Graph).

## Regla

Los frameworks externos (MCP servers, Playwright, LangGraph si algún día
entra) son motores DETRÁS de un adapter con contrato; el kernel es propio
(pack ADR-0007, confirmado). Un adapter sin failure_modes declarados no está
completo. La adopción de capacidad externa sigue el invariante 9 de AGENTS.md:
untrusted, fail-closed, reversible, con consentimiento explícito si instala o
ejecuta código de terceros.
