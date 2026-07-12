# ZIP2 CLOSURE — atlas_fable5_handoff_v1.zip

- **Pack path**: `./atlas_fable5_handoff_v1.zip` (16038 bytes, `??` en git).
- **Unpacked path**: `docs/handoff/atlas_fable5_handoff_v1/` (nombre SÍ
  coincide con el ZIP).
- **Propósito original**: handoff de implementación con checklist concreto
  Phase 0-4 (Repo Audit → Master Docs+Schemas → Event Simulator → Backend
  Bridge → UI Shell) + specs de apoyo + protocolo de continuidad para IA
  sucesora.

## Tickets 0-4 status

**IMPLEMENTED — la fuente MÁS seguida de los 3 packs**, coincide 1:1 con el
trabajo real:
- Phase 0 (Repo Audit): `docs/continuation/REPO_AUDIT.md` existe, 8KB,
  cubre stack real, colisiones build-pack↔repo, peligro doble Orchestrator.
- Phase 1 (Master Docs+Schemas): 6/8 tickets explícitos hechos; Constitution
  y Non-goals no están en la ruta `docs/atlas-master/` que este pack
  esperaba — viven en el pack 3 en su lugar (decisión, no omisión). 26
  schemas reales (vs. los propuestos), 60+ ADRs.
- Phase 2 (Event Simulator): `src/atlas/events/store.py` +
  `src/atlas/events/player.py` + `GET /reality` — simulador funciona
  extremo a extremo.
- Phase 3 (Backend Bridge): 7/7 endpoints requeridos + 8 adicionales en
  `src/atlas/api/server.py`.
- Phase 4 (UI Shell): 13 componentes reales en `ui/atlas-shell/src/`,
  todos los 9 nombrados en el ticket + 4 adicionales (MemoryVault,
  RealityPanel, HarnessPanel, SecurityCenter).

## BACKEND_ADVANCEMENT_SPEC status

**PARTIALLY_IMPLEMENTED.** Los 7 endpoints mínimos propuestos existen y el
repo real añade 8 más. Gap real: de los 6 conectores placeholder propuestos
(Gmail, External AI Account, GitHub, WhatsApp, Local Files, MCP registry),
solo Gmail es real (F16-4, gateado por `GMAIL_OAUTH_TOKEN`); el resto sigue
simulado — documentado honestamente, no oculto.

## ARCHITECTURE_MAP status

**READ (referencia, no código verificable directamente).** Describe 10
kernels/capas conceptuales (Cognitive Kernel, Event Kernel, Memory OS,
Execution Kernel, Governance Kernel, Capability Fabric, Integration Fabric,
Agent Society, Visual Representation Layer, Improvement Radar). No es un
entregable de código en sí — es contexto absorbido en `docs/architecture/
ARCHITECTURE_MAP.md` real (3.7KB) y en las decisiones ADR reales.

## UIUX_FINAL_SPEC status

**IMPLEMENTED — pero con matiz importante (ver chequeo especial abajo).**
Los 13 componentes de Cognitive Surface + Control Plane propuestos existen
1:1 en `ui/atlas-shell/src/`, funcionales y sin stubs (verificado línea a
línea en el manifiesto de Fase 2). La regla "Home = Living Graph, no chat"
se cumple.

**Chequeo especial — superseded por D11/arnés**: Sí, explícitamente. Este
documento se llama "FINAL_SPEC" y prometía la UX definitiva del producto.
La decisión D11 de Fase 15 ("el shell actual es arnés de validación, no la
UX final del producto") **supersede la palabra "FINAL" de este spec**,
aunque no su contenido — el arnés real implementa fielmente lo que este
spec describe, pero Fase 15 decidió (con `WHAT_WE_REJECT_FROM_FABLE.md` del
pack 3) que esa implementación es un medio de validación, no el destino de
producto. Es decir: **el CONTENIDO no está superseded (se construyó tal
cual), el ESTATUS "final" sí está superseded.**

## CONTINUATION_PROTOCOL status

**IMPLEMENTED.** Pide 7 ficheros de continuidad; 6 existen con nombre
exacto (`CONTINUATION_STATE.md`, `NEXT_AI_INSTRUCTIONS.md`,
`IMPLEMENTATION_LOG.md`, `TESTING_STATUS.md`, `KNOWN_RISKS.md`,
`OPEN_QUESTIONS.md`), 1 existe con nombre distinto (`DECISION_REVIEW.md` en
vez de `ARCHITECTURE_DECISIONS_INDEX.md` — variante de nombre, mismo
contenido). Reglas del protocolo (no duplicar chat, no usar frameworks
externos como kernel, conectores solo con permisos+auditoría) se cumplen
vía código real (PolicyEngine, ADR-060, `gate_ticket.schema.json`).

## IMPROVEMENT_DOCTRINE status

**READ (metodología, no entregable de código).** Define el ciclo SOURCE →
PRIMITIVE → LIMITATION → ATLAS REINTERPRETATION → SUPERIORITY TEST →
IMPLEMENTATION PATH. Adoptado como estándar de trabajo (visible en cómo se
documentaron las decisiones Tauri→Vite, React Flow→d3-force), sin un
artefacto único que lo "implemente" — es un proceso, no un módulo.

## QUALITY_GATES status

**PARTIALLY_IMPLEMENTED.** 7 gates propuestos (A-G): B-G pasan con
evidencia real (Event First, Cognitive Surface, Control Plane, Governance,
Continuation, No Prototype Trap). Gate A (Architecture Coherence) falla
formalmente porque exige una "Constitution" en `docs/atlas-master/` que no
existe en esa ruta exacta (existe con otro nombre en el pack 3) — mitigado
en la práctica por gobernanza real en código (PolicyEngine, ADR-062), pero
el gate tal como está escrito no pasa 7/7.

## Prompts status

`PROMPT_FABLE5_BUILD_ALL.md` y `PROMPT_WEAKER_AI_CONTINUE.md` —
**READ/histórico, cumplidos en espíritu.** `PROMPT_FABLE5_BUILD_ALL.md`
define su PROPIA Fase 0-6 interna (Fase 5 "Control Plane real", Fase 6
"Improvement Radar") DISTINTA tanto de `TICKETS_PHASE_0_TO_4.md` (mismo
pack) como de `17_PHASES_ROADMAP.md` (pack 1) — su Fase 0-4 SÍ se hizo; su
"Fase 5/6" propia (Connected Accounts+Permission Matrix+Notification
Router+Automation Rules / fichas SOTA de OpenHands-LangGraph-MCP) NO se
hizo como unidad propia, aunque partes dispersas reaparecen (Security
Center cubre algo de Permission Matrix; `docs/knowledge/` cubre parte del
espíritu de "Improvement Radar" sin ser el mismo entregable). No requiere
ADR de parking propio — es una tercera numeración de la misma intención ya
cubierta por ADR-066 (F5/F6 del pack 1) y por el backlog de F17+.

## Templates status

**IMPLEMENTED.** `ADR_TEMPLATE.md` — 60+ ADRs reales siguen su estructura.
`CONNECTOR_SPEC_TEMPLATE.md` — `GmailReadOnlyConnector` + `connection_
recipe.schema.json` siguen su estructura. `RESEARCH_DIGEST_TEMPLATE.md` —
`docs/research/` sigue su estructura en los digests existentes.

## Implementado

Tickets 0-4 completos, CONTINUATION_PROTOCOL, UIUX_FINAL_SPEC (contenido),
Templates (3/3).

## Parcialmente implementado

BACKEND_ADVANCEMENT_SPEC (conectores), QUALITY_GATES (Gate A formal falla),
Phase 1 de tickets (Constitution/Non-goals en ruta distinta).

## Solo documento

ARCHITECTURE_MAP, IMPROVEMENT_DOCTRINE, SOTA_RESEARCH_PROTOCOL, los 2
prompts.

## Copiado pero no integrado

Ninguno (0/14 — verificado en `PACK_MANIFEST_atlas_fable5_handoff_v1.md`).

## Superseded

El estatus "FINAL" de `UIUX_FINAL_SPEC.md` (no su contenido) — superseded
por decisión D11 de Fase 15.

## Parkeado

La "Fase 5/6" propia de `PROMPT_FABLE5_BUILD_ALL.md` (Control Plane
real / Improvement Radar) — cubierta por el mismo espíritu de ADR-066 +
backlog F17+, no requiere ADR dedicado adicional (sería redundante).

## Pendiente y bloqueante

**Ninguno.**

## Tests que prueban implementación

`tests/test_os_event_store.py`, `tests/test_os_event_schema.py`,
`tests/test_os_api.py`, suite de build de `ui/atlas-shell`.

## Docs/ADRs que prueban implementación

ADR-058, ADR-059, ADR-060, `docs/continuation/REPO_AUDIT.md`,
`docs/continuation/CONTINUATION_STATE.md`,
`docs/continuation/phase_recovery/PACK_MANIFEST_atlas_fable5_handoff_v1.md`.

## Veredicto final

**CLOSED_WITH_PARKED_ITEMS**

Tickets 0-4 (el núcleo del pack) implementados con evidencia fuerte. Los
huecos reales (Gate A formal, conectores no-Gmail, nombre de fichero de
continuidad) son menores, ya documentados, y no bloquean nada. La única
pieza "parkeada" (Fase 5/6 propia del prompt maestro) es redundante con
ADR-066 y el backlog F17+ — no necesita cierre adicional propio.
