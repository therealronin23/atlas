# Adversarial Audit

Date: 2026-07-28
Anchor reviewed: `aa71a980cef53f1a9ddf1374615a461c0eadfa0c`

## Verdict

- `BLOCKING`: 0
- technically resolvable `MAJOR` left open: 0
- `MAJOR` requiring operator authority: 1
- `MINOR`: 4
- `INFO`: 5

The three requested independent reviewer contexts were unavailable because the
subagent quota was exhausted. The primary agent therefore performed a separate
adversarial pass over the complete candidate, validation results, canon
registries and runtime evidence. This is not represented as independent
approval.

## Resolved findings

| Severity | Finding | Resolution |
|---|---|---|
| BLOCKING | A custom/injected Decider could allow high sensitivity | post-Decider constitutional normalization plus regression tests |
| BLOCKING | Sentinel error/corrupt snapshot could look like no finding | fail-closed denial, receipt and quarantine |
| MAJOR | MCP re-vet drift/error left a callable runtime surface | revoke/quarantine during process lifetime |
| MAJOR | command inspection could execute a clean but unadmitted candidate | pure argv inspection; governed admission remains separate |
| MAJOR | product-lineage repositories had no canonical destination | ADR-078 plus lineage registry; no topology-only merge |
| MAJOR | authority, reality and ADR atoms could drift silently | registries, validator and CI gate |
| MAJOR | evidence and operator-gated work could be overstated as ready | evidence qualification and work-order eligibility gates |
| MAJOR | optional SDK edges bypassed strict type safety | mapping boundary validation and lazy dynamic ACP binding |
| MAJOR | tracked UI retained a high-severity PostCSS advisory | compatible lock remediation; current audit is clean |
| MAJOR | semgrep test depended on undeclared local executable | hermetic local/PATH fallback fixtures |
| MAJOR | Reality could cut a passing suite at 600 seconds | finite configurable 900-second default |

## Open findings

### MAJOR — operator required

`ADC-WO-107`: port 7341 exposes mutating POST routes while ADR-058 and ADR-071
describe a read-only projection. Removing or authorizing those routes changes
an operator-owned security/product boundary. The candidate neither widens nor
silently blesses it.

### MINOR

1. The shared structural graph is stale against the candidate and must be
   rebuilt only after integration, not from this isolated worktree.
2. The Atlas shell emits a 674.82 kB production-chunk warning; build integrity
   and audit pass.
3. The runtime lacks the optional Playwright package. `computer_use` tests
   skip, and browser capability remains degraded rather than live-verified.
4. FastEmbed 0.8.0 warns that the multilingual model changed pooling behavior.
   Existing implementation/version/artifact identity guards prevent silent
   persistent-vector mixing; a retrieval benchmark is needed before a pin or
   custom-model change.

### INFO

1. Hermes is mock, unconfigured and not live.
2. MCP has two configured servers but no fresh handshake.
3. No external providers are configured.
4. F2.6 has never been recorded as run.
5. Sanitation reports 165 current docs with no markdown-link edges and one
   expired historical archive quarantine item; both remain visible.

## Security review

- `config/governance.json`: unchanged.
- New project dependencies: none; `uv lock --check` passes.
- ADR-076 C: rejected and absent.
- High-sensitivity rule: structurally enforced.
- Generated-code AST Guard invariant: unchanged.
- `pip-audit --strict` and UI high-severity audit: no known vulnerability.
- Third-party execution remains reversible/fail-closed; no remote executable
  MCP candidate was installed or run by this convergence.

## Completion judgment

No `BLOCKING` finding and no technically resolvable `MAJOR` remains. The one
open `MAJOR` is intentionally reserved to the operator. Runtime/dependency
limits remain evidence-labelled and do not change the candidate's code or
constitutional authority.
