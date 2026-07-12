# 20 — Implementation Map

## Estructura propuesta del repo

```text
atlas/
├── docs/
│   └── atlas-bible/
├── schemas/
├── fixtures/
│   ├── events/
│   └── graph/
├── src/
│   └── atlas/
│       ├── api/
│       ├── events/
│       ├── graph/
│       ├── adapters/
│       ├── imports/
│       └── governance/
└── ui/
    └── atlas-shell/
```

## Backend modules

```text
src/atlas/events/event_bus.py
src/atlas/events/event_store.py
src/atlas/events/schemas.py
src/atlas/graph/projector.py
src/atlas/api/server.py
src/atlas/api/websocket.py
src/atlas/api/cli_bridge.py
src/atlas/imports/conversations.py
src/atlas/adapters/base.py
src/atlas/governance/gates.py
```

## Frontend modules

```text
ui/atlas-shell/src/core/event-store.ts
ui/atlas-shell/src/core/event-reducer.ts
ui/atlas-shell/src/core/graph-projector.ts
ui/atlas-shell/src/core/visual-state-machine.ts
ui/atlas-shell/src/components/living-graph/LivingGraph.tsx
ui/atlas-shell/src/components/execution-pipeline/ExecutionPipeline.tsx
ui/atlas-shell/src/components/universal-bar/UniversalBar.tsx
ui/atlas-shell/src/components/timeline/Timeline.tsx
ui/atlas-shell/src/territories/command-center/CommandCenter.tsx
```

## First implementation command for an agent

1. Create docs/schemas/fixtures exactly.
2. Build simulator.
3. Build UI shell consuming simulator.
4. Add backend bridge.
5. Replace simulator source with backend source.
