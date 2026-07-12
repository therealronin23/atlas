# 04 — Event Canon

El Event Canon es la sangre de Atlas. Toda la UI, la auditoría, el replay y el bridge con backend dependen de él.

## Evento base

```json
{
  "id": "evt_001",
  "type": "step.started",
  "timestamp": "2026-07-10T00:00:00Z",
  "schema_version": "1.0",
  "source": "atlas.kernel",
  "workspace_id": "ws_default",
  "intent_id": "int_001",
  "process_id": "proc_001",
  "actor": "memory",
  "summary": "Buscando contexto relevante",
  "status": "running",
  "risk": "low",
  "confidence": 0.91,
  "visible": true,
  "payload": {},
  "audit": {
    "merkle_hash": null,
    "previous_hash": null
  }
}
```

## Tipos mínimos

```text
system.started
system.health.updated

intent.created
intent.classified
intent.cancelled

context.loaded
context.missing

plan.created
plan.modified
plan.approved
plan.rejected

step.started
step.paused
step.completed
step.failed

tool.called
tool.finished
tool.failed

adapter.connected
adapter.failed
adapter.permission_required

artifact.created
artifact.modified
artifact.deleted

memory.searched
memory.updated
memory.created
memory.conflict_detected

graph.node.created
graph.node.updated
graph.edge.created
graph.edge.updated

approval.required
approval.granted
approval.denied

audit.logged
snapshot.created
snapshot.reverted

error.raised
error.resolved
```

## Estados

```text
idle
queued
running
waiting_user
blocked
completed
failed
cancelled
```

## Riesgo

```text
none
low
medium
high
critical
```

## Confianza

Número entre 0 y 1.

- 0.00-0.39: baja
- 0.40-0.69: media
- 0.70-0.89: alta
- 0.90-1.00: muy alta

## Regla

Si algo cambia en Atlas y no genera evento, para la UI y la auditoría no existe.
