---
name: atlas-audit
description: Record meaningful Hermes actions in Atlas's tamper-evident Merkle ledger.
---

# atlas-audit

Hermes runs unaudited by default. Atlas keeps an append-only, hash-chained
Merkle ledger of everything it does. This skill lets Hermes write its own
actions into that same chain, so the twin has one forensic record of both
hemispheres (ADR-029, reverse twin direction).

## When to use

After completing any action with side effects or worth remembering:
- a skill run (`skill.run`)
- a Telegram reply that took an external action (`telegram.action`)
- a cron tick (`cron.tick`)
- a delegation to Atlas (`atlas.delegated`)

Do **not** audit pure small-talk replies — keep the ledger signal-rich.

## How

Run the client with the action, an outcome, a risk level, and an optional
JSON payload of structured facts:

```bash
python3 ~/.hermes/skills/atlas-audit/atlas_audit.py \
    --action skill.run \
    --result success \
    --risk moderate \
    --payload '{"skill": "weather", "city": "Madrid", "duration_ms": 812}'
```

`--result` ∈ {success, failure, blocked, pending, refused}
`--risk`   ∈ {safe, moderate, high, critical}

The action is automatically namespaced under `hermes.` on the Atlas side, so a
Hermes-origin record can never be confused with an Atlas-native one. The
command prints a JSON receipt with the chained hash:

```json
{"ok": true, "id": "...", "action": "hermes.skill.run", "hash_self": "...", "hash_prev": "..."}
```

## Requirements

- `HERMES_API_KEY` in the environment (the same shared secret the inbound
  `/api/exec/*` endpoints use).
- Atlas reachable over Tailscale (`http://100.85.236.58:7331`). Override with
  `ATLAS_AUDIT_URL` if the address changes.
- If Atlas is offline the client exits non-zero and prints why; treat audit as
  best-effort — never block a user-facing reply on it.
