# WHAT_WAS_IMPLEMENTED — Fase 15

## Contratos (10 schemas estrictos + espejos pydantic)

connection_recipe, connector_pack, connector_health, capability,
policy_rule, question_pack, onboarding_session, business_core,
business_entity, entity_candidate. Todos con paridad probada
(`test_os_product_contracts.py`, 33 tests) igual que los 12 de Fase 2.

## Integration Fabric + Easy Connection Layer

- Connection Ladder (12 peldaños) como dato, no comentario.
- RecipeEngine + PackEngine fail-closed (rechazan, no sirven a medias).
- ConnectionConcierge: plan humano (will/will-not/gates/ladder rung).
- AuthBroker: solo referencias opacas, rechaza formas de secreto real.
- ConnectorRegistry: detección de rug-pull por hash de descriptor.
- HealthMonitor + ConnectionTestRunner: mock/sandbox reales,
  `mode=real` siempre `BLOCKED_BY_MISSING_DEPENDENCY`.
- ConnectorDiscoveryEngine: stub honesto sin red, `unknown_target` cuando
  no hay receta.
- 10 recetas + 5 packs de conectores (fixtures, demo).

## PolicyEngine (D14)

- Capacidades (26, catálogo en código, cubre el mínimo de 22 del prompt).
- 7 invariantes duros en `HARD_RULES` (Python), independientes de fixture.
- Capas: provenance → duros → blandos (fixture) → spec de capacidad →
  default fail-closed.
- Corpus de seguridad: 12 ficheros del pack copiados + 6 fixtures de
  escenario propios (request/expected_decision), todo probado sin
  heurística de lenguaje (P15-R3).

## Atlas Business Core + Adaptive Question Engine + Legacy Link

- 23 kinds de entidad, un solo store con vistas CRM/ERP.
- Draft-first: create_draft→request_activation→approve_activation, único
  camino, sin atajo.
- promote_candidate exige reviewed_by (ReviewRequiredError si no).
- QuestionEngine: lazo pregunta→interpreta→confirma completo; "no sé"/skip
  válidos pero sin conceder capacidades; preguntas con
  why_this_is_needed/what_atlas_will_do_with_it obligatorios en el schema.
- 5 packs de preguntas por sector (gestoría, restauración, ventas/CRM,
  software/IT, vida personal).
- LegacyLinkLayer: sync_enabled=False siempre al proponer; encenderlo exige
  aprobación humana explícita; canonicidad derivada explícitamente.
- EntityCandidateExtractor determinista sobre evidencia estructurada.

## API + CLI

- `/connections/{catalog,recipes,packs,plan,test,discover}`,
  `/integrations/health`.
- `/business/question-packs` + ciclo completo de onboarding + Business
  Core (draft/request-activation/activate/entities).
- `atlas connections {catalog,plan,test}`,
  `atlas business {question-packs,onboarding-start}`.

## Continuidad

- REPO_ALIGNMENT_REPORT, PHASE_15_EXECUTION_PLAN,
  PHASE_15_FILES_TO_CREATE_OR_MODIFY, PHASE_15_RISK_REVIEW (inicio de fase).
- ADR-060, ADR-061; DECISION_REVIEW D11-D14.
- docs/design/UI_QUALITY_GATE.md + ui/atlas-shell/README.md (shell marcado
  arnés, no producto final).
