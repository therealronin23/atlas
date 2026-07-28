# Canon Compilation Report

## Authority result

The compilation does not create a fifth constitution. ADR-067 remains the
constitutional model; `ATLAS.md` is its single human entry and
`docs/canon/authority_registry.yaml` routes machine consumers to the authority
that governs each scope.

Current reality is resolved from fresh runtime, code, tests, configuration and
living status. Target architecture is resolved from the current operator
directive, explicit operator decisions, invariants and accepted ADRs. Historical
or derivative repetition never counts as independent corroboration.

## Corpus result

| Registry | Records |
|---|---:|
| Sources | 1317 |
| Decisions | 215 |
| Conflicts | 124 |
| Supersessions | 14 |
| Components | 76 |
| Capabilities | 61 |
| Contracts | 41 |
| Open questions | 45 |
| Product lineages | 32 |
| Component reality matrix | 137 |
| Total JSONL | 2062 |

All 906 documents are discoverable through `docs/INDEX.yaml`. Exact duplicates
remain one source occurrence set rather than false corroboration.

## ADR disposition

- 56 ADR files were traversed.
- ADR-067 through ADR-077 received explicit definitive addenda or atomic
  registry dispositions where their historical prose could overstate current
  reality.
- ADR-076 is split into A accepted/implemented/opt-in, B
  accepted/implemented/opt-in and C rejected/not implemented/absent.
- ADR-077 is split into implemented gate/report, opt-in activation, missing
  universal Task escalation, explicit unblock limitations and the preserved
  high-sensitivity boundary.
- ADR-078 records the operator-approved Workbench lineage convergence.

## Conflicts and supersessions

Current conflicts for desktop host and first product are resolved by ADR-078.
Android is elevated to its own dependency-gated work order. The mutating API
bridge remains elevated to the operator because ADR-058/071 say read-only
while code exposes mutation.

Recovered low-confidence conflicts retain their underlying `UNRESOLVED`
epistemic state but carry `resolution_status=ELEVATED_TO_PROGRAM` and a named
owner. This preserves uncertainty without allowing it to become implicit
authority.

Every supersession identifies scope, old/new authority, preserved parts and
annulled parts. Notable results:

- ADR-068 refines only the F5/F6 framing, preserving ADR-066 parking;
- ADR-070 retires Hermes REST without claiming a live twin;
- ADR-071 supersedes web-first final UX, not the validation harness;
- ADR-078 refines ADR-071 for desktop host and first product while preserving
  Android.

## Reality discipline

The matrix contains one record for every component and capability registry
entry. It does not infer:

- product from harness;
- liveness from tests;
- handshake from MCP configuration;
- Hermes availability from deployment history;
- fact from GraphRAG hypothesis;
- Android support from a desktop host;
- Atlas integration from donor code in another repository.

Canon integrity and its 15 adversarial tests run in CI without a new
dependency.
