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

**Confidence:** medium-high (raised from `medium` on 2026-07-31 — LongMemEval
ran at its FULL declared scale, n=500, for the first time; ADR-057's own
appendix had only reached a n=50 smoke baseline before today).

**LongMemEval_S, n=500, k=5, all 500 questions — EXECUTED 2026-07-31**
(`scripts/eval_longmemeval.py --mode all`, 1284.9s, JSON result archived in
session scratchpad). Overall Recall@5:

| Mode | Overall | knowledge-update | multi-session | single-session-assistant | single-session-preference | single-session-user | temporal-reasoning |
|---|---|---|---|---|---|---|---|
| cosine | 0.9300 | 0.9872 | 0.9774 | 0.9464 | 0.8667 | 0.7857 | 0.9323 |
| hybrid | 0.9340 | 1.0000 | 0.9774 | 0.9464 | 0.8667 | 0.8000 | 0.9323 |
| temporal | 0.9300 | 0.9872 | 0.9774 | 0.9464 | 0.8667 | 0.7857 | 0.9323 |
| temporal_aof | 0.9300 | 0.9872 | 0.9774 | 0.9464 | 0.8667 | 0.7857 | 0.9323 |
| hybrid_multihop | 0.9340 | 1.0000 | 0.9774 | 0.9464 | 0.8667 | 0.8000 | 0.9323 |

This holds the n=50 smoke baseline (0.9400, `docs/decisions/adr/adr_057_memory_canonical_by_use_case.md`
appendix) at full scale — no collapse from sampling luck. `hybrid` is the
best mode measured (0.9340), marginally ahead of plain `cosine`.
`single-session-user` is the weakest category across every mode (0.7857-0.8000)
-- the one category worth watching if promotion logic is ever gated on a
per-category floor rather than the overall number.

**Honest finding NOT to bury: pure `multihop` scored 0.0040 overall** (0.0000
in 5 of 6 categories, 0.0357 in the sixth) -- investigated, not a bug in
`SqliteMemoryIndex.recall_multihop` itself. `recall_multihop` chains each hop's
query off the PREVIOUS hop's RESULT TEXT (not the original question) and
returns at most `hops=2` candidates regardless of the harness's `k=5` --
a retrieval strategy built for exploring associative memory chains, not for
"find the single best answer to THIS question" (LongMemEval's actual task
shape). `hybrid_multihop` (0.9340, matching plain `hybrid`) confirms this:
fusing multihop with cosine just lets cosine's real signal dominate and
carry the score: the multihop component itself contributes close to nothing
on this benchmark. **This is a mismatch between benchmark task and retrieval
mode design, not evidence that `recall_multihop` is broken for its own
intended use** (lesson-chain exploration) -- that intended use was not
exercised by this measurement and remains unverified either way.

**Falsifier:** an Atlas benchmark shows that the proposed promotion policy
reduces temporal correctness, privacy lineage or abstention quality. **Not yet
directly testable**: no promotion policy is implemented to run an A/B
comparison against. Today's n=500 run establishes the RETRIEVAL-QUALITY
baseline that a future promotion-policy falsifier would need to show does NOT
regress -- it is necessary evidence for that falsifier, not the falsifier
itself.

**Revisit triggers:** a measured bridge threshold between stores, a changed
privacy requirement, a reproducible benchmark that disproves the current
promotion gate, or a `multihop`-specific benchmark (lesson-chain retrieval,
not LongMemEval) if that mode's own intended use case is ever measured.

## Security, privacy and rollback

Promotion must preserve sensitivity and source lineage. Withdrawal removes
sole-source derivatives and recomputes confidence/provenance for independently
corroborated claims. The future change is reversible by disabling the promoter
and rebuilding projections from the durable record; it must not delete the
source record without its existing crypto-shred procedure.

## Evidence IDs

`EVD-LOCAL-ADR-057`, `EVD-LOCAL-MEMORY-INDEX`, `EVD-EXT-PROV-O`,
`EVD-EXT-LONGMEMEVAL`.
