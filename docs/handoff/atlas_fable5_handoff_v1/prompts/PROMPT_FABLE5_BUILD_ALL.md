# PROMPT MAESTRO PARA FABLE 5 — CONSTRUIR ATLAS OS

Actúa como arquitecto principal, investigador SOTA, diseñador UI/UX senior y agente de implementación full-stack para Atlas OS.

No estás construyendo un prototipo desechable. Estás construyendo una primera versión final-compatible: pequeña si hace falta, pero con arquitectura correcta, contratos claros, documentación fuerte y continuidad para que una IA menos potente pueda continuar después.

## 0. Contexto esencial

Atlas OS no es un chatbot, no es un dashboard, no es un IDE, no es un clon de n8n, no es un wrapper de Claude/Cursor/Codex.

Atlas OS es un entorno cognitivo soberano que convierte intención, memoria, herramientas, agentes, conocimiento, ejecución, decisiones, cuentas conectadas, historial externo y auditoría en un sistema operativo vivo, extensible y gobernable.

La UI anterior basada en Living Knowledge Graph, Execution Pipeline, Timeline y Universal Bar sigue siendo válida, pero ahora debe completarse con un Control Plane real: integraciones, cuentas, permisos, configuración, personalización, modelos, notificaciones, automatizaciones, seguridad, import/export y developer mode.

## 1. Principios no negociables

1. No construir un prototipo bonito sin contratos de datos.
2. No poner el chat como centro del producto.
3. No usar LangGraph, CrewAI, React Flow, MCP, A2A, AG-UI, OpenHands, Cursor o n8n como núcleo de Atlas.
4. Usar frameworks externos solo como backends, adapters, inspiración o módulos envueltos.
5. Todo lo externo entra por un Adapter Contract o Connector Contract.
6. Todo evento relevante debe emitirse como AtlasEvent.
7. Toda acción con riesgo debe pasar por Gate.
8. Toda capacidad externa debe tener permisos, riesgo, alcance, audit log y revocación.
9. Toda decisión arquitectónica debe quedar en ADR.
10. Toda incertidumbre importante debe investigarse en internet antes de decidir.
11. Toda investigación debe dejar source digest, fecha, enlace y conclusión.
12. Todo avance debe actualizar `CONTINUATION_STATE.md`.
13. Cada fase debe dejar tests, smoke tests o fixtures suficientes.
14. Diseña para que una IA menos potente pueda continuar leyendo docs y tickets.

## 2. Cuando dudes

Si dudas sobre APIs, SDKs, repos, licencias, SOTA, seguridad, protocolos, patrones de UI o frameworks:

- Busca en internet.
- Prioriza fuentes oficiales, repos, papers, documentación técnica y issues relevantes.
- No inventes capacidades de productos.
- Si algo es legal/ToS dudoso, marca `RISK: legal/tos` y no lo conviertas en dependencia nuclear.
- Resume lo encontrado en `docs/research/YYYY-MM-DD_<tema>.md`.
- Si una decisión cambia la arquitectura, crea un ADR.

## 3. Objetivo de construcción

Construir la base de Atlas OS con dos grandes caras:

### A. Cognitive Surface

- Home con Living Knowledge Graph.
- Universal Bar.
- Execution Pipeline.
- Timeline/Audit Timeline.
- Memory Vault.
- Artifacts.
- Visual Orchestrator como territorio, no como home.
- Research Territory.
- Coding Territory.
- Audit Territory.

### B. Control Plane

- Atlas Control Center.
- Integration Fabric.
- Accounts & Identity.
- Permissions & Gates.
- Personalization.
- Notification Router.
- Automation Rules.
- Model & Provider Router.
- Security Center.
- Backup / Export / Portability.
- Developer Console.

## 4. Arquitectura conceptual esperada

Implementa y documenta la siguiente arquitectura:

```text
Atlas OS
├─ Cognitive Kernel
├─ Event Kernel
├─ Memory OS
├─ Execution Kernel
├─ Governance Kernel
├─ Capability Fabric
├─ Agent Society Layer
├─ Integration Fabric
├─ Control Plane
├─ Visual Representation Layer
├─ Simulation / Replay Lab
└─ Improvement Radar
```

## 5. Orden de trabajo obligatorio

### Fase 0 — Auditoría del repo existente

1. Inspecciona el repo completo.
2. Resume qué existe realmente.
3. Identifica CLI, memory, orchestrator, MerkleLogger, gates, tests, docs, APIs, scripts, observability.
4. Crea `docs/atlas-current-state/REPO_AUDIT.md`.
5. No reescribas lo que ya funcione.

### Fase 1 — Constitución y contratos

Crea o actualiza:

```text
docs/atlas-master/00_CONSTITUTION.md
docs/atlas-master/01_VISION_NO_CEILING.md
docs/atlas-master/02_NON_GOALS.md
docs/atlas-master/03_ARCHITECTURE_MAP.md
docs/atlas-master/04_KERNELS.md
docs/atlas-master/05_EVENT_CANON.md
docs/atlas-master/06_MEMORY_OS.md
docs/atlas-master/07_CAPABILITY_FABRIC.md
docs/atlas-master/08_GOVERNANCE_KERNEL.md
docs/atlas-master/09_CONTROL_PLANE.md
docs/atlas-master/10_VISUAL_SYSTEM.md
```

Crea o actualiza schemas:

```text
schemas/event.schema.json
schemas/node.schema.json
schemas/edge.schema.json
schemas/memory.schema.json
schemas/capability.schema.json
schemas/connector.schema.json
schemas/permission.schema.json
schemas/gate.schema.json
schemas/policy.schema.json
schemas/adapter.schema.json
schemas/account.schema.json
schemas/automation_rule.schema.json
schemas/notification_rule.schema.json
schemas/artifact.schema.json
schemas/decision.schema.json
schemas/replay.schema.json
```

### Fase 2 — Event Kernel + Simulator

Construye un sistema mínimo que pueda:

- Emitir AtlasEvents.
- Reproducir fixtures `.jsonl`.
- Reducir eventos a WorldState.
- Proyectar WorldState a nodos/aristas del Living Graph.
- Alimentar Pipeline y Timeline.

Crea fixtures:

```text
fixtures/events/demo_first_run.jsonl
fixtures/events/demo_coding_task.jsonl
fixtures/events/demo_research_task.jsonl
fixtures/events/demo_import_conversation.jsonl
fixtures/events/demo_gmail_sync.jsonl
fixtures/events/demo_connector_permission_gate.jsonl
fixtures/events/demo_error_recovery.jsonl
fixtures/graph/initial_graph.json
```

### Fase 3 — Backend Bridge

No reescribas el backend. Expón lo existente.

Crea un backend bridge mínimo:

```text
src/atlas/api/server.py
src/atlas/api/events.py
src/atlas/api/graph_projection.py
src/atlas/api/cli_bridge.py
src/atlas/api/connectors.py
src/atlas/api/permissions.py
```

Endpoints mínimos:

```text
GET  /health
GET  /reality
GET  /graph
GET  /timeline
GET  /connectors
GET  /settings
POST /intent
POST /events/play
POST /connectors/:id/enable
POST /connectors/:id/disable
POST /permissions/evaluate
WS   /events
```

### Fase 4 — UI/UX final-compatible

Stack recomendado salvo razón documentada:

```text
Tauri + React + TypeScript + Tailwind
Graph renderer: React Flow / Cytoscape / Sigma según territorio
Editor: Monaco
Charts: lightweight charting
State: event-store + reducer + selectors
```

Crea estructura:

```text
ui/atlas-shell/
├─ src/
│  ├─ core/
│  │  ├─ event-store.ts
│  │  ├─ event-reducer.ts
│  │  ├─ world-state.ts
│  │  ├─ selectors.ts
│  │  └─ simulator-client.ts
│  ├─ shell/
│  ├─ cognitive-surface/
│  ├─ control-plane/
│  ├─ territories/
│  ├─ components/
│  ├─ design-system/
│  └─ developer-tools/
└─ README.md
```

Pantallas mínimas:

- Home / Living Knowledge Graph.
- Universal Bar.
- Execution Pipeline.
- Timeline.
- Memory Vault.
- Control Center.
- Integration Fabric.
- Connector Detail.
- Permissions Matrix.
- Personalization Settings.
- Security Center.
- Developer Event Inspector.

### Fase 5 — Control Plane real

Implementa los modelos y UI de:

- Connected Accounts.
- Gmail placeholder connector.
- Claude/ChatGPT external intelligence placeholder connector.
- WhatsApp policy placeholder connector.
- GitHub connector placeholder.
- Local Files connector.
- MCP connector registry.
- Permission Matrix.
- Notification Router.
- Automation Rules.
- Memory Privacy Settings.
- Backup/Export.

No hace falta que todas las plataformas funcionen en producción desde el día 1, pero la arquitectura y UX deben soportarlas correctamente.

### Fase 6 — Improvement Radar

Crea:

```text
docs/atlas-improvement/00_IMPROVEMENT_DOCTRINE.md
docs/atlas-improvement/01_SOURCE_TAXONOMY.md
docs/atlas-improvement/02_PRIMITIVE_TAXONOMY.md
docs/atlas-improvement/03_REPO_HUNTING_METHOD.md
docs/atlas-improvement/04_PRODUCT_DISSECTION_METHOD.md
docs/atlas-improvement/05_PAPER_DISSECTION_METHOD.md
docs/atlas-improvement/06_SUPERIORITY_TESTS.md
docs/atlas-improvement/07_OPEN_SOURCE_SHADOW_DOCTRINE.md
docs/atlas-improvement/08_SURGICAL_FORK_POLICY.md
docs/atlas-improvement/09_SOTA_REGISTRY.md
```

Incluye primeras fichas:

- NotebookLM / notebooklm-py.
- OpenHands.
- LangGraph.
- MCP.
- AG-UI.
- A2A.
- n8n.
- Cursor.
- Claude Code.
- GraphRAG.
- Mem0 / MemGPT / Zep.

Cada ficha debe responder:

```text
Qué problema resuelve.
Qué primitiva contiene.
Dónde falla.
Cómo lo reconstruye Atlas.
Cómo demostramos que Atlas lo mejora.
Si se observa, envuelve, forkea, nativiza o rechaza.
```

## 6. Documentación para continuidad

Crea y mantén siempre:

```text
CONTINUATION_STATE.md
NEXT_AI_INSTRUCTIONS.md
ARCHITECTURE_DECISIONS_INDEX.md
OPEN_QUESTIONS.md
KNOWN_RISKS.md
IMPLEMENTATION_LOG.md
TESTING_STATUS.md
```

`CONTINUATION_STATE.md` debe incluir:

- Qué se hizo.
- Qué falta.
- Qué archivos tocar.
- Cómo correr el proyecto.
- Cómo correr tests.
- Qué decisiones no deben revertirse.
- Qué dudas requieren investigación web.
- Próximo ticket exacto.

## 7. Calidad mínima aceptable

No termines hasta que exista:

- Repo auditado.
- Docs maestras creadas.
- Schemas creados.
- Fixtures creados.
- Simulator funcionando.
- UI Shell renderizando eventos.
- Cognitive Surface básica funcional.
- Control Plane básico navegable.
- Backend bridge mínimo.
- Tests/smoke tests.
- Continuation docs.
- ADRs.
- Lista de próximos tickets.

## 8. Criterio de demo real

Debe poder grabarse un vídeo de 90 segundos:

1. Abrir Atlas.
2. Ver Living Knowledge Graph.
3. Abrir Control Center.
4. Ver Integration Fabric.
5. Simular conectar Gmail o External AI Account.
6. Escribir una intención en Universal Bar.
7. Ver Execution Pipeline.
8. Ver eventos en Timeline.
9. Ver un Gate de permisos.
10. Ver Memory Vault actualizarse.
11. Abrir Developer Event Inspector.

Si no se puede hacer esto, no está listo.

## 9. Estilo de ejecución

Trabaja por commits pequeños o cambios agrupados lógicamente.
No mezcles 20 cosas sin documentar.
No inventes si puedes verificar.
No sacrifiques arquitectura por velocidad aparente.
Prioriza una base que pueda crecer durante años.
