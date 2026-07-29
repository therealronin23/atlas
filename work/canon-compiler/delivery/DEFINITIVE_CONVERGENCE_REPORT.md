# Atlas Definitive Convergence Report

Date: 2026-07-29

## Outcome

Atlas has one reviewable **ATLAS DEFINITIVE CANDIDATE**. It is not
`ATLAS CANON ACCEPTED`; that elevation remains an explicit operator action.

- Base: `c95038c9d7e97ddc6339f38abe6dad09b166f47d`
- Current substantive validation anchor:
  `fac6bca34831533ae248564adf615e052c59be16`
- Branch: `codex/atlas-definitive-integration-20260728-230000`
- Worktree: `/home/ronin/proyectos/atlas-definitive-integration`
- Substantive local commits: 44
- Canonical implementation target: Atlas Core

The delivery-artifact commit is deliberately excluded from its own commit
inventory and patch. The final bundle contains it; the review patch and
validation anchor stop at `fac6bca` to avoid self-referential evidence.

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
- The generated `atlas-trunk` command now crosses Sentinel's governed-native
  admission boundary; its own child registry still vets each child before
  spawn, and third-party executables remain quarantined.
- Native MCP admission is bound to the loaded Atlas checkout, the exact lexical
  interpreter, governed cwd, exact argv and an empty editable child environment.
  A foreign Git root, interpreter alias, cwd, repository argument or
  `PYTHONPATH` is rejected before spawn; direct Sentinel import is also covered.
- An explicitly empty child environment remains empty at `Popen`; an absent
  `PATH` can no longer turn into inherited `PYTHONPATH`, `PYTHONHOME` or parent
  secrets.
- The FastEmbed corpus is an offline `VALIDATION_HARNESS` with strict JSON
  output. It records a measurement only and changes no dependency, model,
  vector store, index or memory migration.

The branch introduced no project dependency and did not modify
`config/governance.json`.

## Current validation

At `fac6bca`:

- direct core suite: 4550 passed, 58 skipped, 1 deselected, 1 warning;
- strict mypy: clean across 320 source files;
- focused native-MCP/security suite: 137 passed, 6 skipped, including the
  explicit fixture, re-vetting and empty-environment regressions;
- canon: 2085 JSONL records pass the canonical integrity gate;
- docs index: no missing/orphan/stale entries (915 entries);
- Merkle audit, doctor and health exit successfully with explicit external
  integration warnings;
- `uv lock --check` passes (301 resolved packages);
- the UI tree is byte-identical to the candidate source tree and builds with
  its already-local dependencies; the integration worktree intentionally did
  not install `node_modules` merely to turn an environmental absence green;
- the offline FastEmbed runner emitted `MEASURED` and passed all three
  versioned Spanish cases.

Runtime limits are intentionally not promoted: the delivery workspace is dirty
only while these documentation artifacts are generated; browser is degraded
without Playwright; Hermes is mock/unconfigured/not live; two MCP servers are
only configured, not handshake-verified; external providers are absent; F2.6
has never run; and the shared structural graph remains stale against `fac6bca`
because it was not overwritten from the isolated worktree.

## Review and integration

1. Inspect `ATLAS.md`, `STATUS.md`, ADR-078 and the adversarial audit.
2. Verify the new bundle and SHA-256 from
   `/home/ronin/proyectos/atlas-definitive-backup`.
3. Review the atomic commit list and `FINAL_DIFF.patch` at its documented
   anchor.
4. Resolve only operator-owned decisions that should alter the candidate.
5. If accepted, promote this local integration branch through the
   protected-main workflow; do not fast-forward or overwrite the preserved
   original checkout while it carries operator changes.
6. Rebuild the structural graph on the integrated commit, rerun Reality, and
   only then promote graph freshness or live-service claims.
