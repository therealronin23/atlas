# Adversarial Audit

Date: 2026-07-28

## Verdict

- `BLOCKING`: 0
- resolvable `MAJOR` left open: 0
- `MAJOR` requiring operator authority: 1
- `MINOR`: 3
- `INFO`: 4

Three isolated reviewer contexts were requested, but the available subagents
all failed before review because their usage quota was exhausted. The primary
agent therefore reran the review in a separated adversarial pass using the
complete diff, structural/source registries, full validation and runtime
evidence. This limitation does not masquerade as independent approval.

## Resolved findings

| Severity | Finding | Resolution |
|---|---|---|
| BLOCKING | injected Decider could return `Allow` for high sensitivity | post-Decider constitutional normalization plus regression tests |
| BLOCKING | Sentinel internal error/corrupt snapshot could be interpreted as no finding | fail-closed denial, evidence and quarantine |
| MAJOR | MCP re-vet drift/error left callable runtime surface | revoke and quarantine during process lifetime |
| MAJOR | installer conflated argv screening with admission and could execute the candidate during inspection | pure argv inspection; clean but unadmitted candidate is skipped |
| MAJOR | multiple product repositories had no canonical destination | lineage registry plus ADR-078; no topology-only merge |
| MAJOR | root authority, ADR atoms and reality states could drift silently | single entries, registries, validator and CI |
| MAJOR | tracked UI retained a high-severity PostCSS advisory | lock-only compatible resolution; audit now zero |
| MAJOR | semgrep test depended on undeclared local installation | hermetic local/fallback fixtures |
| MAJOR | Reality cut a passing 670-second suite at 600 seconds | tested finite default of 900 seconds |
| MAJOR | live documents overstated production/liveness or stale product choices | current-state addenda, matrices and supersessions |

## Open findings

### MAJOR — operator required

`ADC-WO-107`: the port-7341 API exposes mutating POST routes while ADR-058 and
ADR-071 define a read-only projection. Removing routes may break real clients;
authorizing them changes an accepted security/product boundary. The candidate
neither widens nor silently blesses the contradiction.

### MINOR

1. The shared structural graph is stale against the candidate. It remains
   explicit; rebuilding from the isolated worktree would contaminate the
   original runtime.
2. The Atlas shell emits a ~675 kB production chunk warning. Build integrity
   and audit pass.
3. Sanitation reports 159 current docs with no markdown-link edges. All are
   discoverable and classified in the 906-entry index; navigation can improve.

### INFO

1. Hermes is mock, unconfigured and not live.
2. MCP has two configured servers but no fresh handshake.
3. No external providers are configured; inference is stub/local.
4. Eleven broken links and one expired quarantine item are confined to
   historical archive material.

## Security review

- `config/governance.json`: unchanged.
- New project dependencies: none.
- ADR-076 C: rejected and absent.
- High-sensitivity rule: structurally enforced.
- Generated code AST Guard invariant: unchanged.
- Secret scan on all changed files: no token/private-key/credential finding.
- `pip-audit --strict`: no known vulnerability.
- NPM audit: no known vulnerability.
- Third-party execution remains reversible/fail-closed and no remote candidate
  was installed or executed during convergence.

## Completion judgment

The candidate satisfies Cut 0. The one open MAJOR is not technically
resolvable without changing an operator-owned boundary. No implementation-ready
MAJOR or BLOCKING finding remains.
