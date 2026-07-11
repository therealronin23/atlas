# TESTING_STATUS — Atlas OS (2026-07-11, tras Fase 15)

## Suites del frente OS

| Suite | Tests | Estado | Cubre |
| --- | --- | --- | --- |
| tests/test_os_event_schema.py | 13 | ✅ verde | paridad modelo↔JSON Schema (22 schemas), 6 fixtures, grafo, rechazos |
| tests/test_os_event_store.py | 7 | ✅ verde | store/listeners, player (simulated, anti-merkle, missing), bridge core |
| tests/test_os_api.py | 15 | ✅ verde | endpoints, WS tail+push, guard anti-Orchestrator (4 paquetes), fail-closed, traversal |
| tests/test_os_memory_import.py | 4 | ✅ verde | raw preservado, conformidad schema, idempotencia, eventos reales |
| tests/test_os_product_contracts.py | 33 | ✅ verde | paridad de los 10 schemas Fase 15, orden de la ladder, catálogo de kinds |
| tests/test_os_fabric.py | 21 | ✅ verde | recipes/packs fail-closed, ladder, rug-pull, health, testing runner, concierge, discovery, auth broker |
| tests/test_os_policy_security.py | 21 | ✅ verde | 5 invariantes duros + corpus de ataque, integridad gate_id↔gates.json, catálogo de capacidades |
| tests/test_os_business.py | 18 | ✅ verde | draft-first, promoción con revisión, lazo de preguntas, legacy link, extracción determinista |
| tests/test_os_product_api.py | 12 | ✅ verde | /connections y /business end-to-end sobre FastAPI real |

**Total: 144 passed.**

Comando: `PYTHONPATH=src ATLAS_NESTED_TEST_RUN=1 python -m pytest tests/test_os_*.py -q`

## Tipos y build

- `MYPYPATH=src mypy src/atlas/api/ src/atlas/events/ src/atlas/fabric/ src/atlas/business/ src/atlas/interfaces/cli.py` → limpio (strict, 32 ficheros).
- `ui/atlas-shell: npm run build` → sin cambios esta fase (no se tocó UI).

## Verificación en vivo hecha esta sesión (no solo tests)

- Bridge real levantado con `ATLAS_HOME` aislado en `/tmp` (uvicorn en
  127.0.0.1:7399) y probado por curl real: `/health`, `/connections/catalog`,
  `/connections/plan` (gmail), `/business/question-packs` — respuestas
  reales, proceso detenido y `ATLAS_HOME` temporal borrado al terminar.
- CLI real ejecutada (no solo importada, catch de un bug real de import
  circular): `atlas connections catalog`, `atlas connections plan gmail`,
  `atlas connections test gmail --mode mock`, `atlas business
  question-packs`, `atlas business onboarding-start qp_restauracion_hosteleria`.
- Verificado que `$ATLAS_HOME` real (`~/atlas`) NO recibió escrituras
  durante la suite (`ls ~/atlas/business_core` antes/después de los fixes).

## Qué NO está probado (honesto)

- La UI no tiene tests automatizados (ni unit ni e2e) — sigue igual que
  antes de Fase 15 (no se tocó UI esta fase).
- El WS bajo carga/reconexión prolongada (backoff implementado, no estresado).
- kuzu/grafo real en /graph (no cableado aún, ver OPEN_QUESTIONS #3).
- **(Fase 15)** Concurrencia multi-proceso sobre `BusinessCoreEngine`
  (el lock es intra-proceso, ver NEW_GAPS_FOUND.md #4).
- **(Fase 15)** Persistencia de sesiones de onboarding (viven en memoria
  del proceso del bridge, ver NEW_GAPS_FOUND.md #5).
- **(Fase 15)** Ningún conector real (todo mock/sandbox) — no hay
  verificación contra un sistema externo de verdad todavía.
