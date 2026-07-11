# ARCHITECTURE_MAP — Atlas OS sobre atlas-core

Mapa de las capas objetivo del OS a los módulos REALES del repo. Regla: cada
capa OS o reusa un módulo existente o declara el nuevo con su boundary. Nada
"flota" sin dueño.

```text
Atlas OS
├─ Cognitive Surface + Control Plane (UI)  → ui/atlas-shell/  [NUEVO, ADR-059]
│    dominio en ui/atlas-shell/src/core/ (event store/reducer/projector TS)
│    React solo renderiza; sin reglas de negocio en componentes
│
├─ Event Kernel                            → src/atlas/events/  [NUEVO, ADR-058]
│    canon: schemas/event.schema.json + events/schemas.py (pydantic)
│    store+replay: events/store.py (JSONL en workspace/os_events/)
│    bridge: events/core_bridge.py — SUSCRIPTOR de core/event_bus.py [EXISTENTE]
│    simulador: events/player.py — reproduce fixtures/events/*.jsonl
│
├─ Backend Bridge                          → src/atlas/api/  [NUEVO, ADR-058]
│    FastAPI 127.0.0.1:7341, read-only sobre core, WS /events
│    convive con interfaces/dashboard.py (7331) y exec_api.py [EXISTENTES]
│
├─ Execution Kernel                        → core/orchestrator.py + InferenceHub
│    [EXISTENTE — no se toca en v1; el OS lo REPRESENTA vía eventos]
│
├─ Memory OS                               → memory/ [EXISTENTE, ADR-057:
│    Sqlite=registro/retrieval, Kuzu=nicho GateD, BlockMemory=core memory]
│    el OS añade solo lectura/representación + import de conversaciones
│    externas (Fase 8) que ESCRIBE por las rutas canónicas existentes
│
├─ Governance Kernel                       → governance/ + config/governance.json
│    [EXISTENTE e INTOCABLE por agentes] + gates + CapabilityIssuer
│    el OS añade: permission evaluator de LECTURA para la UI + eventos
│    approval.required/granted/denied proyectados
│
├─ Auditoría                               → transparency/ (Merkle) [EXISTENTE]
│    autoridad de auditoría; el event store OS es autoridad de representación
│
├─ Capability/Integration Fabric           → mcp/ + tools/ + catálogo del trunk
│    [EXISTENTE: MCP trunk con sectores/routing] + schemas/connector.schema.json
│    [NUEVO]: specs de conectores con credential_reference, mock-first
│
├─ Easy Connection Layer + PolicyEngine    → src/atlas/fabric/  [NUEVO, ADR-060,
│    Fase 15] Connection Ladder (12 peldaños, API-first), RecipeEngine/
│    PackEngine fail-closed, ConnectionConcierge, AuthBroker (solo
│    referencias), ConnectorRegistry (rug-pull), PolicyEngine (7
│    invariantes duros en código, envuelve — no duplica — el evaluador v1
│    de Governance Kernel arriba)
│
├─ Atlas Business Core + Question Engine   → src/atlas/business/  [NUEVO,
│    ADR-061, Fase 15] CRM/ERP nativo draft-first (un solo store, vistas
│    CRM/ERP), AdaptiveQuestionEngine (lazo pregunta→interpreta→confirma),
│    LegacyLinkLayer (canonicidad explícita, sync off por defecto)
│
└─ Improvement Engine                      → lab/ + research pipeline
     [EXISTENTE: TopicExpander + research_digest → candidatos de catálogo +
     triage/ingesta] — docs/improvement/ lo documenta, no lo duplica
```

## Los tres planos (separación crítica del pack, confirmada)

```text
Domain  = src/atlas/** (Python, ya existente + events/ + api/)
Event   = schemas/*.json (contrato neutro, versionado)
Render  = ui/atlas-shell (TS/React, sustituible; Tauri futuro)
```

## Puertos locales

| Puerto | Qué | Estado |
| --- | --- | --- |
| 7331 | dashboard Jinja2 existente | EXISTENTE |
| 7341 | Atlas OS bridge (API + WS) | NUEVO |
| 5173 | vite dev de la shell | NUEVO (solo dev) |
