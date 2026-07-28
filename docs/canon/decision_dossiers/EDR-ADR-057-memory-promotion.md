# EDR-ADR-057 — Memory promotion and provenance

**Decision:** ADR-057
**Program:** P04 — Memory and Continuity
**Evidence state:** `PROVISIONAL`
**Decision disposition authority:** `docs/canon/decision_registry.jsonl`

## Question

How should Atlas promote low- and medium-sensitivity information without
collapsing the accepted memory stores or treating semantic graph extraction as
fact?

## Constraints

- Private memory is distilled before inclusion in shareable graphs.
- High sensitivity remains human-controlled or denied.
- Repeated copies are not independent corroboration.
- A new store or dependency requires its own decision.

## Observed evidence

- `EVD-LOCAL-ADR-057` preserves the three role-specific memory stores.
- `EVD-LOCAL-MEMORY-INDEX` shows existing provenance, tenant, temporal and
  crypto-shred mechanisms.
- `EVD-EXT-PROV-O` supplies derivation, revision and invalidation vocabulary.
- `EVD-EXT-LONGMEMEVAL` distinguishes extraction, multi-session, temporal,
  update and abstention quality rather than treating retrieval as one score.

## Alternatives compared

1. Retain the three stores without a governed promotion policy. This avoids a
   premature merge but leaves promotion semantics implicit.
2. Keep the stores and add source-bound, sensitivity-aware promotion with
   lineage withdrawal. This adds an evaluation obligation but preserves the
   accepted topology and makes deletion/revision inspectable.

## Recommendation

Retain the three-layer topology. Add a maintenance/promoter boundary separate
from the primary agent, and allow automatic low/medium promotion only after
deterministic provenance, sensitivity, corroboration and evaluation gates.
Semantic graph claims remain hypotheses until verified.

This is not yet an implementation decision: no automatic promotion path or
benchmark result is claimed by this dossier.

## Confidence and limits

**Confidence:** medium. The local implementation and standard provenance model
are strong evidence; the external memory benchmark establishes what to measure,
not a directly transferable implementation result.

**Falsifier:** an Atlas benchmark shows that the proposed promotion policy
reduces temporal correctness, privacy lineage or abstention quality.

**Revisit triggers:** a measured bridge threshold between stores, a changed
privacy requirement, or a reproducible benchmark that disproves the current
promotion gate.

## Security, privacy and rollback

Promotion must preserve sensitivity and source lineage. Withdrawal removes
sole-source derivatives and recomputes confidence/provenance for independently
corroborated claims. The future change is reversible by disabling the promoter
and rebuilding projections from the durable record; it must not delete the
source record without its existing crypto-shred procedure.

## Evidence IDs

`EVD-LOCAL-ADR-057`, `EVD-LOCAL-MEMORY-INDEX`, `EVD-EXT-PROV-O`,
`EVD-EXT-LONGMEMEVAL`.
