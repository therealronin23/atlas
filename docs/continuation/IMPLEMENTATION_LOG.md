# IMPLEMENTATION_LOG — Atlas OS

Registro append-only por sesión. Entradas nuevas ARRIBA.

## Sesión 2026-07-11 — Fase 16: cierre de los 8 gaps de RECOMMENDED_PHASE_16.md

Orquestación: Opus dirige, delega en `autobuild-impl-sonnet`/`-haiku` vía
`Task`, audita cada diff agregado con `pytest`+`mypy` reales antes de
commitear. Ledger en `.autobuild/ledger-20260711-1238.md`. Cónclave
(`deliberation_council`) convocado una vez para la decisión de mayor riesgo.

- **F16-1** (Opus): `/permissions/evaluate` converge con PolicyEngine para
  capabilities conocidas; v1 legacy intacto para el resto (ADR-062).
- **F16-2** (Opus, baseline limpio): Gate Engine real — `GateTicket` con
  ciclo `open→approved|rejected`, solo humano resuelve; `request_activation`
  abre ticket, `approve_activation` lo aprueba, nuevo `reject_activation`
  (ADR-063). API `/gates/open`, `/gates/{id}`; CLI `atlas gates list`.
- **F16-3** (Sonnet): sesiones de onboarding persistidas a disco
  (`_SessionStore`, patrón `_Store`); sobreviven a reinicio del bridge
  (probado con 2 apps sobre el mismo `business_core_path`).
- **F16-5** (Sonnet): Sector Registry + Objective Registry formales; test de
  drift real (todo `sector_id` de question_packs/connector_packs debe
  existir). `GET /sectors`, `/objectives`.
- **F16-7** (Sonnet): Legal/ToS registry por conector; `recipes_missing_terms`
  audita que toda receta con riesgo legal declara su entrada — halló que
  `odoo_erp` no la necesitaba pero `legacy_desktop_app` sí (dato real, no la
  premisa inicial).
- **F16-8** (Sonnet): `personal_channel: bool` estructural en la receta; el
  invariante duro de canal personal deja de depender del prefijo del
  `connector_id` (evadible) y pasa a un chequeo directo en código.
- **F16-4** (Cónclave + Sonnet, supervisado): primer conector real —
  `GmailReadOnlyConnector`. El Cónclave descartó la ruta MCP-del-tronco por
  HECHO (el bridge 7341 no puede llamar MCP) y decidió cliente propio con
  SOLO `urllib` de stdlib (cero dependencia nueva, sin ADR-de-dependencia
  necesario). Token como `credential_reference` de entorno, nunca
  persistido/logueado (verificado por Opus independientemente). `email.send`
  ausente (sigue hard-gated). ADR-065.
- **F16-6** (hallazgo): el **daemon de autoconstrucción** (`ATLAS_SELF_BUILD=1`,
  proceso vivo detectado por `ps`/`/proc/<pid>/environ`) ya había implementado
  `HarnessPanel.tsx` en paralelo mientras yo cerraba F16-1..5/7/8, usando los
  endpoints reales según se iban commiteando. Verificado por Opus antes de
  aceptar: `npm run build` limpio, bridge real con `ATLAS_HOME` aislado +
  navegador real conduciendo la vista (clic real, banner "HARNESS — no UX
  final" confirmado por DOM, 4 endpoints respondieron 200 real, 20 items
  renderizados con datos reales). Efecto secundario menor: quedó un
  directorio vacío en `~/atlas/business_core/` real durante la investigación
  del port-conflict con un proceso zombi preexistente (`PID 1446025`,
  no listaba nada) — limpiado (`rmdir`, sin datos que perder).
- **Suite OS: 152→190 passed** (+38). mypy strict limpio en `api/ events/
  fabric/ business/ interfaces/cli.py` (39 ficheros). 8 commits
  (`51c57c77`→`847a18c2`). Un título de commit corregido con `amend`
  (copy-paste erróneo, cuerpo era correcto).

## Sesión 2026-07-10/11 — Fase 15: Atlas Product OS (Integration Fabric + Business Core)

- **Contexto**: el operador entregó `atlas_product_os_liquid_ui_pack_v1.zip`
  horas después de pedir un rediseño visual JARVIS del shell; el pack
  declara el shell React arnés de validación y prohíbe pulirlo como
  producto final (D11: rediseño SUPERSEDED antes de escribirse código).
- **F15-0**: REPO_ALIGNMENT_REPORT + planes de ejecución/archivos/riesgos
  en `docs/continuation/phase15/`; D11-D14 en DECISION_REVIEW.
- **F15-1**: 10 schemas estrictos (endurecidos respecto al pack, que traía
  `required: []`) + espejos pydantic en `fabric/models.py` y
  `business/models.py`, 33 tests de paridad.
- **F15-2**: Integration Fabric completo — Connection Ladder como dato,
  RecipeEngine/PackEngine fail-closed, ConnectionConcierge, AuthBroker
  (rechaza secretos reales, nunca los persiste), ConnectorRegistry
  (rug-pull por hash), HealthMonitor/ConnectionTestRunner (real siempre
  `BLOCKED_BY_MISSING_DEPENDENCY`), PolicyEngine con 7 invariantes duros en
  código. 10 recetas + 5 packs de conectores. 21 tests.
- **F15-3**: corpus de seguridad (12 ficheros del pack + 6 escenarios
  propios), 21 tests — ninguno detecta por heurística de lenguaje.
- **F15-4**: Business Core draft-first (create_draft→request_activation→
  approve_activation, único camino), promoción de candidatos con revisión
  humana obligatoria, AdaptiveQuestionEngine con lazo pregunta→interpreta→
  confirma completo (uncertain/skip válidos pero sin conceder capacidades),
  LegacyLinkLayer (sync off por defecto, canonicidad explícita),
  EntityCandidateExtractor determinista. 5 packs de preguntas. 18 tests.
- **F15-5**: `product_routes.py` registrado en `create_app`; CLI con
  grupos `connections`/`business`. 12 tests de API end-to-end.
  **Bug real encontrado y corregido**: import circular
  `fabric.policy→api.models→api.__init__→api.server→api.product_routes→
  fabric.concierge→fabric.policy` (no lo cazaban los tests, solo un
  entrypoint en frío vía CLI); fix con `TYPE_CHECKING` + import perezoso.
  **Riesgo evitado antes de ejecutar nada**: `BusinessCoreEngine` sin path
  explícito habría escrito en `~/atlas/business_core/` real durante tests.
- **F15-6 (cierre)**: ADR-060/061, `docs/design/UI_QUALITY_GATE.md`,
  `ui/atlas-shell/README.md` (declarado arnés). **Gap real encontrado y
  fijado en la misma fase**: 8 de 26 `gate_id` de capacidades no existían
  en `fixtures/governance/gates.json` (default seguro de todas formas, pero
  callejón sin salida) — 8 gates añadidos + test de regresión.
  `docs/continuation/phase15/` con COMPLETION_REPORT, WHAT_WAS[_NOT]_
  IMPLEMENTED, NEW_GAPS_FOUND (12 gaps clasificados),
  RECOMMENDED_PHASE_16, IMPROVEMENT_PROPOSALS, TESTING_STATUS. Docs
  globales de continuación actualizados (no reescritos: CONTINUATION_STATE,
  NEXT_AI_INSTRUCTIONS, KNOWN_RISKS, OPEN_QUESTIONS, RISK_REGISTER).
- **Suite OS al cierre: 152 passed** (`tests/test_os_*.py`), mypy strict
  limpio en `api/`, `events/`, `fabric/`, `business/`, `interfaces/cli.py`.
  Verificación en vivo: bridge real con `ATLAS_HOME` aislado + curl real;
  CLI real (5 comandos ejecutados, no solo importados).
- **Suite COMPLETA del repo: 3162 passed, 1 skipped** (251s) con los mismos
  2 "failed" de siempre en `TestSelfBuildCycleWiring` (artefacto de
  `ATLAS_NESTED_TEST_RUN=1`, re-corridos sin la variable: 4/4 verdes).
  3049 (cierre Fase 10) + 113 tests nuevos de Fase 15 = 3162, cuadra exacto (105 en el cierre + 8 de la auditoría 2026-07-11).
- **Auditoría con Opus (2026-07-11, a petición del operador)**: 3 defectos
  reales cazados y arreglados en la misma sesión — (1) código muerto que
  introduje: `entities.py` huérfano + `emit_policy_event()` sin llamador +
  flag `modules.crm/erp` decorativo → `emit_policy_event` borrado, y
  `CRM_KINDS/ERP_KINDS`+`modules` ahora ENFORCED en `add_entity`
  (`ModuleDisabledError`); (2) 4 fixtures de security copiados sin test
  (incl. `memory_poisoning_attempt.md`, uno de los 5 ataques del criterio
  #11) + criterio #7 (crm bulk export gate) sin test + `impossible` del
  concierge sin cobertura → 8 tests añadidos, los 18 fixtures de security se
  ejercitan todos; (3) `WHAT_WAS_NOT_IMPLEMENTED` callaba los componentes
  nombrados del prompt no construidos (APISpecImporter, WebhookManager,
  MCPGateway, CRMCoreEngine/ERPCoreEngine, etc.) → sección honesta añadida
  distinguiendo "realizado como dato/receta" de "genuinamente ausente".

## Sesión 2026-07-10 — cierre (mismo día, continuación de la entrada de abajo)

- **Fase 2-3**: 12 schemas raíz + espejos pydantic (test de paridad cazó
  `payload` con default indebido) + Event Kernel completo (store/player/
  core_bridge) — 20 tests.
- **Fase 4**: bridge 7341 read-only (guard estático anti-Orchestrator), WS
  push, evaluador fail-closed, 15 tests + smoke curl real.
- **Fase 5-6**: atlas-shell (Vite5/React18/TS/d3-force), verificada
  conduciéndola con navegador (bug real: guard StrictMode mataba el WS —
  arreglado y documentado en el código).
- **Fase 7-9**: 5 conectores mock + 4 gates + Security Center; import de
  conversaciones con raw preservado + provenance (4 tests).
- **Fase 10**: continuidad completa (CONTINUATION_STATE, NEXT_AI_INSTRUCTIONS,
  TESTING_STATUS), docs de arquitectura por kernel, IMPROVEMENT_DOCTRINE
  apuntando al pipeline real de digestión (no duplicado).
- Suite COMPLETA del repo al cierre: **3049 passed, 1 skipped, 4:40** con 2
  "failed" en TestSelfBuildCycleWiring que son ARTEFACTO de correr la suite
  bajo ATLAS_NESTED_TEST_RUN=1 (la guardia anti-recursión corta el ciclo que
  esos tests esperan ejecutar); re-corridos sin la variable: 4/4 verdes.
  Suites OS: 39 tests verdes; mypy strict limpio; npm build limpio.

## Sesión 2026-07-10 — Fable 5, arranque Atlas OS (master build prompt)

- **Contexto**: el operador entregó `atlas_fable5_handoff_v1.zip` +
  `atlas_os_build_pack_v1.zip` + master prompt. Objetivo: primera versión
  final-compatible de Atlas OS (Event Kernel, bridge, UI dos caras, contratos,
  continuidad), no maqueta.
- **Fase -1 (safety)**: raíz confirmada, `atlas reality --json` OK
  (d70b75e0, dirty=12 rutas del operador — se preservan, jamás `git add -A`).
  Decisión: trabajar en `main` con commits pequeños y selectivos (convención
  real del repo: todo se commitea en main, 57 ahead), SIN push. No se toca
  WORK_LEDGER.md (cambios sin commitear del operador); la entrada de ledger se
  propone en chat al cierre.
- **Fase 0 (auditoría)**: hecha → `REPO_AUDIT.md`. Hallazgos mayores:
  fastapi/uvicorn ya son deps; dashboard+exec_api existen; EventBus existe en
  `core/event_bus.py`; bug conocido del doble Orchestrator (corrupción Merkle)
  condiciona el diseño del bridge (v1 = solo lectura del core).
- **Fase 1**: DECISION_REVIEW + RISK_REGISTER + ADRs (en docs/decisions/adr/,
  convención real) — ver commits de esta sesión.
- ZIPs descomprimidos en `docs/handoff/` (fuente: raíz del repo).
