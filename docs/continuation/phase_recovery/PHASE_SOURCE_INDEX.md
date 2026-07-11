# PHASE_SOURCE_INDEX — Phase Recovery

## Hallazgo estructural previo (léase antes de la tabla)

**No existe una única numeración de fases "F1 a F16".** Hay CUATRO fuentes
distintas de numeración, parcialmente solapadas, nunca reconciliadas
explícitamente en un documento único hasta ahora:

1. **`atlas_fable5_handoff_v1/tickets/TICKETS_PHASE_0_TO_4.md`** — Phase 0-4
   (Repo Audit, Master Docs+Schemas, Event Simulator, Backend Bridge, UI
   Shell). Fuente MÁS específica y verificable; es la que el repo siguió más
   de cerca al arrancar.
2. **`atlas_build_pack/docs/atlas-bible/17_PHASES_ROADMAP.md`** — Fase 0-7
   (Canonical Build Pack, Contracts+Simulator, Frontend Shell, Backend
   Bridge, Memory+Connected Accounts, **Visual Orchestrator Territory**,
   **Coding+Research Territories**, Hardening). Más ambiciosa, con 2 fases
   (5 y 6) que el repo real NUNCA ejecutó ni referenció de nuevo tras la
   ingesta inicial. `docs/INDEX.yaml` la marca `status: propuesto` (nunca
   promovida a vigente).
3. **`atlas_build_pack/tickets/EPICS_AND_TASKS.md`** — Epic 1-6 (Contracts,
   Frontend Shell, Backend Bridge, Memory+Imports, Visual Orchestrator,
   Governance). Es una re-derivación de (2) sin numeración de fase — mismo
   contenido, otra forma.
4. **La propia narrativa del repo** (`docs/continuation/IMPLEMENTATION_LOG.md`,
   escrita por la IA que ejecutó el trabajo) — Fase -1, 0, 1, 2-3, 4, 5-6,
   7-9, 10, luego un salto directo a **Phase 15** (pack 3) y Fase 16 (este
   repo). Esta es la numeración que aparece en los mensajes de commit
   (`git log`) y es la que el usuario tenía en mente al pedir esta auditoría.

**La tabla de abajo usa la numeración (4) — la del repo real — como columna
principal ("Fase repo"), porque es la única que tiene commits y tests reales
detrás, y anota en cada fila de qué fuente(s) (1)(2)(3) proviene el
contenido real y cuáles quedaron sin ejecutar.**

## Tabla F(-1) – F16

| Fase repo | Título | Fuente(s) | Fichero fuente | Objetivo | Entregables | Criterio de aceptación (fuente) | Dependencias | ¿Prerrequisito de F15/F16/F17? | Evidencia actual |
|---|---|---|---|---|---|---|---|---|---|
| F-1 | Safety checkpoint | ninguna (invención de sesión) | `docs/continuation/IMPLEMENTATION_LOG.md` §"Fase -1" | Confirmar raíz del repo, estado dirty, decidir no-push | — | — | ninguna | No | commit `44bd8971` (mención), sin doc dedicado |
| F0 | Repo Audit | (1) Phase 0, (2) Fase 0 | `TICKETS_PHASE_0_TO_4.md`, `17_PHASES_ROADMAP.md` | Auditar el repo real antes de construir | `docs/atlas-current-state/REPO_AUDIT.md` (pedido) | "documentos existen y no se contradicen" (fuente 2) | ninguna | Sí — todo lo posterior asume este audit | `docs/continuation/REPO_AUDIT.md` (existe, ruta distinta a la pedida pero mismo contenido: stack real, colisiones build-pack↔repo, peligro doble Orchestrator) — **IMPLEMENTADO** |
| F1 | Master Docs + Schemas / Contracts+Simulator | (1) Phase 1, (2) Fase 1 | ídem | Constitución, Non-goals, Architecture Map, Event Canon, schemas, ADR index | schemas event/node/edge/adapter | "simulador puede reproducir eventos" (fuente 2) | F0 | Sí | commit `44bd8971` (docs) + `2e20312a` (schemas+store) — **IMPLEMENTADO** (ADR-058 Event Kernel) |
| F2-3 | Event Simulator + Backend Bridge | (1) Phase 2+3, (2) Fase 1(sim)+3(bridge) | ídem | Event store/reducer/player, API server + WS | `src/atlas/events/*`, bridge 7341 | "UI reacciona a eventos" / "UI consume eventos reales" | F1 | Sí | commits `2e20312a`, `2902350e` — rutas `/health /reality /graph /timeline /intent /connectors /permissions` + WS `/events` confirmadas por grep — **IMPLEMENTADO** |
| F4 | UI Shell | (1) Phase 4, (2) Fase 2 (Frontend Shell) | ídem | Universal Bar, Living Knowledge Graph, Execution Pipeline, Timeline, Control Center, Integration Fabric, Permissions Matrix, Personalization, Dev Event Inspector | `ui/atlas-shell/` | "UI shell final-compatible" | F2-3 | Sí | commit `1ced8944` — `ui/atlas-shell/src/components/{UniversalBar,LivingGraph,ExecutionPipeline,Timeline,EventInspector}.tsx` + `control/{IntegrationFabric,PermissionsMatrix,Personalization,SecurityCenter}.tsx` todos existen — **IMPLEMENTADO** (nombrado luego "arnés de validación", no UX final, por decisión D11 posterior — ver Fase 15) |
| **F5** | **Visual Orchestrator Territory** | (2) Fase 5, (3) Epic 5 | `17_PHASES_ROADMAP.md`, `EPICS_AND_TASKS.md` | Canvas tipo n8n, node palette, inspector, graph JSON export/import, ejecución visual vía eventos | React Flow canvas + compiler | "flujo visual se ejecuta como eventos" | F4 | No (F15/F16 no lo necesitan) | **CERO evidencia.** `grep -ri "react-flow\|node.palette" ui/ src/` → sin resultados. Ningún ADR lo menciona. Ningún doc de continuación lo menciona tras la ingesta inicial. — **PENDING / MISSING_SOURCE_EXECUTION** (fuente existe, ejecución no) |
| **F6** | **Coding + Research Territories** | (2) Fase 6, (3) parcial en Epic 5/otros | `17_PHASES_ROADMAP.md` | Territorio de código (Monaco/diff/tests) + territorio de investigación (árbol preguntas/fuentes/evidencia) | — | "tareas reales generan artefactos y memoria" | F5 | No | **CERO evidencia de UI dedicada.** (El *backend* de investigación SÍ existe de forma no relacionada: TopicExpander/panorama_scout del lazo de auto-mejora, pero NO como "Research Territory" de este pack, y no hay Coding Territory con Monaco en absoluto.) — **PENDING / MISSING_SOURCE_EXECUTION** |
| F7-9 | Conectores mock + Gates + Security Center + Memory import | (3) Epic 4 (Memory+Imports) + Epic 6 (Governance) parcial; (2) Fase 4 (Memory+Connected Accounts) + parte de Fase 7 (Hardening: "Gates completos") | `EPICS_AND_TASKS.md`, `17_PHASES_ROADMAP.md` | 5 conectores simulados, 4 gates, Security Center UI, import de conversaciones con raw+provenance | `src/atlas/api/conversation_import.py`, fixtures conectores | "importar un export crea nodos/patrones/timeline" (fuente 2, Fase 4) | F4 | Sí (F15 conecta sobre estos gates/conectores) | commit `7f161bee` — **IMPLEMENTADO** (parcial respecto a Fase 7 completa: falta "Audit replay" dedicado a OS, "Performance", "Packaging" — ver fila F-Hardening) |
| F10 | Continuidad completa | ninguna (invención de sesión, práctica estándar) | — | CONTINUATION_STATE, NEXT_AI_INSTRUCTIONS, TESTING_STATUS | docs/continuation/*.md | — | F0-F9 | No, es meta-trabajo | commit `fb914400` — **IMPLEMENTADO** |
| — | Hardening (Fase 7 de fuente 2) | (2) Fase 7 | `17_PHASES_ROADMAP.md` | Audit replay, Gates completos, Sandbox policies, Failure memory, Performance, Packaging | — | "demo final 60-90s sin datos fake críticos" | F1-F9 | Parcial | Gates: **IMPLEMENTADO** (F16-2 Gate Engine). Sandbox: **IMPLEMENTADO** (BwrapJail, preexistente al pack). Failure memory: **IMPLEMENTADO** (LessonStore, preexistente). Audit replay OS-específico: **PARCIAL** (`src/atlas/events/player.py` + `replay.schema.json` existen, pero no hay endpoint `/replay` en `server.py`). Performance/Packaging: **PENDING**, nunca abordados para Atlas OS |
| F11-14 | — | **NINGUNA fuente las define** | — | — | — | — | — | **MISSING_SOURCE_DEFINITION.** No existe ningún fichero en los 3 packs, en `docs/decisions/`, ni en `docs/continuation/` que use literalmente "Fase 11", "Fase 12", "Fase 13" o "Fase 14". El salto de "Fase 10" a "Phase 15" en la narrativa del repo NO se debe a que 11-14 se completaran silenciosamente: esos números simplemente nunca fueron asignados por nadie. Lo más cercano es el trabajo no hecho de F5/F6 (Visual Orchestrator, Coding+Research Territories) de la fuente (2), que tampoco se llama "11-14". |
| F15 | Atlas Product OS | pack 3 completo | `PROMPT_FABLE_PHASE_15.md`, `PHASE_15_TASKS.md` | Integration Fabric, PolicyEngine, Business Core, Adaptive Question Engine, Sector/Objective Registry, etc. | ver `docs/continuation/phase15/` | `ACCEPTANCE_CRITERIA.md` del pack | Ninguna explícita a F11-14; SÍ asume F0-F10 (bridge, event kernel, UI shell existentes) — confirmado en `FABLE_LAST_OUTPUT_ANALYSIS.md` (revisión explícita del output previo) | — | commits `50293445`..`a1ead24e` — **IMPLEMENTADO** (con huecos honestos documentados en `WHAT_WAS_NOT_IMPLEMENTED.md`) |
| F16 | Cierre de gaps de F15 | `docs/continuation/phase15/RECOMMENDED_PHASE_16.md` (auto-generado por la propia Fase 15, no por ningún pack) | ídem | Gate Engine real, convergencia PolicyEngine, persistencia, registries, legal, conector real, arnés UI | ver memoria `atlas-os-phase16-*` | 8 tareas del recomendado | F15 | — | commits `51c57c77`..`4faaf70f` — **IMPLEMENTADO** (verificado sesión anterior, 3200 tests) |

## Resumen ejecutivo de esta fase

- **F0 a F4 (fuente 1, la más específica): IMPLEMENTADAS con evidencia real
  fuerte** (código+tests+docs, no solo narrativa).
- **F5 y F6 (fuente 2, Visual Orchestrator / Coding+Research Territories):
  NUNCA ejecutadas.** Es el hallazgo más concreto de esta auditoría — dos
  fases NUMERADAS con entregables explícitos, sin ADR de rechazo, sin
  mención posterior, ausentes del todo. Ver `PHASE_1_16_COVERAGE_MATRIX.md`
  y `PHASE_1_14_BACKFILL_PLAN.md` para la decisión de qué hacer con ellas.
- **F7-F10: IMPLEMENTADAS**, con un sub-hueco real en "Hardening" (Performance
  y Packaging de Atlas OS específicamente, nunca abordados — pero esto nunca
  fue numerado F11-14 por nadie, es simplemente trabajo pendiente de la Fase
  7 de la fuente 2).
- **F11-14 no existen como concepto en ninguna fuente.** No es un caso de
  "se completaron sin evidencia": es un caso de "nadie las definió nunca".
  El salto de F10 a "Phase 15" fue consciente y revisado (ver
  `PACK_LOCATION_REPORT.md`), no un error de conteo.
- **F15-F16: IMPLEMENTADAS**, ya verificadas en sesiones previas con
  evidencia de tests+build+smoke real.
