# Gate G — Operational Readiness

**Status:** in progress
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
- CLI approvals are persistent across process restarts.
- `atlas pending` lists persisted approvals.
- `atlas approve <task_id>` approves or rejects persisted approvals.

## Pending

- The operator must send `/start` or any message to `GodAtlas_bot` once, so
  Telegram exposes the `chat_id` through `getUpdates`.
- After that, set `TELEGRAM_CHAT_ID` in `.env` and run a Telegram smoke:
  `/status`, `/task`, `/pending`, approve and deny.

## Evidence So Far

```bash
PYTHONPATH=src python scripts/hermes_smoke.py
# -> OK

PYTHONPATH=src python -m pytest tests/test_cli_gate_g.py \
  tests/test_telegram_bot.py tests/test_telegram_orchestrator.py \
  tests/test_orchestrator_gate_f.py -q
# -> 42 passed

PYTHONPATH=src python -m pytest tests/ -q
# -> 512 passed

MYPYPATH=src python -m mypy src/atlas/
# -> Success: no issues found in 44 source files
```
