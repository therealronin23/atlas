# Atlas Definitive Convergence Report

Date: 2026-07-28

## Outcome

Atlas now has one reviewable **ATLAS DEFINITIVE CANDIDATE**. It is not
`ATLAS CANON ACCEPTED`; that elevation remains exclusively with the operator.

- Base: `c95038c9d7e97ddc6339f38abe6dad09b166f47d`
- Substantive validation anchor:
  `ff439d2840e30754fbf8175e0b61c59cf4e3c4de`
- Branch: `codex/atlas-definitive-convergence-20260727-154020`
- Worktree: `/home/ronin/proyectos/atlas-definitive-convergence`
- Canonical repository authority: Atlas Core

`ATLAS.md` is the single human entry. `docs/canon/authority_registry.yaml` is
the machine entry. `VISION.md`, `ARCHITECTURE.md`, `PROGRAMS.md`, `PLAN.md`
and `STATUS.md` separate identity, target architecture, permanent programs,
execution order and demonstrated reality.

## Preservation

The operator checkout was not used as a work surface. Its original HEAD
remains `c95038c`; its dirty sources were backed up and selectively classified.

- Backup directory: `/home/ronin/proyectos/atlas-definitive-backup`
- Git bundle: `atlas-before-definitive.bundle`, verified
- Tracked patch, staged patch and secret-safe untracked archive: present
- Original dirty sources: preserved; later runtime-generated changes were
  compared and dispositioned without blind import

## Canonical convergence

- 13 permanent programs, P00 through P12, are retained.
- 56 ADR source files have a disposition; 215 atomic/recovered decision
  records prevent multi-part ADRs from collapsing into one status.
- ADR-076 A/B remain accepted and opt-in; C remains rejected, absent and not
  implemented.
- ADR-077 remains opt-in and does not alter high-sensitivity human control.
- ADR-078 accepts Atlas Engineering Workbench, CodeOSS/VSCodium as desktop
  host, Void as capability donor and Zed as ACP/pattern donor.
- Android remains a distinct required projection; no desktop implementation
  is presented as mobile.
- 32 product/construction lineages have exact heads and dispositions.
- 137 components/capabilities distinguish design, code, test, wiring,
  configuration, live verification and product acceptance.
- 124 conflict records remain either scoped-resolved or explicitly elevated
  to a program/operator; none is erased by prose.

## Implemented convergence

The candidate adds or corrects:

- post-Decider constitutional enforcement for high sensitivity;
- fail-closed MCP vetting, snapshot/drift handling and runtime revocation;
- separation between pure command screening and governed admission;
- canonical authority, decision, conflict, supersession, component,
  capability, contract, question, lineage and reality registries;
- canonical integrity validator and CI gate;
- honest current-state corrections across ADRs, capabilities, Product OS,
  Membrane/Osmosis and the live ledger;
- PostCSS advisory remediation in the tracked UI;
- hermetic semgrep resolution tests;
- a Reality timeout that allows the canonical suite to complete while
  retaining a finite configurable bound.

No new project dependency was introduced and `config/governance.json` was not
modified.

## Validation

At `ff439d2`:

- core pytest: 4559 passed, 6 skipped, 27 deselected;
- browser pytest: 26 passed, 1 skipped;
- mypy: 318 source modules, no issues;
- extended Reality: `status=ok`, no strict failures;
- Merkle audit, doctor and health: exit 0, with honest external-service
  warnings;
- canon: 2062 JSONL records and 15 integrity tests pass;
- docs index: 906 entries, no missing or orphan index entries;
- UI: exact install, build and audit pass; zero vulnerabilities;
- lock and pip audit: pass, zero known vulnerabilities;
- Python 3.11 wheel: import, packaged resources and CLI smoke pass;
- changed-file secret scan: no token, private key or credential finding.

Runtime limits remain explicit: Hermes is mock/unconfigured/not live; MCP is
configured but has no fresh handshake; providers are absent; the shared
structural graph is stale against the candidate and was not overwritten from
the isolated worktree.

## Review and integration

1. Fetch the published branch.
2. Review `ATLAS.md`, `STATUS.md`, ADR-078 and
   `work/canon-compiler/delivery/ADVERSARIAL_AUDIT.md`.
3. Verify the delivery bundle and its SHA-256.
4. Inspect atomic commits and `FINAL_DIFF.patch`.
5. Resolve only the operator decisions that should change the candidate.
6. If accepted, merge through the normal protected-main workflow.
7. Rebuild the structural graph on the integrated commit, rerun Reality, and
   only then promote any graph freshness claim.
