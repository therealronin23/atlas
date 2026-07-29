# Adversarial Audit

Date: 2026-07-29
Anchor reviewed: `fac6bca34831533ae248564adf615e052c59be16`

## Verdict

- `BLOCKING`: 0
- technically resolvable `MAJOR` left open: 0
- `MAJOR` requiring operator authority: 1
- `MINOR`: 4
- `INFO`: 5

Independent review found two MCP-native admission defects: the aggregate trunk
was missing from the native set, then the initial repair still relied on a
module-name match that did not prove which interpreter or package the child
would execute. The corrective delta derives authority from the loaded Sentinel
checkout and binds the lexical interpreter, cwd, command contract and clean
child environment. A direct-import cycle and an obsolete lazy-registry fixture
were also reproduced and closed. The final review found that `{}` could become
`Popen(env=None)` when `PATH` was absent; explicit-empty environment propagation
and a regression now close that post-admission shadowing path. This is a review
finding and remediation record, not an external approval.

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
| IMPORTANT | generated `atlas-trunk` configuration was quarantined before registry spawn | governed aggregate entrypoint plus serialized-config and registry-boundary regressions |
| BLOCKING | native module-name allowlist could accept a python-named executable or shadowing cwd/package | native admission now derives the root from loaded code and binds lexical interpreter, governed repo/cwd, expected server identity, exact args and no editable child import environment; spoofed configurations are vetoed pre-spawn |
| MAJOR | direct `SentinelGate` import could traverse a circular `atlas.mcp` import edge | identifier validation moved to a dependency-light module; a fresh interpreter import regression passes |
| MINOR | a tiering test used a malformed native fixture and therefore tested quarantine rather than tier precedence | fixture now uses the governed native memory command and retains the tier assertion |
| MINOR | the Orchestrator re-vetting test implicitly relied on a tracked echo fixture | the fixture enables Sentinel's test-only exception directly in the test; no production setting can activate it |
| MAJOR | unchanged re-vetting coverage could pass after the fixture was quarantined before start | the regression now proves the echo transport and tool were admitted before it accepts an empty finding list |
| MAJOR | an explicit empty MCP child environment was converted to `Popen(env=None)` and inherited the parent process | transport preserves `{}`; a `PATH`-absent regression proves that no host environment is substituted |
| MINOR | finite extreme embedding vectors could serialize a non-standard JSON `NaN` | reject non-finite norm/score and enforce strict JSON serialization |
| MINOR | the measured offline benchmark lacked a discoverable operating contract | indexed knowledge document names limits, execution and decision boundary |

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
   The offline corpus measured the current identity, but a baseline comparison
   and migration-cost evidence are still needed before a pin or custom-model
   change.

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
- Historical dependency audits remain evidence only; this integration reran the
  lock check and did not add a dependency.
- Third-party execution remains reversible/fail-closed; no remote executable
  MCP candidate was installed or run by this convergence.

## Completion judgment

No `BLOCKING` finding and no technically resolvable `MAJOR` remains. The one
open `MAJOR` is intentionally reserved to the operator. Runtime/dependency
limits remain evidence-labelled and do not change the candidate's code or
constitutional authority.
