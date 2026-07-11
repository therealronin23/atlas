# PACK_LOCATION_REPORT — Phase Recovery

## Pack 1 — `atlas_os_build_pack_v1.zip`

- **ZIP original**: `./atlas_os_build_pack_v1.zip` (36338 bytes, sin trackear
  en git, `??` en `git status`).
- **Descomprimido en**: `docs/handoff/atlas_build_pack/` (nombre de carpeta
  NO coincide con el nombre del ZIP — es una decisión de la ingesta original,
  no un error de esta auditoría).
- **Ficheros**: 4 schemas JSON (`node`, `event`, `edge`, `adapter`), 2 fixtures
  (`fixtures/graph`, `fixtures/events`), 3 prompts
  (`PROMPT_CLAUDE_CODE_IMPLEMENT.md`, `PROMPT_FABLE5_ATLAS_BUILD.md`,
  `PROMPT_CODEX_IMPLEMENT.md`), 1 ticket file (`EPICS_AND_TASKS.md`, 6 epics
  sin numeración de fase), `docs/atlas-bible/` (19 documentos numerados
  00-18, incl. `17_PHASES_ROADMAP.md` — **la única fuente que define Fase
  0-7 con nombre y entregables explícitos**), 1 README.
- **Indexado en `docs/INDEX.yaml`**: SÍ — 19 entradas bajo
  `docs/handoff/atlas_build_pack/docs/atlas-bible/*`, todas
  `status: propuesto` (nunca promovidas a `vigente`).
- **Referenciado por ARCHITECTURE_MAP/DECISION_REVIEW/WORK_LEDGER**: el
  `REPO_AUDIT.md` (Fase 0 de la sesión 2026-07-10) lo menciona explícitamente
  y establece el orden de prioridad `repo > evidencia > handoff > build pack >
  prompt`. No aparece en `WORK_LEDGER.md` fuera de esa auditoría inicial.
- **Usado por F15/F16**: NO directamente — F15/F16 consumieron el pack 3
  (`atlas_product_os_liquid_ui_pack_v1`), no este.
- **Estado**: parcialmente usado en Fase 0-4 de la sesión 2026-07-10
  (schemas/fixtures base, Event Canon), pero `17_PHASES_ROADMAP.md` (Fase 5
  Visual Orchestrator, Fase 6 Coding+Research Territories) **nunca fue
  ejecutado ni referenciado de nuevo** — ver `PHASE_SOURCE_INDEX.md` y
  `PHASE_1_16_COVERAGE_MATRIX.md`.

## Pack 2 — `atlas_fable5_handoff_v1.zip`

- **ZIP original**: `./atlas_fable5_handoff_v1.zip` (16038 bytes, `??`).
- **Descomprimido en**: `docs/handoff/atlas_fable5_handoff_v1/` (nombre SÍ
  coincide con el ZIP).
- **Ficheros**: `tickets/TICKETS_PHASE_0_TO_4.md` (define Fase 0-4:
  Repo Audit / Master Docs+Schemas / Event Simulator / Backend Bridge / UI
  Shell — **numeración distinta e independiente de la del pack 1**),
  `docs/` (7 specs: BACKEND_ADVANCEMENT_SPEC, ARCHITECTURE_MAP,
  SOTA_RESEARCH_PROTOCOL, CONTINUATION_PROTOCOL, IMPROVEMENT_DOCTRINE,
  QUALITY_GATES, UIUX_FINAL_SPEC), `prompts/` (2: BUILD_ALL,
  WEAKER_AI_CONTINUE), `templates/` (3).
- **Indexado en `docs/INDEX.yaml`**: no confirmado exhaustivamente en esta
  pasada (pendiente de `PACK_MANIFEST_atlas_fable5_handoff_v1.md`).
- **Referenciado por ARCHITECTURE_MAP/DECISION_REVIEW/WORK_LEDGER**: SÍ —
  es la fuente primaria de la sesión "Fable 5, arranque Atlas OS" del
  2026-07-10 (ver `IMPLEMENTATION_LOG.md`).
- **Usado por F15/F16**: indirectamente — F15/F16 heredan el Event Kernel,
  bridge y UI shell que este pack originó.
- **Estado**: Fase 0-3 (Repo Audit, Master Docs, Event Simulator, Backend
  Bridge) con evidencia fuerte de implementación real. Fase 4 (UI Shell) con
  evidencia fuerte también — ver Coverage Matrix.

## Pack 3 — `atlas_product_os_liquid_ui_pack_v1.zip`

- **ZIP original**: `./atlas_product_os_liquid_ui_pack_v1.zip` (216477
  bytes, `??` — el más grande de los tres, con diferencia).
- **Descomprimido en**: `docs/handoff/atlas_product_os_liquid_ui_pack_v1/`.
- **Ficheros**: ~270 ficheros — `context/` (5, incl.
  `FABLE_LAST_OUTPUT_ANALYSIS.md` y `WHAT_WE_KEEP_FROM_FABLE.md`/
  `WHAT_WE_REJECT_FROM_FABLE.md`, que documentan una revisión EXPLÍCITA del
  output previo de Fable antes de escribir este pack), `product/` (36),
  `research/` (~40, numerados 01-15 — **la etiqueta "Phase 15" del prompt
  correlaciona con "Research 01 a 15", no con 14 fases de implementación
  previas**), `sectors/` (17), `design/` (~40), `backend/` (~65 specs de
  motores, la mayoría nunca implementados — ver
  `docs/continuation/phase15/WHAT_WAS_NOT_IMPLEMENTED.md`), `schemas/`
  (~85 JSON schemas, de los cuales el repo real implementó 26), `adr/`
  (~50 ADRs propuestos), `tasks/` (6, incl. `PHASE_15_TASKS.md`,
  `FABLE_EXECUTION_ORDER.md`, `ACCEPTANCE_CRITERIA.md`, `DO_NOT_DO.md`),
  `continuation/` (6 plantillas), `fixtures/` (9 categorías).
- **Indexado en `docs/INDEX.yaml`**: parcial — pendiente de confirmación
  exhaustiva en `PACK_MANIFEST_atlas_product_os_liquid_ui_pack_v1.md`.
- **Referenciado por ARCHITECTURE_MAP/DECISION_REVIEW/WORK_LEDGER**: SÍ —
  es la fuente primaria de F15 (`docs/continuation/phase15/`).
- **Usado por F15/F16**: SÍ, directamente y extensamente — es el pack fuente
  de ambas fases.
- **Estado**: ~15% de los motores de backend nombrados existen como código
  real; el resto está documentado honestamente como NO implementado en
  `docs/continuation/phase15/WHAT_WAS_NOT_IMPLEMENTED.md` (ya escrito en una
  auditoría previa el 2026-07-11, reutilizado aquí, no re-derivado).

## Hallazgo clave de esta fase

**"Phase 15" no es una afirmación de que las fases 1-14 quedaron cerradas.**
El pack 3 fue escrito por el operador/Fable DESPUÉS de revisar explícitamente
el output real de la sesión anterior (`FABLE_LAST_OUTPUT_ANALYSIS.md`:
"Fable produjo... event bridge, FastAPI read-only OS bridge, schemas,
fixtures, OS tests, repo audit, documentación y un UI harness web-first" —
listado que coincide con lo que el repo realmente tiene) y decidir
explícitamente qué conservar (`WHAT_WE_KEEP_FROM_FABLE.md`) y qué rechazar
(`WHAT_WE_REJECT_FROM_FABLE.md` — el shell React como UX final, el grafo
estático como identidad de producto). El número "15" coincide con la
numeración de investigación (`research/01`...`research/15`) del propio pack,
no con un conteo de fases de implementación.

Dicho esto, la auditoría de esta sesión SÍ encuentra fases numeradas y
NUNCA referenciadas de nuevo: `docs/handoff/atlas_build_pack/docs/atlas-bible/
17_PHASES_ROADMAP.md` define Fase 0 a Fase 7 explícitamente, con **Fase 5
— Visual Orchestrator Territory** y **Fase 6 — Coding + Research
Territories** sin ninguna evidencia de código, sin ADR de rechazo, sin
mención en ningún doc de continuación posterior. Ver
`PHASE_SOURCE_INDEX.md` y `PHASE_1_16_COVERAGE_MATRIX.md` para el detalle
completo y evidenciado.
