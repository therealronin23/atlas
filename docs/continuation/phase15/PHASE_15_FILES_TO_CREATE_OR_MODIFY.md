# PHASE_15_FILES_TO_CREATE_OR_MODIFY

## Crear — schemas (estrictos, patrón repo)

- schemas/connection_recipe.schema.json
- schemas/connector_pack.schema.json
- schemas/connector_health.schema.json
- schemas/capability.schema.json
- schemas/policy_rule.schema.json
- schemas/question_pack.schema.json
- schemas/onboarding_session.schema.json
- schemas/business_core.schema.json
- schemas/business_entity.schema.json
- schemas/entity_candidate.schema.json

## Crear — código

- src/atlas/fabric/__init__.py, models.py, ladder.py, recipes.py, packs.py,
  registry.py, concierge.py, auth_broker.py, health.py, testing.py, policy.py,
  capabilities.py, discovery.py
- src/atlas/business/__init__.py, models.py, entities.py, core_engine.py,
  questions.py, extract.py, legacy.py
- src/atlas/api/product_routes.py

## Crear — fixtures (todo fake, marcado demo)

- fixtures/connection_recipes/{gmail,claude_anthropic,whatsapp_personal_import,
  whatsapp_business_platform,odoo_erp,generic_crm,generic_erp,local_csv_folder,
  legacy_desktop_app,ai_provider_registry}.recipe.json
- fixtures/connector_packs/{gestoria,restaurante,crm_sales,software,personal}_pack.json
- fixtures/question_packs/{gestoria_fiscal_contable,restauracion_hosteleria,
  crm_sales,software_it_seguridad,vida_personal}.json
- fixtures/business_core/{restaurant_business_onboarding,gestoria_business_onboarding,
  crm_from_gmail_candidates,erp_from_invoices_candidates,restaurant_business_core_draft,
  gestoria_business_core_draft,legacy_odoo_link_demo,excel_to_atlas_business_core_demo,
  activation_gate_demo}.json
- fixtures/integrations/{connector_health_events.jsonl,sync_conflict_demo.json,
  computer_use_blocked_submit_demo.json,browser_assist_official_portal_demo.json}
- fixtures/security/{policies.json,connector_scope_escalation_denied.json,
  crm_write_requires_gate.json,erp_accounting_write_blocked.json,
  whatsapp_personal_send_blocked.json,cloud_sensitive_data_denied.json}
  + corpus de ataque copiado del pack (prompt injection / tool poisoning /
  memory poisoning / rug pull / remote command)
- fixtures/ui_quality/checklist.json

## Crear — tests

- tests/test_os_fabric.py (recipes/packs/ladder/concierge/registry/health/paridad)
- tests/test_os_policy_security.py (capacidades, invariantes duros, corpus)
- tests/test_os_business.py (questions/onboarding/draft/activación/legacy/extract/paridad)
- tests/test_os_product_api.py (endpoints + CLI wiring)

## Crear — docs

- docs/continuation/phase15/ (este plan + REPO_ALIGNMENT + RISK_REVIEW + cierre)
- docs/decisions/adr/adr_060_integration_fabric_easy_connection.md
- docs/decisions/adr/adr_061_business_core_draft_first.md
- docs/design/UI_QUALITY_GATE.md
- ui/atlas-shell/README.md (declaración de arnés)

## Modificar (mínimo, aditivo)

- src/atlas/api/server.py — registrar product_routes en create_app (2-4 líneas)
- src/atlas/interfaces/cli.py — grupos `connections` y `business` (aditivo)
- tests/test_os_api.py — guard anti-Orchestrator: añadir fabric/ y business/ al scan
- docs/architecture/DECISION_REVIEW.md — D11..D14
- docs/continuation/{CONTINUATION_STATE,NEXT_AI_INSTRUCTIONS,TESTING_STATUS,
  KNOWN_RISKS,OPEN_QUESTIONS,IMPLEMENTATION_LOG}.md
- docs/INDEX.yaml — regenerado por script (nunca a mano)

## Intocables (recordatorio)

WORK_LEDGER.md, AGENTS.md, docs/backlog.yaml, config/governance.json, carpeta 1/,
core/event_bus.py, core/contracts.py, rutas del operador sin commitear.
