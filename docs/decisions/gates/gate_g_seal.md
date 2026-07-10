# Gate G — Seal

**Date:** 2026-05-25
**Status:** COMPLETE
**Tests:** 513/513 passing
**mypy:** green on 44 source files
**Tag:** `v0.6-gate-g`

## Summary

Gate G closes the operational readiness pass after Gate F. The objective was to
make Atlas usable as a local runtime rather than only as a tested core.

## Delivered

| Area | Result |
|---|---|
| Hermes-VPS | CPX22 service restored; Docker container healthy; `scripts/hermes_smoke.py` PASS over Tailscale. |
| GitHub release state | `main` and `v0.5-gate-f` pushed before Gate G work; Gate G will be pushed as `v0.6-gate-g`. |
| CLI approvals | Pending approvals persist to disk under `memory/pending_approvals`; `atlas pending` and `atlas approve <task_id>` work across process restarts. |
| Telegram | Token stored in local `.env`; `TELEGRAM_CHAT_ID` discovered from `/start`; authorizer accepts env chat id; outbound Telegram smoke PASS. |
| Versioning | Atlas version bumped to `0.6.0`. |
| Continuity docs | `ROADMAP.md`, `AGENTS.md`, `memory/system_context/03_adr.md`, README and usage docs updated. |

## Evidence

```bash
PYTHONPATH=src python scripts/hermes_smoke.py
# -> OK

PYTHONPATH=src python -m pytest tests/ -q
# -> 513 passed

MYPYPATH=src python -m mypy src/atlas/
# -> Success: no issues found in 44 source files
```

Telegram smoke:

- `getMe` returned `GodAtlas_bot`;
- `getUpdates` returned the authorized private chat after `/start`;
- `TelegramAuthorizer.from_permission_profile()` accepted `TELEGRAM_CHAT_ID`
  from `.env`;
- `TelegramClient.send_message()` delivered a Gate G smoke message.

## Follow-Ups

- Gate H: ColdUpdateManager MVP (patch intake, isolated worktree, validation,
  HITL, no autonomous code generation initially).
- Observability v2: correlation ids across Orchestrator, BrowserTool,
  EditorTool, Telegram and Hermes.
- Optional manual Telegram UX smoke for `/status`, `/task`, `/pending` and
  inline approve/deny.
