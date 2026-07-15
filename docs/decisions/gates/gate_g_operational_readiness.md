# Gate G — Operational Readiness

> **Snapshot histórico del 2026-05-25.** No es un runbook vigente ni evidencia
> de conectividad actual. Las rutas Hermes REST/Docker quedaron como
> compatibilidad histórica; consultar ADR-026..029 y
> `docs/operations/operational_runbook.md`.

**Status:** complete
**Date:** 2026-05-25

Gate G turns the sealed Gate F core into a usable local operating loop. The
goal is not new autonomy; it is reliable operations.

## Done

- Hermes-VPS on Hetzner CPX22 is reachable through Tailscale again.
- `scripts/hermes_smoke.py` passes against `HERMES_BASE_URL`.
- GitHub `main` and tag `v0.5-gate-f` are pushed.
- Telegram bot token is present in local `.env`.
- Telegram authorizer can merge `TELEGRAM_CHAT_ID` from `.env` with
  `permissions.yaml`.
- Telegram chat authorization is configured locally.
- Real Telegram outbound smoke passed.
- CLI approvals are persistent across process restarts.
- `atlas pending` lists persisted approvals.
- `atlas approve <task_id>` approves or rejects persisted approvals.

## Operational runbook

See [operational_runbook.md](operational_runbook.md) and `scripts/operational_smoke.py`
for the full Sesion A checklist (automated + manual CLI/Telegram).

## Remaining Follow-Up

- Full interactive Telegram command smoke (`/status`, `/task`, `/pending`,
  approve and deny) should be run manually from the Telegram client when desired.
  The bot token, chat authorization and outbound send path are verified via
  `operational_smoke.py` (outbound) and the runbook (interactive).

## Evidence So Far

```bash
PYTHONPATH=src python scripts/hermes_smoke.py
# -> OK

PYTHONPATH=src python -m pytest tests/test_cli_gate_g.py \
  tests/test_telegram_bot.py tests/test_telegram_orchestrator.py \
  tests/test_orchestrator_gate_f.py -q
# -> 42 passed

PYTHONPATH=src python -m pytest tests/ -q
# -> 513 passed

MYPYPATH=src python -m mypy src/atlas/
# -> Success: no issues found in 44 source files
```
