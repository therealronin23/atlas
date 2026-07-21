# ADR-072 — Canonical governance and Atlas Hosted convergence

- **Status**: proposed (DOC-0 RC2, 2026-07-21)
- **Target base**: `d01d4b931fd7f02af81a32c63c889d35f574fcab`
- **Supersedes after acceptance**: ADR-067 for constitutional authority.
- **Does not supersede**: accepted technical ADRs unless an individual claim or
  later ADR says so explicitly.

## Context

Atlas has a large and valuable corpus but several document families have acted
as constitutions at different times: AGENTS, architecture maps, Atlas Bible,
Product OS packs, handoffs, continuation snapshots and ADRs. Implementation
closure of the three imported packs did not equal semantic absorption of every
idea. The result is distributed authority without one compiled registry.

Since ADR-067, the repository also accepted ADR-068 through ADR-071: F5/F6 were
reframed for self-construction, Mission Layer and Golden Route became real,
legacy Hermes REST was retired and final UX moved from web-first to dedicated
Linux and Android applications. Any replacement canon must include those later
facts rather than freeze the repository at the earlier F15/F16 snapshot.

## Decision

1. `ATLAS.md` is the human entrypoint.
2. `docs/canon/ATLAS_CLAIMS.yaml` is the machine registry of accepted,
   proposed, parked, rejected, superseded and unresolved claims.
3. `ATLAS_PRECEDENCE.yaml` defines authority order.
4. Canon direction and live operational reality remain separate.
5. New documents default to `propuesto` until explicitly classified.
6. Handoffs, prompts, packs and filenames do not grant authority.
7. Every mutable state is assigned one current and one target authority in the
   Authority Ledger; split authority is migration debt, not silently accepted
   architecture.
8. Source implementation accounting and semantic absorption remain separate.
9. Atlas Hosted converges through the six-layer target architecture and the
   DOC/H roadmap. No total rewrite is authorized.
10. RC2 remains a candidate until this ADR is accepted and merged.

## Consequences

- ADR-067 remains historical rationale but no longer defines constitutional
  authority after acceptance.
- Existing ADRs, contracts, code and tests keep their scoped authority.
- The repository gains a strict auditor and inventory that expose missing
  references, duplicate authority, uncovered docs and incomplete absorption.
- Historical sources remain in place until their claims are classified.

## Acceptance gate

- Apply in an isolated non-main worktree at the target commit.
- `git apply --check` and rollback check pass.
- `scripts/canon_audit.py --strict` passes.
- `scripts/canon_inventory.py --strict` reports no unclassified file paths.
- Updated `scripts/docs_index_audit.py --strict` passes.
- Relevant tests pass without changing runtime behavior.
- Operator reviews the claim summary and changes this status to `accepted` in
  the same merge that adopts the canon.
