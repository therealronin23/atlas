# 17 — Fases de Implementación

## Fase 0 — Canonical Build Pack

Duración: 1-2 días.

Entregables:

```text
Manifesto
Non Goals
Event Canon
Graph Schema
Adapter Contract
Gates
ADR index
Build prompt
```

Gate: los documentos existen y no se contradicen.

## Fase 1 — Contracts + Simulator

Duración: 2-4 días.

Entregables:

```text
schemas/event.schema.json
schemas/node.schema.json
schemas/edge.schema.json
schemas/adapter.schema.json
fixtures/events/*.jsonl
fixtures/graph/initial_graph.json
```

Gate: el simulador puede reproducir eventos y actualizar estado.

## Fase 2 — Frontend Shell final-compatible

Duración: 1-2 semanas.

Entregables:

```text
Tauri + React shell
Living Knowledge Graph
Universal Bar
Execution Pipeline
Timeline
Reality Status
Event Store
Visual State Machine
Simulator Client
```

Gate: UI reacciona a eventos simulados.

## Fase 3 — Backend Bridge

Duración: 1 semana.

Entregables:

```text
FastAPI/WebSocket bridge
GET /health
GET /graph
POST /intent
WS /events
CLI bridge para atlas reality, atlas memory, atlas task --dry-run
```

Gate: UI consume eventos reales mínimos.

## Fase 4 — Memory + Connected Accounts

Duración: 2 semanas.

Entregables:

```text
Manual import de conversaciones
Parser normalizado
Conversation nodes
Pattern extraction
Insights iniciales
Memory Vault visual
```

Gate: importar un export crea nodos, patrones y timeline.

## Fase 5 — Visual Orchestrator Territory

Duración: 2 semanas.

Entregables:

```text
Canvas
Node palette
Inspector
Graph JSON
Graph compiler inicial
Execute/debug visual
```

Gate: flujo visual se ejecuta como eventos.

## Fase 6 — Coding + Research Territories

Duración: 3-4 semanas.

Entregables:

```text
Coding territory con Monaco/diff/tests
Research territory con árbol de preguntas/fuentes/evidencia
```

Gate: tareas reales generen artefactos y memoria.

## Fase 7 — Hardening

Duración: continuo.

Entregables:

```text
Audit replay
Gates completos
Sandbox policies
Failure memory
Performance
Packaging
```

Gate: demo final 60-90 segundos sin datos fake críticos.
