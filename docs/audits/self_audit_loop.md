# Atlas Self-Audit Loop

Atlas self-audit is a cold, auditable maintenance loop. It observes the repo,
runtime health and environment fingerprint, records findings, and writes
candidate improvements. It does not hot-patch Atlas and it does not merge into
`main`.

## Run

```bash
set -a && source .env && set +a
PYTHONPATH=src atlas self-audit run --hours 24 --profile full
```

Smoke one cycle before a long run:

```bash
PYTHONPATH=src atlas self-audit run --hours 1 --profile quick --max-cycles 1 --dry-run
```

## Inspect

```bash
atlas self-audit status
atlas self-audit proposals
atlas self-audit report
atlas self-audit stop
```

Reports are written to:

- `docs/self_audit_latest.json`
- `docs/self_audit_YYYY-MM-DD.md`

Every cycle, stop request and final report is logged to Merkle.

## Safety model

- No hot self-patching.
- No automatic merge to `main`.
- No changes to `.env`, `governance.json`, secrets or systemd units.
- Candidate patches must go through ADR-025 ColdUpdate validation.
- Validated changes may be promoted only in an isolated branch/worktree until
  human review approves a final merge.
