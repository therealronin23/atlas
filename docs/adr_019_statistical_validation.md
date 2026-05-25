# ADR-019 — Statistical Validation Framework

**Status:** SEALED (minimal v1, 2026-05-25)  
**Module:** `src/atlas/lab/evaluator.py`

## Decision

Atlas compares execution metric samples (latency proxy, success) using stdlib `statistics` before promoting generated tools when `ATLAS_STAT_VALIDATE=1`.

## Scope v1

- `StatisticalEvaluator.recommend_promotion(baseline, candidate)`
- Optional hook in `ResultAuditor.promote_if_valid` when env enabled and ≥3 baseline snapshots exist
- No scipy/sklearn dependency

## Out of scope

- Full router cross-validation multi-seed (future script `scripts/stat_validate.py`)
