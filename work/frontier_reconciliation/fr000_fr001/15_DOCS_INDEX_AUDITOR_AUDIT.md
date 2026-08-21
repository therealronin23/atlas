# Docs-index auditor audit

Verdict: **MIXED**.

## Historical result preserved

CR-001 observed **334 missing paths = 246 graveyard + 88 non-graveyard**. That result remains historical evidence and is not rewritten. Its source artifact is `work/checkpoints/CR-001_DOCS_INDEX_DRIFT.json`.

## Current read-only reproduction

The unchanged script (`sha256:1dcf64688a0a5c8bd3958a99dce15098f5fd947f3c898604b6117c5907cb1b41`) returned exit 1 with **97 missing, 0 orphan, 0 expired**. Classification is exhaustive:

| Finding class | Count |
| --- | ---: |
| Ordinary current documents (`TRUE_DOCUMENT_DRIFT`) | 20 |
| Canon schema contracts | 3 |
| Fixture payloads | 65 |
| Archived code/build metadata | 9 |
| Total | 97 |

The 88 non-graveyard paths are unchanged between observations. The graveyard population changed from 246 physical-tree paths to 9 currently emitted tracked artifacts; the sealed Git tree has only 48 graveyard blobs and no tracked `node_modules` or `vendor` subtree.

## Auditor-of-auditor finding

The explicit prose contract says every document under `docs/` is indexed. The implementation instead performs a physical `rglob`, filters a small exception list, and accepts generic document-like suffixes. It has no scope contract for fixtures, schemas, archive source trees, `node_modules`, vendor, build/dist, ignored, or untracked files. Tests do not cover those families.

Therefore the gate contains both real drift (20 ordinary documents) and a scope defect (77 non-ordinary artifacts): **MIXED**, not a pure documentation failure and not a pure false positive.

`docs/INDEX.yaml` was not changed. The current result does not replace the CR-001 result because the populations differ.
