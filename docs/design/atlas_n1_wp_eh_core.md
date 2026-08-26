# Atlas N+1 — WP-EH-CORE implementation binding

Status: `VERIFIED_PENDING_INDEPENDENT_AUDIT_FINAL_VERDICT`

## Frozen authority

Implementation starts from the exact frozen baseline:

- commit: `2161f2b1240ef69c20319fa5366b8bbcb9fc6cc8`
- tree: `7d22ac8478df1237e5b1ad81a8d865935d70cc90`
- freeze: `ATLAS-N1-DESIGN-FREEZE-001`

`ATLAS_N1_CODEX_EXTERNAL_AUTHORITIES_COMPLETE.zip` was treated as an external
attachment, not as repository input. Its SHA-256 is
`282f4a73a15540d81429a162d547ef03b2fd30318c26fbee2bb1c0e4393ec93e`.
`MANIFEST.json` and `SHA256SUMS.txt` were extracted and validated before any
inner artifact. All eight declared files then passed outer hashes, declared
sizes, safe-path checks, ZIP integrity and their own internal manifests.

| Frozen attachment | SHA-256 |
| --- | --- |
| `ATLAS_N1_DESIGN_FREEZE.zip` | `eeef83672d2cbe865d97bf0fa9733424644424052bbbb2f290affc54843a31dc` |
| `CC002R1_FORK_ADOPTION_CONVERGENCE.zip` | `de0561da3dda4cc90bc9b5af3bbce22d08fdcb0ec0a79973204528998bb3a6a7` |
| `CC003R1_ARCHITECTURE_SYNTHESIS.zip` | `6485f8735e5ea4a48341620089a186a1d28589a93d06d8fba9c4f05cf745f30f` |
| `CC004R1_MIGRATION_DELETION_MAP.zip` | `ad84a8262ac70a549dc7f915993b496ffc43b52e581860fd8248e9c81a7e799a` |
| `CC005R1_BENCHMARK_ACCEPTANCE_ARCHITECTURE.zip` | `03b6614dd3006da6ed5c6f230d8f1a7d29c4094d66014d45d836ab2b61a18f81` |
| `CC006R1_IMPLEMENTATION_DECOMPOSITION.zip` | `93788c0ec242d9fa5b525fdcb0cb9563f9cfa772f649e58ac992d44e0abf8753` |
| `FR003A3_DEFINITIVE_FRONTIER_TAXONOMY.zip` | `e6f1e27198bb720a8f46e3dcbc2bd9815660aad7b0f976fac76fa99d72893824` |
| `FR007R1_DEPENDENCY_BLOCKER_GRAPH.zip` | `8e0d3904f75e592cf6a56fcb94358479437720700c953d9d4112b09f9f9c267d` |

The older `FR003_DEFINITIVE_FRONTIER_TAXONOMY.zip` is not an accepted
substitute and was not used.

## Physical binding of `R1-PL-EH-CORE`

The freeze intentionally assigned no current filesystem path. The post-freeze
implementation binds the proposed logical layout to `src/atlas/acceptance/`.
It is a new, isolated enablement seam and does not replace the production
evidence owner (`ARC-C13`) or the independent verifier (`ARC-C14`/`ARC-C18`
where frozen contracts require it).

The bounded implementation provides:

- exact A0–A6 and `PASS|FAIL|INCONCLUSIVE|BLOCKED|NOT_RUN` vocabularies;
- immutable, duplicate-rejecting acceptance-contract registry metadata;
- cryptographic source provenance for each registered identity;
- a strict evidence receipt envelope implementing the frozen CC005 fields;
- adapter binding from one receipt to one registered contract and one declared
  acceptance level, without promotion or normalization.

A structural audit loaded all contract-identity families from the verified
CC005R1 bytes:

| Family | Identities |
| --- | ---: |
| Guarantee | 94 |
| Frontier | 110 |
| Component | 22 |
| Interface | 64 |
| Benchmark | 58 |
| Selected asset ADAPT | 93 |
| Migration | 114 |
| UNKNOWN inspection | 102 |
| Blocker/wall gate | 14 |
| Performance/resource | 13 |
| **Total** | **684 unique** |

This was a structural `NOT_RUN` validation. It does not claim that any
acceptance contract passed semantically.

## Verification boundary

The bounded test suite, strict mypy check, full source-tree mypy check, canon
integrity check and Merkle audit passed. The full pytest regression passed when
excluding only the two MCP subprocess tests independently reproduced against
the exact frozen baseline; neither imports nor exercises `atlas.acceptance`.

A separate adversarial reviewer found and the implementation corrected
deep-JSON mutability, unvalidated Pydantic instance bypasses, nested receipt
revalidation, contract-to-receipt source lineage, whitespace-only mandatory
fields, unsafe/ambiguous provenance paths, non-finite JSON numbers, scalar
coercions, exact A0--A6 input handling and JSON-key coercion. The focused suite
covers these mutations. The reviewer exhausted its execution quota before a
final independent verdict over the final source hash, so this document does
not claim that the independent audit has passed and no later work package may
start.

## Explicit non-goals

The following remain outside this work package:

- verifier identity registries and trust-domain comparison (`WP-EH-IDENTITY`);
- anti-self-verification (`WP-EH-ANTI-SELF`);
- failure injection (`WP-EH-FAILURE`);
- receipt capture, storage and retention (`WP-EH-RECEIPTS`);
- holdout, state, authority and rollback observation;
- cross-contract aggregation (`WP-EH-AGGREGATION`);
- production wiring, authority/state mutation, migration, deletion or claims of
  `LIVE_VERIFIED` / `PRODUCT_ACCEPTED`.

## Out-of-scope observation

`OBS-N1-20260826-001` remains `REQUIRES_EXPLICIT_RECONCILIATION`: current-main
CI/status/ecosystem references still treat `ui/atlas-shell` as active despite
ADR-085 and its archival relocation. It predates this work package, is not a
historical-branch unique delta, and is not modified here.

`OBS-N1-20260826-002` is also `REQUIRES_EXPLICIT_RECONCILIATION`: the exact
frozen baseline and this worktree both fail the same two MCP subprocess tests
when the shared FastEmbed cache points to a missing `model_optimized.onnx`.
The affected modules have no dependency on `atlas.acceptance`; the remaining
regression suite passed. Cache repair or subprocess-environment isolation is
outside `WP-EH-CORE` and is not modified here.

`OBS-N1-20260826-003` is `REQUIRES_EXPLICIT_RECONCILIATION`: `atlas handoff
--check` reports a generated handoff pack stale at the exact frozen baseline
commit. Regenerating it would alter a derived surface outside this work package,
so it is left untouched.
