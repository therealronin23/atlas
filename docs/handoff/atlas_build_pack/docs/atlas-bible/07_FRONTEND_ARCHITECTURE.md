# 07 — Arquitectura Frontend

## Decisión

Frontend Shell v1: Tauri + React + TypeScript.

Motivo: permite construir rápido una UI avanzada con grafos, Monaco, timeline, paneles, React Flow, Cytoscape/Sigma y WebSocket. No significa que Atlas dependa de React.

## Capas

```text
ui/atlas-shell/
├── src/
│   ├── core/
│   │   ├── event-store.ts
│   │   ├── event-reducer.ts
│   │   ├── visual-state-machine.ts
│   │   ├── graph-projector.ts
│   │   ├── simulator-client.ts
│   │   └── backend-event-client.ts
│   ├── components/
│   │   ├── universal-bar/
│   │   ├── living-graph/
│   │   ├── execution-pipeline/
│   │   ├── timeline/
│   │   ├── reality-panel/
│   │   ├── inspector/
│   │   └── layout/
│   ├── territories/
│   │   ├── command-center/
│   │   ├── coding/
│   │   ├── research/
│   │   ├── memory/
│   │   ├── orchestrator/
│   │   ├── audit/
│   │   ├── bond/
│   │   └── connected-accounts/
│   ├── design/
│   │   ├── tokens.ts
│   │   ├── colors.ts
│   │   ├── motion.ts
│   │   └── typography.ts
│   └── adapters/
│       ├── renderer-adapter.ts
│       └── tauri-bridge.ts
```

## Reglas

- React no contiene reglas de negocio.
- Los componentes consumen estado visual derivado de eventos.
- El simulador y backend real implementan la misma interfaz.
- El renderer debe poder sustituirse en el futuro.
- El primer shell debe ser final-compatible, no demo fake.

## Vistas iniciales

```text
Command Center
Living Knowledge Graph
Execution Pipeline
Timeline
Reality Status
Universal Bar
Context Inspector
```
