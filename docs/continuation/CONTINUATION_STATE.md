# CONTINUATION_STATE — Atlas OS

Actualizado: 2026-07-11 (sesión Fable 5, Fase 15 — Product OS).

## Current Status

Sobre la base final-compatible del 2026-07-10 (Event Kernel, Backend
Bridge, UI shell, governance inicial), Fase 15 añade el sustrato de
producto exigido por `atlas_product_os_liquid_ui_pack_v1`: Integration
Fabric + Easy Connection Layer, PolicyEngine determinista, Atlas Business
Core draft-first, Adaptive Question Engine, Legacy Link Layer. 22 schemas,
152 tests OS, todo con verificación en vivo (bridge real + CLI real).
Detalle completo en `docs/continuation/phase15/PHASE_15_COMPLETION_REPORT.md`.

## What Is Real

- Todo lo de la sesión anterior (ver historial de este fichero en git).
- **Integration Fabric**: RecipeEngine/PackEngine cargan y validan de
  verdad (rechazan recetas inseguras, no las sirven a medias);
  ConnectionConcierge genera un plan real desde una receta + PolicyEngine;
  AuthBroker rechaza de verdad valores con forma de secreto; ConnectorRegistry
  detecta rug-pull por hash real de descriptor.
- **PolicyEngine**: 7 invariantes duros en código (no en fixture),
  probados a que sobrevivan a borrar/vaciar `fixtures/security/policies.json`.
- **Business Core**: `create_draft→request_activation→approve_activation`
  es el único camino real a `active` (probado que saltarse un paso lanza
  error); `promote_candidate` exige revisión humana real.
- **Question Engine**: el lazo pregunta→interpreta→confirma es código real
  que rechaza avanzar sin confirmación (no solo un comentario de intención).
- Bridge real probado con `ATLAS_HOME` aislado + curl real:
  `/connections/catalog`, `/connections/plan`, `/business/question-packs`.
- CLI real ejecutada (no solo importada): `atlas connections {catalog,plan,test}`,
  `atlas business {question-packs,onboarding-start}`.

## What Is Simulated

- Todo lo de la sesión anterior sigue simulado igual (intent pipeline,
  conectores Fase 4-9, /graph fixture).
- **Todos los conectores del Integration Fabric son mock/sandbox**;
  `mode=real` siempre `BLOCKED_BY_MISSING_DEPENDENCY`.
- Los `EntityCandidate` de los fixtures son datos demo explícitos.
- `BusinessCore.activation.gate_id` es descriptivo — NO hay ceremonia de
  Gate Engine real todavía (gap #3, Fase 16).

## What Was Changed

6 commits Fase 15 en `main` (sin push):
`bac77283`→`50293445`→`986c77f0`→`63932f44`→`13f724f8`→`cd3fd214`.
Ficheros core tocados (aditivo, mínimo): `src/atlas/api/server.py` (registra
product_routes), `src/atlas/interfaces/cli.py` (+2 grupos), `tests/test_os_api.py`
(guard ampliado a fabric/business + gates=12), `tests/test_os_event_schema.py`
(schemas=22). `fixtures/governance/gates.json` ampliado con 8 gates (gap #1
del cierre, ver NEW_GAPS_FOUND.md — encontrado y fijado en la misma fase).

## Architecture Decisions Made (Fase 15)

- ADR-060 (Integration Fabric + Easy Connection Layer + PolicyEngine).
- ADR-061 (Business Core draft-first + Question Engine + Legacy Link).
- DECISION_REVIEW.md D11-D14 (incluye D11: rediseño JARVIS del shell
  SUPERSEDED por el pack de producto — nunca se llegó a implementar).

## Risks

Ver docs/risks/RISK_REGISTER.md (OS-R1..R11 + P15-R1..R12 en
`docs/continuation/phase15/PHASE_15_RISK_REVIEW.md`). Nuevo letal
verificado en esta fase: import circular fabric↔api si algo bajo
`atlas.fabric.*`/`atlas.business.*` importa `atlas.api.*` a nivel de
módulo (ADR-060 documenta el fix — `TYPE_CHECKING` + import perezoso).

## Next Best Tasks

Ver `docs/continuation/phase15/RECOMMENDED_PHASE_16.md` (prioridad 1-8,
con justificación). Resumen: converger PolicyEngine con el evaluador v1,
Gate Engine real para activaciones, persistir sesiones de onboarding,
primer conector real (Gmail read-only), Sector/Objective Registry formales.

## How To Run

```bash
cd ~/proyectos/atlas-core && source .venv/bin/activate
PYTHONPATH=src atlas os-bridge          # bridge en 127.0.0.1:7341
cd ui/atlas-shell && npm install && npm run dev   # shell en 127.0.0.1:5173 (ARNÉS, ver su README)
```

## How To Test

```bash
PYTHONPATH=src ATLAS_NESTED_TEST_RUN=1 python -m pytest tests/test_os_*.py -q   # 152 passed
MYPYPATH=src python -m mypy src/atlas/api/ src/atlas/events/ src/atlas/fabric/ src/atlas/business/ src/atlas/interfaces/cli.py
cd ui/atlas-shell && npm run build      # tsc strict + vite (sin cambios esta fase)
```

## Known Failures

- Ninguno en los 152 tests OS al cierre de Fase 15. Anomalía pre-existente
  del repo sin relación: multihop=0.0 en eval_longmemeval (anotada en ledger).

## Where To Continue

Leer EN ORDEN: este doc → `docs/continuation/phase15/PHASE_15_COMPLETION_REPORT.md`
→ `docs/continuation/phase15/NEW_GAPS_FOUND.md` → ADR-060/061 → el código
de `src/atlas/fabric/` y `src/atlas/business/` (pequeño a propósito).

## Warning To Next AI

Todo lo de la sesión anterior sigue aplicando (NO Orchestrator en el
bridge/fabric/business, NO tocar ficheros del operador, NO `git add -A`,
NO inventar merkle_hash, NO deps Python sin ADR, regenerar INDEX.yaml).
Añadido en Fase 15: NO importar `atlas.api.*` a nivel de módulo desde
`atlas.fabric.*`/`atlas.business.*` (círculo real, ya ocurrió — usa
`TYPE_CHECKING` + import perezoso si hace falta un tipo de `atlas.api.models`).
NO construyas `BusinessCoreEngine`/`AuthBroker`/`ConnectorRegistry` en un
test sin pasar `path`/`refs_path`/`approvals_path` explícito bajo
`tmp_path` — sin eso escriben en el `$ATLAS_HOME` real (ya casi pasó esta
fase, se cazó antes de ejecutar).
