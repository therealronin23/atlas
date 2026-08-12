# Canon compiler capability audit — 2026-08-12

## Verdict

- **VERIFIED — validation/inventory harness.** The recovered R2.1 artifact has
  manifests, hashes, negative fixtures and 14 recorded validators. Its own
  `validation_report.json` records a passing historical run over 850 atomic
  records and 121 conflicts at baseline `c95038c`.
- **NOT VERIFIABLE — reproducible canon compiler.** No tracked command or
  packaged entrypoint accepts the source corpus and regenerates the current
  `docs/canon/`. `00_START_HERE.md` delegates compilation to an agent through
  work orders; the live `delivery/_SNAPSHOT_STATUS.md` says the delivery is a
  historical snapshot and is not regenerated from that directory.
- **VERIFIED — current integrity gate after lineage repair.** The live
  `scripts/check_canon.py` validates relationships and fails fast, but its own
  module contract says it does not approve prose or promote canon. Passing it
  demonstrates consistency of the current registries, not reproducibility of
  the historical compilation.

## Measured corpus and drift

Read-only stdlib inspection of the R2.1 ZIP recovered from
`atlas-definitive-backup/untracked-working-tree.tar.gz` found:

| Property | Verified value |
| --- | ---: |
| Source archives declared by the R2.1 manifest | 13 |
| Source member rows | 1,305 |
| Unique content hashes | 497 |
| Rows marked exact duplicates | 1,089 |
| Rows only `INVENTORIED` | 1,183 |
| Rows `PHYSICALLY_PRESERVED` | 122 |
| Historical conflicts validated at R2.1 | 121 |
| Live `docs/canon/conflict_registry.jsonl` rows | 125 |

The 13 archives therefore prove breadth of intake, not independent evidence or
a current regeneration capability. Most rows are duplicated lineage, and the
historical conflict count already differs from the live registry.

## Reproduction evidence

```text
PYTHONPATH=src .venv/bin/python scripts/check_canon.py --root .
before repair: exit 1, exactly INVALID_LINEAGE_HEAD for LINEAGE-CODEX-CLI and
LINEAGE-CLAUDE-AGENT-SDK

git -C ~/proyectos/atlas-forks/codex remote get-url origin
https://github.com/openai/codex.git
git -C ~/proyectos/atlas-forks/codex rev-parse HEAD
cc2f2620330116b961c87430d9fdaa16d948d3bf

git -C ~/proyectos/atlas-forks/claude-agent-sdk remote get-url origin
https://github.com/anthropics/claude-agent-sdk-python.git
git -C ~/proyectos/atlas-forks/claude-agent-sdk rev-parse HEAD
0982371d69ca7411fc21a589493b34f480a16efb
```

Both checkouts were clean on `main...origin/main` and contained a top-level
`LICENSE`. This audit did not fetch, clone, execute either checkout or alter the
historical delivery snapshot.
