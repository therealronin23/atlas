# ZIP1 CLOSURE — atlas_os_build_pack_v1.zip

- **Pack path**: `./atlas_os_build_pack_v1.zip` (36338 bytes, `??` en git).
- **Unpacked path**: `docs/handoff/atlas_build_pack/` (nombre de carpeta NO
  coincide con el ZIP — decisión de ingesta previa a esta sesión, no un
  error de esta auditoría).
- **Propósito original**: blueprint arquitectónico + contratos de schema
  fundacionales para arrancar Atlas OS — "Canonical Build Pack" con
  Fase 0-7 explícitas (`docs/atlas-bible/17_PHASES_ROADMAP.md`), incluyendo
  Manifesto, Non-Goals, Event Canon, reglas de construcción, ADRs
  propuestos (0001-0010).

## Docs/prompts/schemas/fixtures importantes

- `docs/atlas-bible/` — 21 documentos numerados 00-20 (Manifesto, Non-Goals,
  Architecture Map, Rules, Event Canon, Visual/Motion Grammar, Frontend
  Architecture, Backend Bridge, Territories, Memory+Continuity, Harness
  Adapter Contract, Governance Gates, Graph Rendering Strategy, Tech Stack
  Decisions, Framework Boundaries, ADR Index, **17_PHASES_ROADMAP.md**,
  Acceptance Criteria, Premortem, Implementation Map) + `adr/` (10 ADRs
  propuestos 0001-0010).
- `schemas/` — 4 schemas raíz: `event`, `node`, `edge`, `adapter`.
- `fixtures/` — `events/` (4 JSONL), `graph/` (`initial_graph.json`).
- `prompts/` — 3 prompts maestros (Claude Code, Fable5, Codex).
- `tickets/EPICS_AND_TASKS.md` — Epic 1-6 sin numeración de fase.

## Implementado

- Los 4 schemas raíz (`event`, `node`, `edge`, `adapter`) — 1:1 con
  `schemas/*.schema.json` reales, verificado por comparación directa.
- `fixtures/events/demo_first_run.jsonl` y `fixtures/graph/initial_graph.json`
  — presentes con contenido idéntico en `fixtures/` del repo real.
- `04_EVENT_CANON.md` — todos los 50+ tipos de evento propuestos son válidos
  contra `schemas/event.schema.json` real. **Confirmado sano.**
- Principios de ADR-0006/0007/0008/0010 (renderer swappable, kernel propio
  no LangGraph, adapter contract obligatorio, final-compatible no
  prototipo) — observados estructuralmente en el código real, aunque sin
  ADR propio formal que los cite (se cumplen de facto).
- Epic 1-4 de `EPICS_AND_TASKS.md` (Contracts, Frontend Shell, Backend
  Bridge, Memory+Imports).

## Parcialmente implementado

- `07_FRONTEND_ARCHITECTURE.md` — estructura real más simple que la
  propuesta (`ui/atlas-shell/src/core/` tiene 3 ficheros, no 6+); los
  componentes de UI sí existen 1:1.
- `08_BACKEND_BRIDGE.md` — el bridge real EXCEDE la propuesta (más
  endpoints), pero es read-only por decisión (ADR-058), distinto al diseño
  original.
- `12_GOVERNANCE_GATES.md` — sistema de gates real existe pero es más
  sofisticado (PolicyEngine basado en riesgo) que el checklist de 10 gates
  propuesto.
- `EPICS_AND_TASKS.md` Epic 6 (Governance) — SecurityCenter.tsx y gates
  reales existen, pero no como el checklist literal propuesto.
- `20_IMPLEMENTATION_MAP.md` — backend coincide con lo propuesto; frontend
  simplificado.

## Solo documento

- 21 de los 45 ficheros del pack son puramente narrativos/de referencia
  (Manifesto, Non-Goals, Visual/Motion Grammar, Territories, Memory+
  Continuity, Harness Adapter Contract, Graph Rendering Strategy, Framework
  Boundaries, ADR Index, Acceptance Criteria, Premortem, los 3 prompts) —
  documentan intención/contexto, nunca prometieron código propio verificable
  más allá de lo ya contado arriba.

## Copiado pero no integrado

- Ninguno detectado (0/45 — verificado en `PACK_MANIFEST_atlas_os_build_
  pack_v1.md`). El pack no tiene ficheros "consultados pero nunca usados
  ni descartados formalmente" — todo lo que no se implementó cae en PENDING
  (Fase 5/6) o SUPERSEDED (ADRs propuestos), categorías más precisas.

## Superseded

- **10 ADRs propuestos (0001-0010)** — nunca entraron al árbol real de
  decisiones (`docs/decisions/adr/`). Reemplazados por:
  - ADR-058 (Event Kernel Bridge) supersede 0001, 0002, 0007.
  - ADR-059 (UI Stack Web-First) supersede 0005 (Tauri→Vite, React
    Flow/Cytoscape/Sigma→d3-force).
  - ADR-063 (Gate Engine) supersede 0012 (gobernanza — el pack no llegó a
    tener un 0012 real, la referencia es temática).
  - ADR-065 (Gmail connector) relacionado con 0009 (Connected Accounts).
- `14_TECH_STACK_DECISIONS.md` (Tauri+React) — superseded por ADR-059
  explícitamente (razón documentada: Node 18 vs 20+, presión de RAM/disco,
  foco en contratos reactivos antes que empaquetado).

## Parkeado

- **Fase 5 — Visual Orchestrator Territory** y **Fase 6 — Coding+Research
  Territories** de `17_PHASES_ROADMAP.md` — parkeadas formalmente esta
  sesión anterior vía **ADR-066** (`docs/decisions/adr/
  adr_066_visual_orchestrator_and_territories_parked.md`). Motivo: D11 de
  Fase 15 (el shell actual es arnés de validación, no UX final — invertir
  en un canvas/editor completo ahora sería trabajo probablemente
  desechable) + fuera del alcance explícito de ambos mandatos de auditoría
  ("no empezar UI nueva"). Reabrible si el operador lo pide explícitamente.

## Pendiente y bloqueante

**Ninguno.** F5/F6 están pendientes pero NO bloqueantes — verificado en
`F15_F16_DEPENDENCY_AUDIT.md`: ningún módulo de F15/F16 importa ni depende
de nada relacionado con un canvas de workflows.

## Tests que prueban implementación

`tests/test_os_event_schema.py`, `tests/test_os_event_store.py` (schemas +
event store), `tests/test_os_api.py` (backend bridge), suite de
`ui/atlas-shell` build (frontend shell) — heredados de sesiones previas,
no re-ejecutados desde cero en esta auditoría (ver Phase K para qué SÍ se
re-corrió).

## Docs/ADRs que prueban implementación

ADR-058, ADR-059, ADR-066 (nuevo), `docs/continuation/REPO_AUDIT.md`,
`docs/continuation/phase_recovery/PACK_MANIFEST_atlas_os_build_pack_v1.md`
(auditoría exhaustiva fichero-por-fichero, 45/45 clasificados).

## Qué debería quedarse como referencia histórica

Todo el pack — es un blueprint que sigue siendo la referencia MÁS
específica del Event Canon (`04_EVENT_CANON.md`) y de lo que significaría
completar F5/F6 si el operador reabre ADR-066 en el futuro.

## Qué debería borrarse, si algo

**Nada.** Bajo riesgo de mantenerlo (16KB-36KB de docs, sin coste de
mantenimiento activo), alto valor si F5/F6 se reabre alguna vez — borrar
la única fuente detallada de esa especificación sería una pérdida
irreversible por un ahorro de espacio irrelevante.

## Veredicto final

**CLOSED_WITH_PARKED_ITEMS**

Todo ítem importante de este pack está: implementado (schemas, event
kernel, backend bridge, frontend shell — con evidencia real), superseded
(10 ADRs propuestos, decisión Tauri), o parkeado con razón explícita y ADR
(F5/F6, ADR-066, esta sesión). Ningún ítem queda en ambigüedad.
