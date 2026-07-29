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

> **Nota (2026-06-04, ADR-039 slice 7):** Atlas ya genera patches candidatos
> (`CodegenProposer`). Esto **no** relaja el "no autonomous code generation":
> entra como *post-MVP* y **solo** como patch revisable, gateado idéntico a un
> patch manual — generación libre, **aplicación nunca autónoma**. El objetivo lo
> apunta el humano (`CodegenTarget`), el patch se restringe fail-closed al fichero
> apuntado, y la adopción exige el seam del decisor (ADR-040). La invariante de
> este ADR sigue intacta: el ejecutor solo aplica tras validación + aprobación.

## Open Questions

- Should this live in Gate F or Gate G?
- What benchmark gates matter beyond tests/mypy?
- Which directories are allowed for self-improvement?
- How does this interact with GitHub PR creation?

## Hardening compatible with this ADR (2026-07-29)

The existing narrow self-maintenance scope is now enforced at the actual patch
intake boundary, not merely declared by a constant in the manager. A candidate
patch must be a UTF-8 unified text diff whose paths are confined to
`src/`, `tests/`, `scripts/`, `docs/` or `config/`; the single root exception
is `pyproject.toml`, required by the accepted ADR-039 dependency-bump path.
`config/governance.json` is denied for every origin. Traversal, absolute or
ambiguous paths, binary diffs, symlinks/submodules, and rename/copy forms fail
closed before a worktree is created.

The stored patch is SHA-256 bound to its proposal. Validation, approval, apply,
tier-1 processing and rollback re-check both scope and digest, so an approval
cannot be reused if the stored artifact changed. Ledger entries written before
the digest field are intentionally non-applicable and must be re-proposed.

This is an intake/integrity guard, not a claim that diff text is safe to run.
It does not weaken the existing Bwrap/AST Guard, validation, Decider, human
approval, Merkle or rollback requirements; it gives those later gates the same
reviewed artifact and prevents a patch from reaching them outside its allowed
scope.
