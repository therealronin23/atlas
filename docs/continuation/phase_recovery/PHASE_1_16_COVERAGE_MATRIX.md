# PHASE_1_16_COVERAGE_MATRIX — Phase Recovery

Estados permitidos (exactamente uno por fase): IMPLEMENTED,
PARTIALLY_IMPLEMENTED, DOCUMENT_ONLY, SUPERSEDED, PARKED, PENDING, UNKNOWN,
CONFLICTS_WITH_CURRENT_DIRECTION.

Ver `PHASE_SOURCE_INDEX.md` para las fuentes y el detalle de por qué existen
4 numeraciones distintas. Esta matriz usa la numeración del repo real
(la que aparece en commits y en `IMPLEMENTATION_LOG.md`).

## F0 — Repo Audit

**Status: IMPLEMENTED**

- Evidencia de código: N/A (es un audit, no código).
- Evidencia de docs/ADR: `docs/continuation/REPO_AUDIT.md` (existe, cubre
  stack real, colisiones build-pack↔repo, peligro doble Orchestrator,
  gobernanza de docs, estado git).
- Evidencia runtime: `atlas reality --json` es el mecanismo real que este
  audit institucionalizó como hábito recurrente (usado en cada sesión desde
  entonces, incl. esta).
- Huecos: ninguno relevante.
- ¿F15/F16 dependían de esto?: Sí — el orden de prioridad `repo > evidencia >
  handoff > build pack > prompt` que estableció se siguió literalmente en
  F15/F16.
- ¿Bloquea seguir tras F16?: No.
- Acción recomendada: ninguna.

## F1 — Master Docs + Schemas / Contracts+Simulator

**Status: IMPLEMENTED**

- Código: `schemas/event.schema.json`, `node.schema.json`, `edge.schema.json`
  existen (más 23 schemas adicionales de fases posteriores).
- Tests: paridad schema↔pydantic verificada en `tests/test_os_*contracts*.py`
  y equivalentes (heredado del patrón F15).
- Docs/ADR: ADR-058 (Event Kernel), commit `44bd8971`.
- Huecos: ninguno relevante — la "Constitución"/"Non-goals" formales del
  pack 1 no se escribieron como documento propio, pero su contenido quedó
  absorbido en AGENTS.md/ecosystem map (decisión implícita, no documentada
  como tal — hueco menor de trazabilidad, no de sustancia).
- ¿F15/F16 dependían?: Sí — los 26 schemas actuales extienden directamente
  este patrón (mismo directorio `schemas/`, misma convención strict).
- Acción recomendada: ninguna funcional; opcionalmente, un ADR corto que
  documente "la Constitución vive distribuida en AGENTS.md + ecosystem_map,
  no como fichero único" para cerrar la trazabilidad. Ver backfill Phase 8.

## F2-3 — Event Simulator + Backend Bridge

**Status: IMPLEMENTED**

- Código: `src/atlas/events/{core_bridge,emit,player,schemas,store}.py`,
  `src/atlas/api/server.py` (rutas `/health /reality /graph /timeline
  /intent /connectors /permissions` + WS `/events` confirmadas por grep en
  esta sesión).
- Tests: `tests/test_os_event_store.py`, `tests/test_os_event_schema.py`,
  `tests/test_os_api.py`.
- Docs/ADR: ADR-058, commits `2e20312a`, `2902350e`.
- Huecos: ninguno relevante para lo que pedía la fuente.
- ¿F15/F16 dependían?: Sí — `product_routes.py` se registra sobre esta misma
  app FastAPI (`register_product_routes`), y el evaluador fail-closed que
  F16-1 converge es el mismo `/permissions/evaluate` de esta fase.
- Acción recomendada: ninguna.

## F4 — UI Shell

**Status: IMPLEMENTED**

- Código: los 9 componentes nombrados en la fuente 1 (Universal Bar, Living
  Knowledge Graph, Execution Pipeline, Timeline, Control Center [=carpeta
  `control/`], Integration Fabric, Permissions Matrix, Personalization
  Settings, Developer Event Inspector) existen 1:1 como ficheros reales en
  `ui/atlas-shell/src/components/`.
- Docs/ADR: ADR-059, commit `1ced8944`.
- Huecos: el shell fue re-clasificado en Fase 15 como "arnés de validación,
  no UX final" (decisión D11) — esto NO es un hueco de implementación, es
  una redirección de producto documentada y deliberada.
- ¿F15/F16 dependían?: Sí — F16-6 (HarnessPanel) se montó como una vista más
  dentro de este mismo shell (`App.tsx` `view === "harness"`).
- Acción recomendada: ninguna. La UI nativa/líquida que reemplazaría este
  arnés es trabajo de producto futuro, no un gap de esta fase.

## F5 — Visual Orchestrator Territory

**Status: PENDING**

- Código: **ninguno.** `grep -ri "react-flow\|reactflow\|node.palette" ui/
  src/` sin resultados. No existe `workflow.schema.json`,
  `workflow_node.schema.json` ni `workflow_edge.schema.json` en `schemas/`
  (sí existen en el pack 3 sin implementar — ver
  `WHAT_WAS_NOT_IMPLEMENTED.md`).
- Docs/ADR: ninguno menciona esta fase después de la ingesta inicial del
  pack 1 (`docs/handoff/atlas_build_pack/docs/atlas-bible/17_PHASES_ROADMAP.md`,
  `status: propuesto` en INDEX.yaml, nunca promovido).
- Huecos: el 100% del entregable (canvas, node palette, inspector, graph
  JSON export/import, graph compiler, execute/debug visual).
- ¿F15/F16 dependían de esto?: **No.** Ninguna ruta de código de F15/F16
  importa ni referencia nada relacionado con un canvas de workflows.
  Verificado: `grep -ri "workflow\|orchestrator.canvas" src/atlas/fabric/
  src/atlas/business/` → sin resultados relevantes (solo el `Orchestrator`
  del core preexistente, que es una cosa distinta — el motor de tareas, no
  un canvas visual).
- ¿Bloquea seguir tras F16 / Pixel Perfect / F17?: No directamente, pero es
  una promesa de producto sin cumplir del pack 1 que nadie ha cerrado ni
  parkeado formalmente.
- Acción recomendada: **PARK con razón explícita**, no implementar en esta
  sesión (fuera del alcance — "no empezar F17/UI nueva"). Ver
  `PHASE_1_14_BACKFILL_PLAN.md`.

## F6 — Coding + Research Territories

**Status: PENDING**

- Código: ninguno para "Coding Territory" (Monaco/diff/tests UI) ni
  "Research Territory" (árbol preguntas/fuentes/evidencia UI) como
  superficies del producto Atlas OS.
- Nota importante para no confundir: SÍ existe un sistema de investigación
  autónoma real en Atlas (`panorama_scout`, `topic_expander`, ingesta a
  `docs/knowledge/`, ver `WORK_LEDGER.md` entradas 2026-07-09/10) — pero es
  el motor de auto-mejora del NÚCLEO de Atlas (preexistente, sin relación
  con este pack), no la "Research Territory" que este pack pedía como
  superficie visual del producto Atlas OS. Son dos cosas distintas con
  nombre similar — no contar la primera como evidencia de la segunda.
- Docs/ADR: mismo caso que F5 — `status: propuesto`, nunca ejecutado.
- ¿F15/F16 dependían?: No.
- Acción recomendada: **PARK con razón explícita**, igual que F5.

## F7-9 — Conectores mock + Gates + Security Center + Memory import

**Status: IMPLEMENTED** (con nota de alcance parcial respecto a "Hardening")

- Código: `src/atlas/api/conversation_import.py`, fixtures de 5 conectores,
  4 gates, `ui/atlas-shell/src/components/control/SecurityCenter.tsx`.
- Tests: `tests/test_os_memory_import.py` + suites relacionadas.
- Docs: commit `7f161bee`.
- Huecos: ninguno respecto a lo que la fuente 2 (Fase 4, Memory+Connected
  Accounts) pedía explícitamente.
- ¿F15/F16 dependían?: Sí — F16 amplía el mismo Gate concept (Gate Engine
  real F16-2 generaliza sobre esta base de 4 gates).
- Acción recomendada: ninguna.

## F10 — Continuidad completa

**Status: IMPLEMENTED**

- Docs: `CONTINUATION_STATE.md`, `NEXT_AI_INSTRUCTIONS.md`,
  `TESTING_STATUS.md`, commit `fb914400`. Mantenidos vivos y actualizados en
  cada fase posterior (F15, F16, y ahora esta auditoría).
- Acción recomendada: ninguna.

## "Hardening" (Fase 7 de la fuente 2, sin número propio en la narrativa del repo)

**Status: PARTIALLY_IMPLEMENTED**

- Gates: IMPLEMENTED (F16-2 Gate Engine).
- Sandbox policies: IMPLEMENTED (BwrapJail, preexistente al pack, no
  específico de Atlas OS pero cumple el objetivo).
- Failure memory: IMPLEMENTED (LessonStore, preexistente).
- Audit replay: PARTIALLY_IMPLEMENTED — `src/atlas/events/player.py` +
  `schemas/replay.schema.json` existen (mecanismo real), pero no hay un
  endpoint `/replay` expuesto en `server.py` ni un test que ejercite replay
  end-to-end sobre el bridge OS específicamente.
- Performance: PENDING — nunca medido/optimizado como entregable propio de
  Atlas OS.
- Packaging: PENDING — no hay build empaquetado (Tauri u otro) de
  `ui/atlas-shell`; solo `npm run dev`/`npm run build` (Vite web).
- Acción recomendada: no bloqueante. Candidato de bajo-medio riesgo para
  backfill documental (registrar el hueco), no de código urgente.

## F11-14

**Status: DOCUMENT_ONLY** — más precisamente: **no hay documento que las
declare**. Se usa `DOCUMENT_ONLY` aquí en el sentido de "el único artefacto
posible es documentar su inexistencia", no porque exista un doc que las
defina sin código. Ver `PHASE_SOURCE_INDEX.md`: **MISSING_SOURCE_DEFINITION**
es el estado más preciso, no está en la lista de estados permitidos de este
documento — se usa DOCUMENT_ONLY como el más cercano de los estados
permitidos.

- ¿Bloquean F15/F16/F17?: No — nunca fueron una unidad de trabajo real, por
  lo que no hay nada que "desbloquear".
- Acción recomendada: cerrar la ambigüedad numérica documentando
  explícitamente (este mismo documento + `PHASE_RECOVERY_FINAL_VERDICT.md`)
  que F11-14 no existen y por qué, para que ninguna sesión futura las
  busque de nuevo.

## F15 — Atlas Product OS

**Status: IMPLEMENTED**

- Evidencia exhaustiva ya existente: `docs/continuation/phase15/
  PHASE_15_COMPLETION_REPORT.md`, `WHAT_WAS_IMPLEMENTED.md`,
  `WHAT_WAS_NOT_IMPLEMENTED.md` (honesto, incluye huecos reales:
  conectores reales, vault de secretos, sector registry completo [5/22],
  gestoría vertical completa, Presence Engine, Liquid App Runtime, etc.).
- Tests: 152 tests OS al cierre de F15 (parte de los 190 actuales).
- Auditoría cruzada ya realizada 2026-07-11 (sesión previa): 3 defectos
  reales cazados y arreglados (código muerto, criterios sin test, honestidad
  de docs) — commit `be85665f`.
- ¿F15 asumía componentes F1-F14 existentes?: Sí — Event Kernel (F1-F3),
  bridge (F2-3), UI shell (F4), gates (F7-9). NO asumía F5/F6 (Visual
  Orchestrator/Coding+Research Territories) — F15 nunca los referencia ni
  los necesita.
- Acción recomendada: ninguna — ver `F15_F16_DEPENDENCY_AUDIT.md` para el
  detalle formal de esta pregunta.

## F16 — Cierre de gaps de F15

**Status: IMPLEMENTED**

- Evidencia: memoria de sesión `atlas-os-phase16-autobuild-conclave-daemon-
  2026-07-11.md`, `docs/continuation/CONTINUATION_STATE.md` (sección Fase
  16), 9 commits `51c57c77`..`4faaf70f`, suite completa del repo verificada
  en 3200 passed/1 skipped al cierre.
- Acción recomendada: ninguna — ver `F15_F16_DEPENDENCY_AUDIT.md` y
  `F15_F16_RECONCILIATION_REPORT.md`.

## Tabla resumen

| Fase | Status |
|---|---|
| F0 | IMPLEMENTED |
| F1 | IMPLEMENTED |
| F2-3 | IMPLEMENTED |
| F4 | IMPLEMENTED |
| F5 (Visual Orchestrator) | PENDING |
| F6 (Coding+Research Territories) | PENDING |
| F7-9 | IMPLEMENTED |
| F10 | IMPLEMENTED |
| Hardening (sin número propio) | PARTIALLY_IMPLEMENTED |
| F11-14 | no existen (ver nota arriba) |
| F15 | IMPLEMENTED |
| F16 | IMPLEMENTED |
