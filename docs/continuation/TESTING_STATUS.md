# TESTING_STATUS — Atlas OS (2026-07-10)

## Suites del frente OS

| Suite | Tests | Estado | Cubre |
| --- | --- | --- | --- |
| tests/test_os_event_schema.py | 13 | ✅ verde | paridad modelo↔JSON Schema, 6 fixtures, grafo, rechazos |
| tests/test_os_event_store.py | 7 | ✅ verde | store/listeners, player (simulated, anti-merkle, missing), bridge core |
| tests/test_os_api.py | 15 | ✅ verde | endpoints, WS tail+push, guard anti-Orchestrator, fail-closed, traversal |
| tests/test_os_memory_import.py | 4 | ✅ verde | raw preservado, conformidad schema, idempotencia, eventos reales |

Comando: `PYTHONPATH=src ATLAS_NESTED_TEST_RUN=1 python -m pytest tests/test_os_*.py -q`

## Tipos y build

- `MYPYPATH=src mypy src/atlas/api/ src/atlas/events/` → limpio (strict).
- `ui/atlas-shell: npm run build` (tsc strict + vite) → limpio.

## Verificación en vivo hecha esta sesión (no solo tests)

- Bridge smoke por curl: /health, /intent (pipeline 10 eventos), /graph,
  /memory/summary (338 registros REALES del índice canónico).
- UI conducida con navegador real: WS conectado, fixture demo_first_run
  reproducido, pipeline encadenado visible, tema dark↔light con persistencia,
  Integration Fabric con 5 conectores mock (capturas en el chat de la sesión).
- Suite completa del repo lanzada al cierre (resultado en IMPLEMENTATION_LOG).

## Qué NO está probado (honesto)

- La UI no tiene tests automatizados (ni unit ni e2e) — solo verificación
  manual dirigida. Candidato: vitest para event-reducer.ts (dominio puro).
- El WS bajo carga/reconexión prolongada (backoff implementado, no estresado).
- kuzu/grafo real en /graph (no cableado aún, ver OPEN_QUESTIONS #3).
