# 08 — Backend Bridge

## Objetivo

Conectar el Atlas Frontend Shell al Atlas Core existente sin reescribir el backend.

## Bridge mínimo

```text
src/atlas/api/
├── server.py
├── events.py
├── graph_projection.py
├── cli_bridge.py
├── schemas.py
└── simulator.py
```

## Endpoints mínimos

```text
GET  /health
GET  /graph
GET  /timeline
POST /intent
GET  /memory/summary
WS   /events
```

## CLI bridge inicial

Conectar solo:

```text
atlas reality
atlas memory
atlas task --dry-run
```

## Flujo POST /intent

```text
User intent
↓
intent.created
↓
intent.classified
↓
plan.created
↓
step.started
↓
memory.searched
↓
tool.called or simulated
↓
artifact.created
↓
memory.updated
↓
audit.logged
```

## Regla

El backend real puede llegar poco a poco. La UI no debe esperar a que todo el backend esté terminado para comportarse correctamente.
