# CONTEXT_LEDGER — qué se ha leído y por qué (para no releer)

Guía de lectura mínima para retomar sin quemar contexto. Actualizar solo con
rutas + una línea de para qué sirve.

## Lecturas hechas (sesión 2026-07-10)

- `AGENTS.md` — operating loop, invariantes (Merkle, governance.json intocable,
  no deps nuevas sin ADR), naming técnico, comandos clave.
- `WORK_LEDGER.md` (top) — campaña x10 activa; suite verde 1.9GB; primera
  convergencia autónoma del lazo.
- `docs/handoff/atlas_fable5_handoff_v1/README_USE_THIS_FIRST.md` y
  `docs/handoff/atlas_build_pack/README.md` — orden de construcción.
- `docs/handoff/atlas_build_pack/docs/atlas-bible/{02,08,14,17,20}` — mapa,
  bridge, stack, fases, implementation map. Resto de la bible: leer bajo
  demanda, son cortos.
- `docs/handoff/atlas_build_pack/schemas/event.schema.json` — base del canon.
- `src/atlas/core/event_bus.py` (completo, 47 líneas) y `core/contracts.py`
  (Event/EventType) — el bus real.
- `src/atlas/interfaces/dashboard.py` (cabecera + rutas) — app FastAPI real,
  singleton Orchestrator inyectado, bug doble-Orchestrator documentado ahí.
- `src/atlas/interfaces/exec_api.py` (cabecera + rutas) — HMAC exec + Merkle
  endpoints.
- Grafo vivo: importers de event_bus (orchestrator, hermes_webhook) y de
  dashboard (cli, runtime.service_runner).

## Para archivos grandes

- `core/orchestrator.py`, `memory/*`: NO leídos enteros — usar grafo
  (graph_importers/graph_blast_radius) y grep dirigido antes de abrir.
