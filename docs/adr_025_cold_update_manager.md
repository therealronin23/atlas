# ADR-025 — ColdUpdateManager

**Status:** SEALED (MVP v1, 2026-05-25).
**Context:** `grok.md` repeatedly rejects hot self-patching and recommends a
controlled cold-update protocol for Atlas self-improvement.

## Decision To Make

Whether Atlas should support self-improvement only through an isolated,
auditable, human-approved update flow.

## Non-Negotiables

- No self-AST patching.
- No runtime mutation of Governance L0.
- No automatic merge without HITL.
- No command execution outside AtlasExecutor.
- No update is valid unless tests and type checks run.

## Proposed Protocol

1. **Freeze intent**: record improvement request in MerkleLogger.
2. **Snapshot**: record TimeTravel checkpoint and git state.
3. **Isolate**: create a worktree or isolated copy.
4. **Generate**: produce a patch in the isolated area.
5. **Validate**: run focused tests, full suite, mypy and optional benchmarks.
6. **Review**: present summary, risk, diff and evidence to CLI/Telegram.
7. **Approve**: require explicit human approval.
8. **Apply**: merge/swap only after approval.
9. **Rollback**: revert/switch back automatically if post-apply checks fail.
10. **Seal**: log outcome and evidence.

## Candidate Modules

- `src/atlas/core/cold_update_manager.py`
- `src/atlas/core/worktree_manager.py`
- `src/atlas/core/validation_runner.py`
- `src/atlas/interfaces/update_review.py`

## First Safe MVP

The MVP should not generate code autonomously. It should:

1. create an isolated worktree;
2. accept an existing patch;
3. run tests/mypy;
4. produce an approval report;
5. log everything.

Only after this is stable should Atlas generate candidate patches itself.

## Open Questions

- Should this live in Gate F or Gate G?
- What benchmark gates matter beyond tests/mypy?
- Which directories are allowed for self-improvement?
- How does this interact with GitHub PR creation?

