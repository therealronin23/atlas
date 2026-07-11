# TESTING_STATUS — Fase 15 (ver también docs/continuation/TESTING_STATUS.md, global)

## Unit tests

113 tests nuevos en 5 suites: `test_os_product_contracts.py` (33),
`test_os_fabric.py` (22), `test_os_policy_security.py` (27),
`test_os_business.py` (19), `test_os_product_api.py` (12) — más 1 test
extendido en `test_os_api.py` (guard anti-Orchestrator) y 2 aserciones
actualizadas (schemas=22, gates=12). Total suite OS: **152 passed**.

## Integration tests

`test_os_product_api.py` cubre los dos flujos completos de extremo a
extremo sobre FastAPI real (TestClient): onboarding (start→answer→
confirm→skip→preview→confirm, incluido el 422 real si se salta
confirmar) y Business Core (draft→activate directo rechazado 422→
request-activation→activate).

## Schema validation

22 schemas (12 Fase 2 + 10 Fase 15), paridad modelo↔schema para los 10
nuevos en `test_os_product_contracts.py`, incluida verificación de que la
ladder está ordenada API-first y que `entity_candidate.requires_review`
es `const true` real (rechaza `False` en runtime).

## Security fixtures

18 ficheros en `fixtures/security/`: 12 copiados del corpus del pack
(prompt injection directo/indirecto/OCR, memory poisoning, rug pull,
comando remoto de alto riesgo, issue malicioso, fuga de secreto) + 6
fixtures de escenario propios (request/expected_decision) para los 5
invariantes duros. Ninguno se valida por heurística de lenguaje — todos se
traducen a una dimensión determinista (ver cabecera de
`test_os_policy_security.py`).

## UI quality checks

No aplica esta fase (UI no tocada; `docs/design/UI_QUALITY_GATE.md`
adoptado como criterio para cuando exista superficie de producto real).

## Manual checks

Bridge real + CLI real ejecutados en vivo (ver
`PHASE_15_COMPLETION_REPORT.md` sección "What works" para el detalle
exacto de comandos y endpoints probados).
