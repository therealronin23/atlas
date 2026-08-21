# FR-001 report — Decisions, supersession and R0 mapping

Status: **COMPLETE FOR EXTERNAL ADVERSARIAL REVIEW**, not operator approval of any decision or frontier taxonomy.

## Decision coverage

- All decision records: 276 / 276 classified; independent decision subjects: 268 / 268.
- Current decision records: 134 / 134 classified; 8 semantic companion records are deduplicated.
- Independent current decision subjects: 126 / 126 (100.0%).
- Historical decision records: 136.
- Explicit graph records: 17; canonical source records: 15; canonical atomic endpoint pairs: 18; chronology-derived edges: 0.

The current-authority record population is 134: 85 canonical rows, 36 ADC work orders, and 13 program rows. Eight canonical companion rows share an independence key with their atomic ADR subject, so coverage uses 126 independent subjects: 77 canonical + 36 work orders + 13 programs. Referential graph endpoints are excluded. Historical recovered decisions remain `HISTORICAL`.

## Required focused revalidation

- `ADC-WO-107`: **CONTRADICTED / REQUIRES_OPERATOR** remains supported. Mission approve/reject POST handlers mutate ColdUpdate outside ADR-080's scoped Product OS exception.
- `ADR-057`: **PROVISIONAL** evidence qualification; no automatic promoter is established.
- `ADR-058`: **PROVISIONAL** with an active scope breach; ADR-080 supersedes only the named Product OS scope.
- `ADR-069`: **PROVISIONAL**; v0 code/tests do not establish the proposed durable effect journal.
- `ADR-078`: **PROVISIONAL** accepted design, not a completed Workbench product.

`ADC-WO-124` is additionally `CONTRADICTED` at document-reality level. `ADC-WO-109` is also `CONTRADICTED`: the clean external checkout is 1.132.0/f7c27192 while tracked lineage remains 1.129.1/8a7abeba, and the work-order row contains mutually incompatible state claims. No build/runtime receipt was rerun.

## R0 cross-mapping

- Examined: 109 / 109 (100.0%).
- Assessment counts: MERGE_CANDIDATE=2, NEW_EVIDENCE=35, REFORMULATE=1, SPLIT_CANDIDATE=1, UNKNOWN=70.
- Merge candidate group: `FR-P06-010` + `FR-P10-005` (one group, two frontier rows).
- Split candidate: `FR-P00-007`, because it combines the compiler/selection concern and typed ContextPacket concern already separated in `FR-P02-002`/`FR-P02-003`.
- Candidate new frontiers: 0. Every anomaly and current contradiction has a durable fit assessment; zero is derived, not initialized. Existing mappings do not resolve the problems.

## F2.6 preservation

`execution_outcome=FAIL`, `automatic_grade=1/6`, `measurement_validity=INCONCLUSIVE`. Execution result and measurement validity remain separate. F2.6 was not run.

## Phase state

PRESERVED_CONSTRAINTS: no decision resolution, no date-only supersession, pack remains non-canon, historical claims retain their source qualification.

NEW_EVIDENCE: explicit decision edges, code/decision mismatch at port 7341, documentary conflict at ADC-WO-124, current Code OSS identity conflict at ADC-WO-109, exhaustive R0 examination.

INVALIDATED_CLAIMS: DONE/ACCEPTED is not automatically implementation, wiring, runtime, or product evidence; port 7341 is not uniformly read-only in sealed code.

NEW_UNKNOWNS: current production clients of mutating routes, route identity/idempotency/recovery, live desktop admission, unrun provisional falsifiers.

NEW_CONTRADICTIONS: ADC-WO-107, ADC-WO-109, ADC-WO-124, F2.6 execution versus measurement interpretation.

UNCLASSIFIED_COUNT: 0.
