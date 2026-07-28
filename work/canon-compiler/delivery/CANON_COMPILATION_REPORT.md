# Canon Compilation Report

## Authority result

The compiler did not create a fifth constitution. ADR-067 remains the
constitutional model; `ATLAS.md` is the single human entry and
`docs/canon/authority_registry.yaml` routes machine consumers to the source
that governs each scope.

Current reality is derived from fresh runtime, code, tests, configuration and
living status. Target architecture is derived from the operator directive,
explicit operator decisions, invariants and accepted ADRs. Repeated or
derivative documents never count as independent corroboration.

## Corpus result at `aa71a98`

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
| Evidence sources | 19 |
| Decision-evidence matrix | 4 |
| **Total JSONL** | **2085** |

All 912 tracked documents are discoverable through `docs/INDEX.yaml`. Four
decision dossiers expose alternatives, falsifiers and revisit triggers without
claiming that their `PROVISIONAL` recommendations are accepted implementation.

## ADR and conflict disposition

- 56 ADR source files were traversed.
- ADR-076 is atomic: A and B are accepted/implemented/opt-in; C is rejected,
  absent and not implemented.
- ADR-077 preserves its implemented/opt-in pieces and its high-sensitivity
  human-command boundary.
- ADR-078 records the Workbench lineage decision without presenting a host or
  donor repository as already product-accepted.
- The mutating port-7341 bridge remains elevated as `ADC-WO-107`: ADR-058/071
  describe a read-only projection while current code exposes mutation.

Every supersession names scope, old/new authority, preserved parts and annulled
parts. Unresolved evidence stays visible as an open question or program-owned
conflict rather than being erased in prose.

## New evidence and eligibility gates

`scripts/check_canon.py` now validates source tiers, local evidence paths,
cross-references, independent corroboration, falsifiers, revisit triggers and
dossiers. It also validates that a work order needing the operator cannot be
`READY`, that `REQUIRES_OPERATOR` explicitly says so, and that an operator
question links only to a registered compatible blocker.

The current candidate passes the gate with 2085 JSONL records and 25 behavioral
tests. This is an authority/discovery control, not evidence that external
services or product surfaces are live.

## Reality discipline

The component matrix does not infer product from a harness, liveness from unit
tests, a handshake from configuration, Hermes availability from history, fact
from GraphRAG hypothesis, Android support from a desktop host, or Atlas
integration from donor code elsewhere.
