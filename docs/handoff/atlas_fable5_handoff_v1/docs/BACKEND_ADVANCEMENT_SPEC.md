# Atlas OS — Backend Advancement Spec

## Objetivo

Avanzar el backend actual sin romperlo ni reescribirlo.

## Prioridad

1. Exponer realidad existente.
2. Convertir CLI/orchestrator/memory/audit en eventos.
3. Crear API bridge mínimo.
4. Añadir connectors como contratos, no como hacks.
5. Mantener tests y smoke tests.

## Endpoints mínimos

```text
GET  /health
GET  /reality
GET  /graph
GET  /timeline
GET  /memory
GET  /connectors
GET  /settings
POST /intent
POST /events/play
POST /connectors/:id/enable
POST /connectors/:id/disable
POST /permissions/evaluate
WS   /events
```

## Event bridge

Todo output del backend debe poder expresarse como AtlasEvent.

Eventos mínimos:

```text
intent.created
intent.classified
context.loaded
plan.created
step.started
step.finished
tool.called
tool.finished
artifact.created
memory.updated
audit.logged
approval.required
connector.enabled
connector.sync.started
connector.sync.finished
permission.evaluated
error.raised
recovery.started
recovery.finished
```

## Integraciones iniciales

Implementar placeholders seguros primero:

- Gmail connector placeholder.
- External AI Account connector placeholder.
- GitHub connector placeholder.
- WhatsApp policy connector placeholder.
- Local Files connector.
- MCP registry placeholder.

Cada placeholder debe tener schema, UI, permisos, eventos simulados y documentación.

## Regla

No conectar una plataforma real sin:

- Scope mínimo.
- Credencial aislada.
- Revocación.
- Audit log.
- Dry-run.
- Gate para escritura/envío.
