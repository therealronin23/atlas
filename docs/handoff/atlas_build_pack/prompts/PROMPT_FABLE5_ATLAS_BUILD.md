# Prompt maestro para Fable 5 / agente constructor

Vas a construir Atlas OS usando este repositorio y los documentos canónicos incluidos en `docs/atlas-bible/`.

## Identidad

Atlas OS no es un chatbot, no es un dashboard, no es un clon de Cursor, no es un clon de n8n, no es Obsidian y no es un wrapper de herramientas de IA.

Atlas OS es un entorno operativo cognitivo soberano donde conocimiento, memoria, ejecución, herramientas, procesos, artefactos, usuario y auditoría se representan como estado vivo.

## Objetivo

Construir la versión inicial más cercana posible a la visión final, no un prototipo desechable.

Debes implementar una arquitectura final-compatible:

```text
Event Canon
↓
Graph Projection
↓
Reality Simulator
↓
Frontend Shell
↓
Backend Bridge
↓
Atlas Core Integration
```

## Lee primero

1. `docs/atlas-bible/00_MANIFESTO.md`
2. `docs/atlas-bible/01_NON_GOALS.md`
3. `docs/atlas-bible/02_ARCHITECTURE_MAP.md`
4. `docs/atlas-bible/04_EVENT_CANON.md`
5. `docs/atlas-bible/07_FRONTEND_ARCHITECTURE.md`
6. `docs/atlas-bible/08_BACKEND_BRIDGE.md`
7. `docs/atlas-bible/12_GOVERNANCE_GATES.md`
8. `docs/atlas-bible/17_PHASES_ROADMAP.md`
9. `docs/atlas-bible/18_ACCEPTANCE_CRITERIA.md`

## Implementación esperada

### Paso 1 — Validar contratos

Crea o verifica:

```text
schemas/event.schema.json
schemas/node.schema.json
schemas/edge.schema.json
schemas/adapter.schema.json
fixtures/events/*.jsonl
fixtures/graph/initial_graph.json
```

No cambies schemas sin actualizar docs y fixtures.

### Paso 2 — Crear Atlas Shell

Usa:

```text
Tauri + React + TypeScript
```

Crea:

```text
ui/atlas-shell/src/core/event-store.ts
ui/atlas-shell/src/core/event-reducer.ts
ui/atlas-shell/src/core/graph-projector.ts
ui/atlas-shell/src/core/visual-state-machine.ts
ui/atlas-shell/src/core/simulator-client.ts
```

### Paso 3 — Crear componentes principales

```text
LivingKnowledgeGraph
UniversalBar
ExecutionPipeline
Timeline
RealityPanel
ContextInspector
CommandCenter
```

### Paso 4 — Cargar simulator

La UI debe poder reproducir:

```text
fixtures/events/demo_first_run.jsonl
fixtures/events/demo_coding_task.jsonl
fixtures/events/demo_import_conversation.jsonl
fixtures/events/demo_error_and_recovery.jsonl
```

### Paso 5 — Bridge backend mínimo

Crear:

```text
src/atlas/api/server.py
src/atlas/api/events.py
src/atlas/api/cli_bridge.py
src/atlas/api/graph_projection.py
```

Endpoints:

```text
GET /health
GET /graph
POST /intent
WS /events
```

### Paso 6 — Conectar mínimo a Atlas Core

Conectar:

```text
atlas reality
atlas memory
atlas task --dry-run
```

## Restricciones

- No hagas home basada en chat.
- No pongas Visual Orchestrator como home.
- No acoples React a dominio Atlas.
- No uses LangGraph como kernel.
- No integres herramientas externas de golpe.
- No ocultes la ejecución detrás de spinners.
- No construyas pantallas sin eventos.
- No uses datos fake donde ya exista fixture/evento.

## Criterio de finalización

Debe poder grabarse una demo de 60-90 segundos:

1. Abrir Atlas Shell.
2. Ver Living Knowledge Graph.
3. Escribir intención.
4. Ver eventos en Timeline.
5. Ver Execution Pipeline.
6. Ver cambios en el grafo.
7. Abrir un nodo.
8. Ver audit.logged.

## Mejora de visión permitida

Puedes mejorar la visión inicial si respetas estos principios:

- Más claridad sin perder ambición.
- Más trazabilidad sin saturar.
- Más belleza si está ligada a estado real.
- Mejor arquitectura si mantiene Event Canon.
- Mejor UX si mantiene Living Graph como home.

Si una mejora convierte Atlas en chat, dashboard, n8n o Cursor, recházala.
