# Handoff to frontier reconciliation

Atlas N identity is verified at `df4fbe7a96c70507094c24c7bf553efd297cc80a` / `b790640b12ebff8eb100939f9f7a92f02de0b502`. The output is an audit layer only; the checkpoint and Atlas functional code are unchanged.

## Start here

1. Read `20_COVERAGE_REPORT.json` for denominators.
2. Read `10_CONTRADICTIONS.jsonl`, `11_NEGATIVE_EVIDENCE.jsonl`, and `13_UNKNOWNS.jsonl` before interpreting positive claims.
3. Use `12_EVIDENCE_REGISTRY.jsonl` to inspect source quality and contamination.
4. Use `03_CURRENT_COMPONENT_MAP.jsonl` for the exhaustive 471-unit implementation census and `04_AUTHORITY_MAP.jsonl` for critical semantic capability boundaries.
5. Use `06_SUPERSESSION_GRAPH.jsonl` and `07_DECISION_REALITY_MAP.jsonl` together; an edge never implies implementation.
6. Treat `08_FRONTIER_MAPPING.jsonl` R0 rows as cross-mapping of hypotheses, not approved taxonomy.

## Counts

- Current sources classified: 1571 / 1571.
- Current component units classified: 471 / 471.
- Independent current decision subjects classified: 126 / 126 (134 / 134 records before semantic deduplication).
- R0 frontiers examined: 109 / 109.
- Contradictions: 22; semantic unknown registry records: 24; explicit UNKNOWN dimensions: 3036; unclassified current: 0.

## Non-actions

No feature, bug fix, refactor, migration, dependency adoption inside Atlas, docs-index repair, Semgrep rescan, F2.6 run, PR, or tag was performed. At artifact generation time nothing was staged or committed; the operator later explicitly authorized publication of this audit-only directory.

## Commit candidates

Only files beneath `work/frontier_reconciliation/fr000_fr001/` are candidates, after external review. Use explicit paths if authorization is later given; never `git add .`, `git add -A`, or `git add --all`.

Required artifact set (21 files): 00_EXECUTION_MANIFEST.json, 01_SOURCE_COVERAGE_REGISTRY.jsonl, 02_SOURCE_CLASSIFICATION_SUMMARY.md, 03_CURRENT_COMPONENT_MAP.jsonl, 04_AUTHORITY_MAP.jsonl, 05_CALLER_WRITER_ANOMALIES.jsonl, 06_SUPERSESSION_GRAPH.jsonl, 07_DECISION_REALITY_MAP.jsonl, 08_FRONTIER_MAPPING.jsonl, 09_CANDIDATE_NEW_FRONTIERS.jsonl, 10_CONTRADICTIONS.jsonl, 11_NEGATIVE_EVIDENCE.jsonl, 12_EVIDENCE_REGISTRY.jsonl, 13_UNKNOWNS.jsonl, 14_UNCLASSIFIED.jsonl, 15_DOCS_INDEX_AUDITOR_AUDIT.md, 16_EVIDENCE_RETENTION_GAPS.md, 17_FR000_REPORT.md, 18_FR001_REPORT.md, 19_HANDOFF_TO_RECONCILIATION.md, 20_COVERAGE_REPORT.json.
