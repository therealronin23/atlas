# Self Audit Report — self-audit-20260621-125713

- Status: `running`
- Profile: `full`
- Started: `2026-06-21T12:57:13.111508+00:00`
- Finished: `2026-06-21T12:57:13.259898+00:00`
- Cycles: `1`

## Findings

- **high** `resilience` — Tracked worktree changes present: Start the 24h loop from a clean tracked worktree.
- **medium** `security` — .claude directory is untracked: Do not include .claude/ in self-audit patches.

## Candidates

- `needs_patch` **high** — Resolve Tracked worktree changes present
- `needs_patch` **medium** — Resolve .claude directory is untracked
