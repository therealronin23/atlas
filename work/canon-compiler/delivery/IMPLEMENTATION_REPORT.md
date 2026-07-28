# Implementation Report

## Work orders

Twelve work orders are complete after delivery:

- `ADC-WO-000` preservation and isolated baseline;
- `ADC-WO-001` live-source classification/import;
- `ADC-WO-002` authority and traceability compilation;
- `ADC-WO-003` definitive documents and P00–P12;
- `ADC-WO-004` canonical validator and CI;
- `ADC-WO-005` reality/claim reconciliation;
- `ADC-WO-006` adversarial review, validation and delivery;
- `ADC-WO-007` high-sensitivity constitutional guard;
- `ADC-WO-008` fail-closed MCP vetting/re-vetting;
- `ADC-WO-009` UI advisory remediation;
- `ADC-WO-010` product/construction lineage reconciliation;
- `ADC-WO-101` Workbench host and first-product decision.

Five work orders require the operator, five are dependency-blocked, and
`ADC-WO-106` remains rejected by design.

## Code and security changes

### Constitutional decision boundary

All supported and injected Deciders pass through the same post-verdict
normalization. High sensitivity cannot become autonomous `Allow`. The plugin
receipt path uses the same boundary. Tests cover custom Deciders and direct
clients.

### Third-party MCP boundary

Sentinel failures, corrupt snapshots and behavioral drift now deny and record
evidence. Re-vetting revokes/quarantines affected runtime servers. Installer
command inspection is separated from admission so static argv screening never
executes a clean-but-unadmitted third party.

### Reality and tests

The semgrep binary-resolution test is hermetic and covers both local-venv and
PATH fallback behavior. Reality's finite default check timeout is 900 seconds,
because the canonical suite takes approximately 670 seconds on the measured
host; `ATLAS_REALITY_TIMEOUT` remains the explicit override.

### UI

The existing Atlas shell remains a validation harness. Its lock now resolves
PostCSS 8.5.23; build and audit pass with zero known advisories.

## Documentation and product lineage

Atlas Core is the only canonical implementation target. No editor tree was
blindly merged:

- Doc0 capability precursor: already present semantically;
- Doc0 canon precursor: historical authority seed;
- Void and its forward-port: port source for Cut 2;
- CodeOSS/VSCodium: host baseline;
- Zed: ACP/pattern donor;
- relevant cold-update and self-build worktrees: ancestor/already integrated
  or semantically present.

ADR-078 and work orders 108–111 turn that evidence into a future construction
sequence without pretending Cut 1, Cut 2 or Android already exists.

## Rollback

Each functional change is an atomic commit. Revert in reverse order by concern:
Reality timeout/test, MCP hermetic test, canon/docs, UI lock, MCP
screening/admission, high-sensitivity guard, then Sentinel admission. The
original checkout and pre-convergence bundle provide an independent rollback
root.
