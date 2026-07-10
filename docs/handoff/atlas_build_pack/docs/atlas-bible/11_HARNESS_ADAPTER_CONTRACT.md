# 11 — Harness Layer and Adapter Contract

## Definición

El Execution Harness Layer es el órgano que ejecuta tareas. Vive dentro de Atlas, pero Atlas es más grande.

## Harness incluye

```text
- Agent loop
- Tool calling
- Model routing
- Memory read/write
- Guardrails
- Human approval
- Background execution
- Logging
- Audit
```

## Adapter Contract

Todo adapter debe cumplir:

```json
{
  "id": "adapter_aider",
  "display_name": "Aider",
  "provider_type": "local_cli",
  "capability_type": "coding",
  "input_schema": {},
  "output_schema": {},
  "required_permissions": ["filesystem.write", "git.diff"],
  "risk_profile": "medium",
  "sandbox_required": true,
  "supports_streaming": true,
  "supports_diff": true,
  "supports_files": true,
  "supports_rollback": true,
  "emits_events": true,
  "memory_policy": "summarize_and_store",
  "audit_policy": "full",
  "failure_modes": ["cli_missing", "repo_dirty", "permission_denied"]
}
```

## Tipos de adapters

```text
Model Adapter
Tool Adapter
Workspace Adapter
Conversation Import Adapter
Coding Adapter
Research Adapter
System Adapter
MCP Adapter
Automation Adapter
```

## Regla

Una integración sin contrato no entra en Atlas.
