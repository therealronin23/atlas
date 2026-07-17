# T5.1 Smoke de proveedores — cierre por AFLORAMIENTO (mini-plan)

**Recon 2026-07-17 (bootstrap, 20 min):** T5.1 "smoke diario de cadena" YA existe
y funciona — `ProviderChainSmoke` (src/atlas/core/self_maintenance/provider_smoke.py,
2026-07-09) + `maintenance_provider_smoke_tick` (maintenance_facade.py:542),
opt-in `ATLAS_PROVIDER_SMOKE=1` (presente en .env línea 130), cadencia propia
24h, resultado persistido en `workspace/self_build/provider_smoke_state.json`
+ Merkle. Corrió HOY 00:36Z: 12 ok, 1 failed (openrouter_qwen3_coder_free,
429 upstream), 1 skipped (together_free sin key). El plan maestro §T5.1
("pendiente desde 2026-07-08") está CADUCADO — trampa doctrina §3
"afirmación punto-en-tiempo sin caducidad".

**El gap real:** la detección muere en un JSON que nadie mira. `atlas reality
--json` (lo primero que corre cada driver, por ley de AGENTS.md) dice "run
inference_smoke for live evidence" ignorando la evidencia viva de hoy.
"Detecta antes que un humano" exige que un humano/driver lo VEA sin buscarlo.

**Goal:** una sección `provider_smoke` en `atlas reality --json` que proyecte el
último resultado del smoke del daemon. Cero llamadas de red nuevas (solo lee el
state file). Fail-honesto: sin fichero → `never_ran` (+ hint del env flag).

**Tech:** Python 3.12, reality.py existente, pytest, mypy --strict.

## Global Constraints

- Tests dirigidos: `ATLAS_NESTED_TEST_RUN=1 PYTHONPATH=src .venv/bin/python -m pytest tests/test_reality.py -q` (JAMÁS suite completa). mypy --strict en reality.py.
- Sin dependencias nuevas. Sin red. Un commit.

### Task única: sección provider_smoke en reality

**Files:** Modify: `src/atlas/core/reality.py`; Test: el fichero de tests de reality existente.

- Produces: clave `provider_smoke` en el snapshot: `{"status": "ran"|"never_ran", "last_run_date": str|None, "ok": [names], "dead": [names], "skipped": [names], "reason": str}`. `dead` no vacío → `status_reason` lo nombra. State file ilegible/corrupto → `never_ran` con reason honesta, jamás excepción.
- Ruta del state: `<repo_root>/workspace/self_build/provider_smoke_state.json` (la misma convención que usa maintenance_facade `_project_root()`).
- TDD rojo→verde: fixture tmp con state real (1 dead) → sección correcta; sin fichero → never_ran; JSON corrupto → never_ran sin crash.
- Evidencia de cierre T5.1: `atlas reality --json | jq .provider_smoke` muestra el failed de HOY sin lanzar ninguna llamada.
