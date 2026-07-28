# Atlas Definitive Convergence Report

Date: 2026-07-28

## Outcome

Atlas has one reviewable **ATLAS DEFINITIVE CANDIDATE**. It is not
`ATLAS CANON ACCEPTED`; that elevation remains an explicit operator action.

- Base: `c95038c9d7e97ddc6339f38abe6dad09b166f47d`
- Current substantive validation anchor:
  `aa71a980cef53f1a9ddf1374615a461c0eadfa0c`
- Branch: `codex/atlas-definitive-convergence-20260727-154020`
- Worktree: `/home/ronin/proyectos/atlas-definitive-convergence`
- Canonical implementation target: Atlas Core

The delivery-artifact commit is deliberately excluded from its own commit
inventory and patch. The final bundle contains it; the review patch and
validation anchor stop at `aa71a98` to avoid self-referential evidence.

`ATLAS.md` is the sole human entry. `docs/canon/authority_registry.yaml` is
the machine discovery entry. `VISION.md`, `ARCHITECTURE.md`, `PROGRAMS.md`,
`PLAN.md` and `STATUS.md` remain projections over scoped authority rather than
a replacement constitution.

## Preservation

The original Atlas Core checkout was never used as a work surface. Its base
HEAD, dirty sources and secret-safe backup were preserved before this branch
was created.

- Backup root: `/home/ronin/proyectos/atlas-definitive-backup`
- Pre-convergence bundle: `atlas-before-definitive.bundle`, verified
- Tracked/staged patches and secret-safe untracked archive: preserved
- R2.1 package: immutable input; expected SHA-256 and ZIP CRC verified

## Convergence delivered

- The 13 permanent programs P00–P12 remain explicit; no program was collapsed
  into a temporary wave.
- All 56 ADR source files have a disposition. ADR-076 A/B remain accepted and
  opt-in; C remains rejected, absent and unimplemented. ADR-077 preserves the
  high-sensitivity human boundary.
- ADR-078 fixes the first product/desktop-host decision without claiming that
  a donor repository is already integrated: Atlas Engineering Workbench uses a
  CodeOSS/VSCodium host path, Void is a capability donor, and Zed is an
  ACP/pattern donor.
- 32 product/construction lineages, 137 component/capability reality records,
  124 conflict records, and explicit supersessions prevent topology or prose
  from becoming implementation truth.
- Evidence governance is now machine-enforced: 19 evidence sources, four
  decision matrices and four dossiers make ADR-057, ADR-058, ADR-069 and
  ADR-078 explicitly `PROVISIONAL` rather than overclaimed.
- Canon validation now rejects evidence-reference drift, unsafe local evidence
  paths, insufficient corroboration, decision-gated `READY` work orders, and
  incompatible operator-question blockers.
- Optional adapters now validate `fal_client` response shape at the boundary;
  lazy ACP binding no longer weakens the strict type gate.

The branch introduced no project dependency and did not modify
`config/governance.json`.

## Current validation

At `aa71a98`:

- direct core suite: 4522 passed, 57 skipped, 1 deselected, 1 warning;
- extended Reality rerun: same core result, strict mypy clean across 318
  source files, and `computer_use` skipped because Playwright is absent;
- canon: 2085 JSONL records and 25 integrity tests pass;
- docs index: no missing/orphan/stale entries (912 entries);
- Merkle audit, doctor and health exit successfully with explicit external
  integration warnings;
- UI exact install, build and high-severity audit pass with zero known
  vulnerabilities;
- `uv lock --check` and `pip-audit --strict` pass; no known Python dependency
  vulnerability is reported;
- sanitation finds no unclassified code vapor.

Runtime limits are intentionally not promoted: browser is degraded without
Playwright; Hermes is mock/unconfigured/not live; two MCP servers are only
configured, not handshake-verified; external providers are absent; F2.6 has
never run; and the shared structural graph remains stale against the candidate
because it was not overwritten from the isolated worktree.

## Review and integration

1. Inspect `ATLAS.md`, `STATUS.md`, ADR-078 and the adversarial audit.
2. Verify the new bundle and SHA-256 from
   `/home/ronin/proyectos/atlas-definitive-backup`.
3. Review the atomic commit list and `FINAL_DIFF.patch` at its documented
   anchor.
4. Resolve only operator-owned decisions that should alter the candidate.
5. If accepted, merge through the protected-main workflow; do not fast-forward
   the preserved original checkout.
6. Rebuild the structural graph on the integrated commit, rerun Reality, and
   only then promote graph freshness or live-service claims.
