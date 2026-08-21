# FR-000 source classification summary

Sealed denominator: **2,344 tracked Git blobs** at `b790640b12ebff8eb100939f9f7a92f02de0b502`. Every blob has a path identity, SHA-256, Git blob SHA, category, lifecycle, relevance, ownership inference, and independence key.

The registry is exhaustive at file level, while `conceptual_entity=false` prevents fixtures, generated files, and third-party payloads from becoming thousands of independent capability claims.

## Categories

| Category | Files |
| --- | ---: |
| ADR | 79 |
| BENCHMARK | 5 |
| CANON | 20 |
| CI | 1 |
| CODE | 371 |
| DESIGN | 84 |
| EVIDENCE | 59 |
| FIXTURE | 246 |
| GENERATED | 30 |
| HISTORICAL | 545 |
| OTHER | 124 |
| PLAN | 24 |
| PRODUCT | 19 |
| PROTOTYPE | 52 |
| RESEARCH | 42 |
| RUNTIME_CONFIG | 3 |
| SCHEMA | 38 |
| SPEC | 12 |
| TEST | 477 |
| TOOLING | 113 |

## Lifecycle

| Lifecycle | Files |
| --- | ---: |
| ARCHIVED | 104 |
| CURRENT | 1571 |
| GENERATED | 26 |
| HISTORICAL | 634 |
| SUPERSEDED | 9 |

## Deduplication and ownership

- Files participating in an exact-content duplicate group: 214.
- Non-conceptual fixture/generated/vendor rows: 277.
- Explicit third-party/vendor rows: 1 (the graveyard contains no tracked node_modules/vendor subtree; the Gradle wrapper JAR is the known third-party binary).
- `independence_key` is content-addressed. Repeated copies never increase evidence independence.

## Program inference

Program is a path/subsystem inference, not decision authority. `UNKNOWN` is retained instead of forcing a frontier.

| Program | Files |
| --- | ---: |
| P00 | 118 |
| P01 | 22 |
| P02 | 30 |
| P03 | 72 |
| P04 | 103 |
| P05 | 88 |
| P06 | 86 |
| P07 | 143 |
| P08 | 521 |
| P09 | 164 |
| P10 | 34 |
| P11 | 15 |
| P12 | 52 |
| UNKNOWN | 896 |

`UNCLASSIFIED_CURRENT = 0`: UNKNOWN program or frontier mapping is an explicit classification; no current source is silently absent.
