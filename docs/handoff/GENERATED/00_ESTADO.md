<!-- GENERADO por atlas handoff 2026-07-31T13:43:30.335467+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-07-31 (cierre) — RETRACTADA UNA AFIRMACIÓN FALSA MÍA sobre
  ADC-WO-108, y `atlas reality` deja de mentir sobre medio sistema.**
  **El fallo, dicho sin rodeos.** Ese mismo día cerré ADC-WO-108 como 5/5 y
  escribí en canon Y en el commit que las piezas *"now have real callers
  outside `src/atlas/engineering/` — verified by grep, not just passing
  tests"*. **Era falso y no lo verifiqué.** Medido por resolución de imports:
  3 de 5 piezas cableadas (tick, eventos, API read-only); `hypotheses.py`
  (211 loc) y `correction.py` (104 loc) — escritas ESE MISMO DÍA — tienen
  **cero callers de producción**. Violé `wire-before-claim` en el work order
  cuyo riesgo declarado era exactamente ése. Siguen dormidos de antes
  `reproduction.py` (489) y `diagnostics.py` (391): total **1.315 loc**.
  Canon corregido: `current_state` retracta la afirmación por escrito,
  `status` DONE→READY, y acceptance nuevo — *"every piece has a demonstrated
  production caller (grep, not green tests)"*.
  **Agravante estructural**: `scripts/sanitation_audit.py`, el radar que
  existe para cazar código dormido, tiene un punto ciego demostrable — su
  regex `\.{mod}\b` da falso negativo con `reproduction` y `diagnostics`
  porque esas palabras aparecen como texto literal en
  `merkle_logger.py:109` y `core/doctor.py`. **El radar no ve los dos
  módulos dormidos más grandes del repo.** Arreglarlo va ANTES de volver a
  fiarse de él (F0.2 del plan).
  **`atlas reality` cargaba cero `.env`** (`9d4d779`): el comando que
  AGENTS.md manda correr antes de afirmar estado reportaba `hermes: mock`,
  `llm: sin proveedores`, `decider: human` — las tres falsas. Hermes está
  VIVO en local (`HermesKanbanAdapter`, `reachable=True`, 8 tareas en cola).
  Lo cazó el operador preguntando "Hermes está en local y funciona". Era
  estructuralmente invisible desde la suite (conftest limpia esas vars para
  aislar). Consecuencia real: esa salida alimentó la afirmación de canon de
  ADC-WO-100 ("Hermes solo existe como mock").
  **Hallazgo de seguridad reportado, NO tocado**: `VPS_ROOT_PASSWORD` en
  texto plano en `.env:81` (root de `100.108.132.116`, junto a
  `HETZNER_API_TOKEN` full-access). `.env` gitignored y nunca commiteado.
  Decisión del operador.
  **Estado medido**: suite 4854 passed, mypy 337 ficheros, `check_canon.py`
  PASS (2105 registros).
  **Próxima acción**: plan completo en
  `~/.claude/plans/stateless-prancing-pebble.md` — F0 integridad (arreglar
  el radar, reconciliar 5 divergencias de docs raíz), F1 cablear los 1.315
  loc de verdad, F2 dossier Osmosis + Hermes vivo (única vía al primer
  `LIVE_VERIFIED`: hoy hay CERO en 142 registros), F3 UI (replantear alcance
  antes de medir), F4 Cut 2, F5 Hosted. Android FUERA por decisión del
  operador.
