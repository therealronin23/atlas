<!-- GENERADO por atlas handoff 2026-07-22T12:12:37.171784+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **ATLAS PRIME Cycle 10 — recuperado y cerrado el worktree abandonado
  `feat/atlas-engine-program` (2026-07-22 14:15)** — investigado a petición
  del operador tras el hallazgo de Cycle 9 (worktree con ~2 días de trabajo
  sin commitear). Diagnóstico: rama 1 commit por delante de `main`
  (`e57744aa`) + WIP real de la fase A2 (PluginManifest declarativo +
  admisión staged, ADR-072/073), capturada a mitad de un ciclo TDD — 59/60
  tests, el único rojo (`test_trial_gate_does_not_promote_unstaged_local_
  third_party_mcp`) documentaba exactamente el invariante que el propio WIP
  añadía a `MEMORY.md` (`staged-artifact-is-not-an-argv`) pero el código aún
  no lo aplicaba en `_trial_mcp_install()`: un módulo de terceros con argv
  "limpio" (p.ej. `python -m third_party_mcp`, no dispara
  `requires_network_bootstrap` por no ser npx/uvx) pasaba el trial sin
  verificación real de spawn. Fix: `is_atlas_native_module(cmd)` distingue
  código propio (confiable sin spawn) de terceros (exige staging). 60/60 en
  el worktree, cerrado con commit propio en la rama (`9384cea3` en ese
  checkout). Sin colisión con nada de hoy (verificado: `main` no tocó
  ninguno de estos ficheros en toda la sesión). Traído a `main` limpio (11
  ficheros del feature — `plugin_admission.py`, `plugin_manifest.py`,
  `supply_chain.py`/`_models.py`, `static_content.py`, ADR-072/073, 2 schemas
  nuevos, tests) sin tocar `WORK_LEDGER.md`/`MEMORY.md` de la rama (ambos
  desactualizados frente a hoy — reescritos aquí en su lugar). **Suite
  completa en `main` tras el merge: 3684 passed, 0 failed.** mypy --strict
  global limpio salvo `trunk_capabilities.py` (6 errores preexistentes,
  confirmados sin relación vía `git stash`, no tocados).
  **Estado nuevo declarado:** Supply-chain admission scan (A1, PENDIENTE) +
  Declarative PluginManifest v1 (A2, PENDIENTE) en
  `docs/design/atlas_ecosystem_map.md`. **Próxima acción:** A3 (materializador
  de procedencia inmutable + receipt Merkle/HITL + activador reversible,
  ADR-073) — o T0.5b paso 2 / las 4 decisiones toasty.
