# 02 — Mapa de Arquitectura

## Vista global

```text
┌────────────────────────────────────────────────────────────────┐
│                         Atlas OS                               │
├────────────────────────────────────────────────────────────────┤
│ Adaptive Interface Layer                                       │
│ - Living Knowledge Graph                                       │
│ - Universal Bar                                                │
│ - Execution Pipeline                                           │
│ - Timeline                                                     │
│ - Territories                                                  │
├────────────────────────────────────────────────────────────────┤
│ Visual State Machine                                           │
│ - Event reducer                                                │
│ - Graph projector                                              │
│ - Motion semantics                                             │
│ - Territory router                                             │
├────────────────────────────────────────────────────────────────┤
│ Event Kernel                                                   │
│ - Event Canon                                                  │
│ - Event Store                                                  │
│ - Streaming bridge                                             │
│ - Replay                                                       │
├────────────────────────────────────────────────────────────────┤
│ Cognitive Kernel                                               │
│ - Intent classifier                                            │
│ - Context loader                                               │
│ - Planner                                                      │
│ - Router                                                       │
│ - Governance checks                                            │
├────────────────────────────────────────────────────────────────┤
│ Execution Harness Layer                                        │
│ - Agent loop                                                   │
│ - Tool execution                                               │
│ - Adapters                                                     │
│ - LangGraph/CrewAI optional backends                           │
│ - Human approval                                               │
├────────────────────────────────────────────────────────────────┤
│ Living Knowledge System                                        │
│ - Memory Vault                                                 │
│ - Knowledge Graph                                              │
│ - Conversation import                                          │
│ - Pattern extraction                                           │
│ - Provenance                                                   │
├────────────────────────────────────────────────────────────────┤
│ Governance + Audit                                             │
│ - Gates                                                        │
│ - Risk profiles                                                │
│ - Capability tokens                                            │
│ - MerkleLogger                                                 │
│ - Snapshot/replay/rollback                                     │
├────────────────────────────────────────────────────────────────┤
│ Atlas Core / Existing Backend                                  │
│ - Orchestrator                                                 │
│ - Gates                                                        │
│ - GhostReplay                                                  │
│ - MerkleLogger                                                 │
│ - Memory Vault                                                 │
│ - InferenceHub                                                 │
│ - CLI                                                         │
│ - Observability/Prometheus                                     │
└────────────────────────────────────────────────────────────────┘
```

## Separación crítica

Atlas debe tener tres capas claramente separadas:

```text
Domain Layer      = qué es Atlas
Event Layer       = cómo se comunica Atlas
Renderer Layer    = cómo se ve Atlas
```

React, Tauri, Slint, WebGL o cualquier renderer no deben contener reglas de negocio. Solo renderizan el estado derivado de eventos.

## Home real

La home final-compatible es:

```text
Command Center
├─ Living Knowledge Graph
├─ OS Navigation
├─ Reality Status
├─ Universal Bar
└─ Timeline
```

## Territorios

```text
Home / Command Center     → estado general vivo
Coding Territory          → código, diffs, tests, blast radius
Research Territory        → fuentes, hipótesis, contradicciones, síntesis
Memory Territory          → conocimiento, patrones, recuerdos, importaciones
Visual Orchestrator       → flujos tipo n8n/LangGraph, pero propio
Audit Territory           → Merkle logs, replay, decisiones
Bond Territory            → conversación humana profunda, no product-centric
Connected Accounts        → importación y análisis de historial externo
```
