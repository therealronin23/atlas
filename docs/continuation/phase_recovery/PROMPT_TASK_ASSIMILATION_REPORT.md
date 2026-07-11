# PROMPT_TASK_ASSIMILATION_REPORT — Phase Recovery

Nota metodológica añadida en esta fase: `atlas_fable5_handoff_v1/prompts/
PROMPT_FABLE5_BUILD_ALL.md` define **su propia numeración interna de Fase
0-6**, DISTINTA tanto de `tickets/TICKETS_PHASE_0_TO_4.md` (mismo pack) como
de `atlas_build_pack/docs/atlas-bible/17_PHASES_ROADMAP.md` (Fase 0-7,
pack distinto). Su "Fase 5 — Control Plane real" (Connected Accounts,
Gmail/Claude/WhatsApp/GitHub placeholder connectors, Permission Matrix,
Notification Router, Automation Rules) y "Fase 6 — Improvement Radar"
(docs/atlas-improvement/*, fichas SOTA de OpenHands/LangGraph/MCP/etc.) NO
son las mismas que las Fase 5/6 de `17_PHASES_ROADMAP.md`. Es evidencia
adicional de que la fragmentación de numeración entre packs (y DENTRO de un
mismo pack) es la causa raíz de la confusión de fases — no una fase
inventada del aire, sino tres documentos con la misma intención general y
números que no coinciden entre sí.

## Pack 1 — `atlas_os_build_pack_v1` (→ `docs/handoff/atlas_build_pack/`)

| Fichero | Propósito | ¿Usado? | ¿Ignorado? | ¿Superseded? | ¿Conflicto con dirección actual? | ¿Debería ser NEXT_AI_INSTRUCTIONS? | ¿Parkear? | ¿Definir trabajo faltante? |
|---|---|---|---|---|---|---|---|---|
| `prompts/PROMPT_CLAUDE_CODE_IMPLEMENT.md` | Construir Frontend Shell final-compatible (schemas→simulator→Tauri+React shell→bridge) | Sí, parcialmente (schemas+simulator+shell reales, Vite en vez de Tauri) | No | No | No | No — ya obsoleto una vez ejecutado F0-F4 | Sí (histórico) | No |
| `prompts/PROMPT_FABLE5_ATLAS_BUILD.md` | Prompt maestro alternativo, mismo objetivo con más detalle (Paso 1-6) | Sí, parcialmente (mismo patrón) | No | No | No | No | Sí | No |
| `prompts/PROMPT_CODEX_IMPLEMENT.md` | Versión corta para Codex, mismo objetivo | Redundante con los 2 anteriores — no hay evidencia de que se usara específicamente | Sí (redundante) | No | No | No | Sí | No |
| `tickets/EPICS_AND_TASKS.md` | Epic 1-6 sin numeración de fase | Parcial (Epic 1-4 sí, Epic 5-6 no — ver Coverage Matrix) | Parcial | No | No | No | Sí (histórico) | **Sí — Epic 5 (Visual Orchestrator) y Epic 6 (Governance, cubierto parcialmente por Security Center) definen trabajo real pendiente/parcial** |
| `docs/atlas-bible/17_PHASES_ROADMAP.md` | Fase 0-7 con entregables y gate por fase | Parcial (F0-F4 y parte de F7 sí; F5-F6 no) | Parcial | No | No | No | Sí (histórico) para F0-4/F7; **F5/F6 necesitan un ADR de parking explícito, no solo "ignorar"** | **Sí — es la fuente MÁS específica de lo que falta** |
| `docs/atlas-bible/00-16 (resto)` (Manifesto, Non-Goals, Event Canon, Visual/Motion Grammar, Frontend Architecture, Backend Bridge, Territories, Memory+Continuity, Harness Adapter Contract, Governance Gates, Graph Rendering, Tech Stack, Framework Boundaries, ADR Index) | Contexto/principios de diseño | Sí, como contexto absorbido en decisiones reales (p.ej. AGENTS.md invariantes, ADR-058/059) | No | Parcial — varias decisiones técnicas (Tauri, React Flow para grafo) fueron sustituidas explícitamente por ADR-059 (Vite/d3-force) | No | No | Sí (histórico) | No |
| `README.md` | Instrucciones de uso del pack | Sí (una vez, al ingerir) | No | No | No | No | Sí (histórico) | No |

## Pack 2 — `atlas_fable5_handoff_v1`

| Fichero | Propósito | ¿Usado? | ¿Ignorado? | ¿Superseded? | ¿Conflicto? | ¿NEXT_AI_INSTRUCTIONS? | ¿Parkear? | ¿Define trabajo faltante? |
|---|---|---|---|---|---|---|---|---|
| `tickets/TICKETS_PHASE_0_TO_4.md` | Phase 0-4 con checklist concreto | **Sí, la fuente MÁS seguida** — coincide 1:1 con el trabajo real F0-F4 | No | No | No | No, ya cerrado | Sí (histórico, cumplido) | No |
| `docs/ARCHITECTURE_MAP.md`, `BACKEND_ADVANCEMENT_SPEC.md`, `CONTINUATION_PROTOCOL.md`, `IMPROVEMENT_DOCTRINE.md`, `QUALITY_GATES.md`, `UIUX_FINAL_SPEC.md`, `SOTA_RESEARCH_PROTOCOL.md` | Specs de apoyo | Sí, como contexto de diseño | No | Parcial | No | No | Sí (histórico) | No |
| `prompts/PROMPT_FABLE5_BUILD_ALL.md` | Prompt maestro con SU PROPIA Fase 0-6 (ver nota metodológica arriba) | Parcialmente — F0-4 de este prompt SÍ se hicieron (auditoría, docs/schemas, Event Kernel, bridge, UI); **"Fase 5 — Control Plane real" y "Fase 6 — Improvement Radar" de ESTE prompt NO se hicieron como unidad propia**, aunque partes de su contenido reaparecen dispersas: Security Center (F7-9) cubre algo de Permission Matrix; el lazo de auto-mejora del núcleo (preexistente, no de este pack) cubre parte del espíritu de "Improvement Radar" sin ser el mismo entregable (`docs/atlas-improvement/*` con fichas SOTA de OpenHands/LangGraph/MCP nunca se escribió) | No | No | No | No | Sí (histórico) para 0-4; **F5/F6 de este prompt son trabajo faltante adicional, distinto del F5/F6 del pack 1** |
| `prompts/PROMPT_WEAKER_AI_CONTINUE.md` | Instrucciones de continuidad para IA más débil | Sí, en espíritu (la disciplina de leer CONTINUATION_STATE antes de tocar código es la práctica real de cada sesión) | No | No | No | **Sí, en esencia — ya lo es informalmente** | No | No |
| `templates/*.md` (3) | Plantillas ADR/research/connector | Sí — `docs/decisions/adr/` sigue la convención de plantilla | No | No | No | No | Sí (histórico) | No |
| `README_USE_THIS_FIRST.md` | Orden de lectura | Sí | No | No | No | No | Sí (histórico) | No |

## Pack 3 — `atlas_product_os_liquid_ui_pack_v1`

| Fichero | Propósito | ¿Usado? | ¿Ignorado? | ¿Superseded? | ¿Conflicto? | ¿NEXT_AI_INSTRUCTIONS? | ¿Parkear? | ¿Define trabajo faltante? |
|---|---|---|---|---|---|---|---|---|
| `PROMPT_FABLE_PHASE_15.md` | Prompt de la Fase 15 real | Sí, ejecutado íntegramente (con huecos honestos) | No | No | No | No, ya cerrado | Sí (histórico, cumplido) | Los huecos ya están en `RECOMMENDED_PHASE_16.md` (F16, ya cerrado) |
| `PROMPT_CONTINUATION_FOR_WEAKER_AI.md` | Orden de lectura para continuar | Sí, en espíritu | No | No | No | Sí, en esencia | No | No |
| `tasks/FABLE_EXECUTION_ORDER.md` | Orden de 14 pasos de ejecución | Sí, seguido de cerca (auditoría→REPO_ALIGNMENT_REPORT→marcar UI como arnés→scaffolds seguros→Business Core contracts→Gestoría demo simulada→UI quality gate→security fixtures→continuación) | No | No | No | No | Sí (histórico, cumplido) | No |
| `tasks/ACCEPTANCE_CRITERIA.md` | Criterios de aceptación de F15 | Sí — la auditoría 2026-07-11 previa a esta sesión verificó explícitamente los 18 fixtures de seguridad y el criterio #7 (crm bulk export gate) que faltaban | No | No | No | No | Sí (histórico) | No |
| `tasks/DO_NOT_DO.md` | 15 prohibiciones explícitas | **Sí — respetadas activamente**: ningún filing real, ningún envío silencioso, WhatsApp personal bloqueado estructuralmente (F16-8), sin certificados, sin computer-use como ruta primera | No | No | No | **Sí — debería seguir citándose en cada fase futura, es la lista de guardarraíles más concreta de las 3 packs** | No | No |
| `tasks/GAP_DETECTION_REGISTER.md` | 15 gaps conocidos a vigilar | Parcial — gap #8 (Legal/ToS registry per platform) YA se cerró (F16-7); el resto (org onboarding, multi-user roles, data residency, offline queues, backup/restore, notification routing multi-canal, cost/latency/privacy dashboard, evaluation harness, performance model UI nativa, sync conflict resolution, community connector trust, migración Business Core desde Excel, validación regulatoria por sector, expansión de dataset) siguen abiertos y NO bloquean nada de F15/F16 | No | No | No | No | **Sí — es un backlog de producto útil para F17+, no para esta sesión** | Sí (los 14 restantes) | Define trabajo de producto futuro, no de recuperación de fases |
| `tasks/CONTINUOUS_IMPROVEMENT_PROTOCOL.md` | Mandato de identificar ≥10 debilidades antes de cerrar fase | Sí — el patrón de auto-auditoría (usado en el cierre de F15 el 2026-07-11: 3 defectos reales cazados) sigue este protocolo | No | No | No | Sí, en esencia | No | No |
| `tasks/PHASE_15_TASKS.md` | Desglose de tareas de F15 | Sí, ejecutado | No | No | No | No, cerrado | Sí (histórico) | No |
| `context/{DECISION_INDEX,WHAT_WE_KEEP_FROM_FABLE,WHAT_WE_REJECT_FROM_FABLE,CHAT_DECISIONS_SINCE_LAST_ZIP,FABLE_LAST_OUTPUT_ANALYSIS}.md` | Revisión explícita del output previo antes de escribir el pack 3 | Sí — es la evidencia central de que "Phase 15" fue una continuación deliberada, no un salto ciego (ver `PACK_LOCATION_REPORT.md`) | No | No | No | No | Sí (histórico, valor probatorio permanente) | No |
| `MANIFEST.md` | Índice del pack | Sí | No | No | No | No | Sí (histórico) | No |
| Resto (`product/`, `research/`, `sectors/`, `design/`, `backend/`, `schemas/`, `adr/`, `continuation/`, `fixtures/`) | Specs detalladas por dominio | Parcial — ~26/85 schemas, ~20/74 motores backend, 5/22 sectores, 0/51 diseños UI implementados (todos documentados honestamente en `WHAT_WAS_NOT_IMPLEMENTED.md` y en los 3 manifiestos de Fase 2 de esta auditoría) | Parcial (documentado, no silenciado) | No | No | No | Sí para lo no implementado (candidatos F17+) | Ya cubierto en `PHASE_1_16_COVERAGE_MATRIX.md` y en `WHAT_WAS_NOT_IMPLEMENTED.md` |

## Veredicto de esta fase

Ningún prompt/tarea de los 3 packs fue silenciosamente descartado sin
rastro. Todo lo NO ejecutado está documentado en al menos un lugar (esta
auditoría, `WHAT_WAS_NOT_IMPLEMENTED.md`, o `GAP_DETECTION_REGISTER.md` del
propio pack). El único hallazgo accionable de esta fase es el mismo de la
Fase 3/4: **F5/F6 de `17_PHASES_ROADMAP.md`** necesitan un cierre formal
(ADR de parking), no descubrimiento — ya se sabía que no existían, faltaba
decidir y registrar qué hacer con ellas.
