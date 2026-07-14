# ATLAS CORE — Operating Context For Agents

Operational context, not marketing copy. If this conflicts with live evidence,
live evidence wins.

## OPERATING LOOP

Pre-flight, cheap and factual:

1. Run `PYTHONPATH=src atlas reality --json` before making claims about Atlas state.
2. Structure = graph first: answer "who imports X / blast radius / churn /
   dependencies" from the live project graph (MCP trunk → `trunk_invoke_readonly`
   with `graph_importers`, `graph_blast_radius`, `graph_imports_of`,
   `graph_churn`, `graph_overview`) BEFORE reading files or docs. Docs are
   past/future; the graph is the present (auto-regenerated after every commit
   by the scheduler's project-graph cycle).
3. Locate the work in the shallowest matrioska node: `Gate -> ADR -> Fase -> Tipo`.
   Tipo 2 correctness/foundation comes before Tipo 1 build-on-top; Tipo 3 is a real
   wall to route around or accept.
4. Pick the fitting skill and actually use it: plan -> planning, tests -> TDD,
   build -> incremental implementation, bug -> debugging, review -> code review,
   cleanup -> simplification, ADR/doc -> documentation.
5. Preserve the single authority model:
   - `WORK_LEDGER.md` = live WHERE/status and next action only.
   - `docs/design/atlas_ecosystem_map.md` = canonical ecosystem map.
   - Design docs = HOW/detail/checklists.
   - `MEMORY.md` and `feedback-*.md` = WHY/lessons/manias.
6. Update ledger, design note, and memory in the same commit as the work.

Definition of done: relevant tests green, mypy strict clean when code changes,
ledger updated, design-doc note present, and honest limits declared.

## Reality First

```bash
cd ~/proyectos/atlas-core
source .venv/bin/activate
PYTHONPATH=src atlas reality --json
```

Fresh verification:

```bash
PYTHONPATH=src atlas reality --run-checks --include-browser --json
```

Do not hand-maintain test counts in docs. Do not claim Hermes, Telegram,
browser, LLM, MCP, or external providers are live unless current environment or
fresh smoke evidence proves it.

## Current Identity

Atlas is a local intelligence runtime. It coordinates local tools, local models,
provider models, memory, approvals, audit, and cold self-improvement. It is not
a SaaS wrapper and not a chatbot shell.

The strategic line is **selective assimilation without cloning**:
observe external systems, dissect them, absorb useful capabilities/patterns,
wrap them with Atlas invariants, measure, and improve. Cursor, Codex, Claude
Code, MemGPT/MemPalace, Hermes, MCP servers, skills, prompts, APIs, and repos
are sources to learn from; Atlas does not become any of them.

Atlas ecosystem taxonomy lives in `docs/design/atlas_ecosystem_map.md`.

## Invariants

1. Every external effect must be Merkle-audited.
2. Generated Python code must pass AST Guard before execution.
3. `config/governance.json` is never modified by agents or runtime instructions.
4. `sensitivity="high"` forces human approval or denial in autonomous modes.
5. DEGRADED/OMEGA thermal modes must not load heavy local LLMs.
6. No new dependencies without explicit ADR or gate-level approval.
7. Tests must cover code changes before merge.
8. Before editing files, state the intended diff.
9. External MCP/tool/skill adoption is untrusted, fail-closed, reversible where
   possible, and requires explicit consent when it installs or executes third-party code.

## Standing Manias

`plan-then-execute` · `decide-with-facts` · `honesty-over-sycophancy` ·
`convergence-discipline-verification` · `debt-closure-workflow` ·
`operating-loop` · `verify-the-real-case` · `internal-prior-art-first` ·
`wire-before-claim` · `least-effort-automation` · `roadmap-is-guide-not-law` ·
`stdlib-over-new-deps` · `no-aux-scripts-bloat` · `no-cli-against-live-workspace` ·
`no-gui-in-tests` · `no-deepen-hitl-coupling` · `no-security-lectures-local` ·
`arxiv-citation-verification` · `adopt-real-not-shell` ·
`research-before-deciding` · `challenge-the-trio` ·
`deep-onboarding-new-sessions` · `no-rewrite-git-history` ·
`absorb-without-cloning`.

When the user states a recurring preference or workflow improvement, add/update
a `feedback-*.md` memory, add a one-liner in `MEMORY.md`, and add the mania name
above if it should become a standing rule.

## Naming Rules

Use technical names in code, comments, prompts, and instructions. Narrative
aliases belong only in human-facing historical docs.

| Use | Do not use in code |
| --- | --- |
| `SystemContextLoader` | `TrinityMemo` |
| `ErrorRegistry` | `FailureAtlas` |
| `ApprovedPatternStore` | `PatternLibrary` |
| `ProviderMetricsStore` | `PerformanceLedger` |
| `LayeredIsolationSandbox` | `MatrioskaSandbox` |
| `OperationalMode.NORMAL` | `TriageMode.ALFA` |
| `OperationalMode.DEGRADED` | `TriageMode.OMEGA` |
| `OfflineFallbackMode` | `ModoFantasma` |

Compliance/transparency vocabulary authority:
`docs/membrana/OSM-000_membrana.md`.

| Use técnico | Alias narrativo only in human docs |
| --- | --- |
| `in-path verifiable AI compliance filter` | Osmosis / Filtro Osmosis |
| `admission gate` | membrane / membrana |
| `adaptive defense layer` | antivirus inmune |
| `external knowledge ingestion & verification pipeline` | organismo de conocimiento |
| `defense-pattern mutation & selection` | afinidad maduración |
| `decision/action provenance record` | never "chain-of-thought auditable" |

## Key Commands

```bash
PYTHONPATH=src python -m pytest tests/ -q
PYTHONPATH=src python -m pytest tests/ -q -m "computer_use"
MYPYPATH=src python -m mypy src/atlas/
PYTHONPATH=src atlas reality
PYTHONPATH=src atlas doctor
PYTHONPATH=src atlas health
PYTHONPATH=src atlas audit --verify
```

Live smokes require current secrets/network:

```bash
set -a && source .env && set +a
PYTHONPATH=src python scripts/inference_smoke.py
PYTHONPATH=src python scripts/hermes_smoke.py
PYTHONPATH=src python scripts/operational_smoke.py
```

## Runtime Dependency: bubblewrap

`LayeredIsolationSandbox.execute_in_jail()` requires `bwrap`. Without it,
Python code execution is fail-closed (`BwrapUnavailableError`); other Atlas
functionality is unaffected. Slice 2 seccomp-bpf remains deferred because it
requires an explicit external dependency decision.

## Graphify / Obsidian / NotebookLM guidance

For agent-facing knowledge navigation in this repo, prefer `AGENTS.md` over a separate `CLAUDE.md` so the operating context remains centralized.

- Run `./scripts/update-knowledge-graph.sh` from the repo root to update the code-only Graphify graph and rebuild the Obsidian export.
- Open `graphify-out/GRAPH_REPORT.md` first for architecture context before reading source code.
- Use `graphify query "<question>"`, `graphify explain "<concept>"`, and `graphify path "A" "B"` for focused, low-token exploration.
- Open `graphify-vault/` in Obsidian for graph-based navigation of nodes, links, and code/document relationships.
- Use `./scripts/prepare-notebooklm.sh` to generate a NotebookLM upload package from the current report and docs.
- To include the Obsidian vault notes in the NotebookLM package, run `./scripts/prepare-notebooklm.sh --include-vault`.
- Recommended Obsidian plugins: Dataview, Graph View, QuickAdd, Natural Language Dates, Search Extended.
- The current Graphify build is intentionally `code-only` to avoid LLM API key/token cost. To ingest docs/papers later, set `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY` and re-run the update script.

## How To Resume

1. Activate the venv.
2. Run `atlas reality --json`.
3. Query the live graph for the code area you will touch (`graph_importers` /
   `graph_blast_radius` via the MCP trunk).
4. Read `WORK_LEDGER.md` and `docs/design/atlas_ecosystem_map.md`.
5. Read only the design doc named by the active node.
6. Prefer small reversible changes with tests.
