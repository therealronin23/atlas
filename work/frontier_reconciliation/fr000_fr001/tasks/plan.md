# FR-000 + FR-001 audit plan

## Scope

Reconstruct Atlas N at the sealed `atlas-n-cr001-20260820` checkpoint without
implementing, repairing, migrating, rescanning Semgrep, or rerunning F2.6.
Only new audit artifacts may be written below
`work/frontier_reconciliation/fr000_fr001/`.

## Authority order

1. Reproducible evidence observed during this audit.
2. Code at the sealed checkpoint.
3. Reproducible tests.
4. Preserved and verifiable runtime evidence.
5. Current canon and ADRs.
6. Current documentation.
7. Historical artifacts.
8. Frontier Pack hypotheses.
9. Inference.
10. Narrative.

## Dependency-ordered phases

1. Verify the annotated tag, peeled commit, tree, worktree isolation, local
   state categories, live reality, token ledger, and F2.6 notification path.
2. Rebuild and verify the stale project graph before structural inspection;
   query overview, imports, importers, blast radius, churn, callers, and
   callees for critical components.
3. Validate and slice the external Frontier Pack without treating it as canon.
4. Enumerate every tracked Atlas N source and classify project-owned,
   third-party, generated, archived, historical, and current material.
5. Audit the docs-index auditor and preserve the historical 334-path claim
   without changing `docs/INDEX.yaml`.
6. Preserve Semgrep retention gaps without rescanning.
7. Reconstruct current components and caller/writer/authority paths from code,
   tests, graph data, configuration, and preserved runtime evidence.
8. Classify decisions and build explicit supersession, contradiction,
   dependency, implementation, test, runtime-evidence, and falsifier edges.
9. Cross-map the independently reconstructed reality to all R0 frontiers;
   identify merge, split, delete, superseded, historical, unknown, and new
   frontier candidates.
10. Generate evidence, contradiction, negative-evidence, unknown,
    unclassified, coverage, phase-state, and handoff artifacts.
11. Validate JSON/JSONL schemas and referential integrity; then perform a
    fresh-context adversarial review and retain self-review corrections.
12. After every audit stop condition passes, use the operator's later explicit
    authorization to commit only this directory and publish by fast-forward to
    `main`; never rewrite the checkpoint tag or history.

## Checkpoints

- After phases 1-3: baseline identity and graph freshness are evidenced; pack
  remains external input; no functional files changed.
- After phases 4-6: every tracked source has a registry record or an explicit
  unknown/unclassified record; docs-index and Semgrep history are preserved.
- After phases 7-9: components, critical authority paths, decisions, and all R0
  frontiers have classifications with evidence or explicit unknowns.
- After phases 10-11: all required files exist, machine-readable validation
  passes, coverage denominators match registries, and git scope is clean.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Pack claim leakage | Isolate pack analysis and mark every pack-derived record as hypothesis. |
| Lost-in-the-middle omissions | Write phase records with preserved constraints, new evidence, invalidations, unknowns, contradictions, and unclassified count. |
| Duplicate evidence inflation | Assign `independence_key` and hash content; do not count copies as independent support. |
| False maturity promotion | Require one evidence locator for each maturity transition; record missing transitions as negative evidence. |
| Stale structural claims | Rebuild the Kuzu graph and preserve freshness metadata before graph queries. |
| Generated/vendor explosion | Register files exhaustively while grouping conceptual third-party/generated populations in summaries. |
| Audit self-confirmation | Run a fresh-context issues-only review and retain superseded findings instead of deleting them. |

## Verification

- Required output names exist.
- Every JSONL line parses as one JSON object.
- Every registered tracked path resolves to the sealed tree and has a content
  hash plus git blob SHA when applicable.
- Coverage numerators and denominators are recomputed from registries.
- `git diff --check` passes.
- No path outside the authorized audit directory is modified.
- No PR or tag is created. Commit/push occurs only after validation and the
  operator's explicit later authorization; publication must be fast-forward.
