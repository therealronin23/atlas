# ATLAS CORE — Operating Context For Agents

Operational context, not marketing copy. If this conflicts with live evidence,
live evidence wins.

## OPERATING LOOP

Pre-flight, cheap and factual:

1. Run `PYTHONPATH=src atlas reality --json` before making claims about Atlas state.
1b. If that output shows `f26_gate.status == "due"` (or
    `atlas f26 status --json` does), use the `f26_gate.notification` field
    (or `atlas f26 status --json`'s own `notification` field — same shape)
    to call `spawn_task` with that exact `title`/`tldr`/`prompt`. Do not run
    `atlas f26 run` yourself without flagging it first — it dispatches a
    real, expensive LLM session (a cold Sonnet run of the succession
    rubric), not a cheap deterministic check. `spawn_task` puts a visible
    chip in front of a human instead of silently burning a session or
    silently doing nothing.
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
4b. A doc-append request from a human/mission (not your own working-session
    edits) goes through the golden route (`atlas golden-route request "TEXT"`,
    ADR-069 — free text -> ColdUpdate proposal on the same ledger as
    `atlas update`), then `atlas update validate/approve/apply`. A direct
    `Edit` on a tracked doc for that kind of request is the failure mode
    the F2.6 succession rubric checks for.
5. Preserve the single authority model:
   - `WORK_LEDGER.md` = live WHERE/status and next action only.
   - `docs/design/atlas_ecosystem_map.md` = canonical ecosystem map.
   - Design docs = HOW/detail/checklists.
   - `MEMORY.md` and `feedback-*.md` = WHY/lessons/manias.
   - `docs/design/actor_roles.md` = who Fable/Sonnet/Haiku/Opus are + delegation policy.
   - This file is the boot protocol; `docs/continuation/NEXT_AI_INSTRUCTIONS.md` is SUPERSEDED (historical F15/F16).
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
`absorb-without-cloning` · `adversarial-audit-no-assumptions` ·
`graph-rebuild-single-writer` · `semantic-full-scan-before-publish` ·
`semantic-checkpoint-per-source` ·
`semantic-coverage-human-owned` · `filesystem-limits-are-runtime-facts` ·
`cost-ledger-is-not-billing` · `local-agent-config-is-secret-by-default` ·
`distill-private-sources-before-graphing` · `tracked-surface-requires-ci`.

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

## Token Budget Awareness (Important for Cost Control)

Before starting expensive operations, check the local token ledger:

```bash
# Check usage explicitly recorded by Atlas tooling
./scripts/token-tracker.sh report

# Example output:
# ✅ openrouter: 45% budget (225k/500k locally recorded tokens)
# ℹ️  nvidia: budget unknown (120k locally recorded tokens)
```

This is **not** provider billing or a live quota query. Calls that bypass the
ledger are not inferred. Record response-reported usage with
`./scripts/token-tracker.sh log <provider> <actual-token-count> <model>`; never
log a token cap as if it were actual usage.

**Provider budgets** (monthly, adjust in scripts/token-tracker.sh):
- **Groq**: 1M tokens (free tier, fastest)
- **OpenRouter**: 500K tokens (multi-model)
- **Anthropic**: 200K tokens (conservative, local recommendation)
- **Ollama**: Unlimited (local 7B model)
- **Gemini**: 1M tokens
- **NVIDIA / OpenAI direct**: budget unknown until explicitly configured;
  usage may be recorded but no percentage is claimed

**Decision rules for locally recorded usage**:
- If approaching >80%: Use Ollama locally instead
- If >95%: Pause expensive operations, use GraphRAG for efficient context
- If critical: Switch to grep/local graph queries only

Running `report` periodically only reports the ledger; it does not collect
provider usage. Prefer wiring actual response usage at each caller.

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

Live smokes require current secrets/network. Parse `.env` as data:

```bash
PYTHONPATH=src .venv/bin/python scripts/safe_dotenv.py .env -- \
  .venv/bin/python scripts/inference_smoke.py
PYTHONPATH=src .venv/bin/python scripts/safe_dotenv.py .env -- \
  .venv/bin/python scripts/hermes_smoke.py
PYTHONPATH=src .venv/bin/python scripts/safe_dotenv.py .env -- \
  .venv/bin/python scripts/operational_smoke.py --skip-telegram
```

## Runtime Dependency: bubblewrap

`LayeredIsolationSandbox.execute_in_jail()` requires `bwrap`. Without it,
Python code execution is fail-closed (`BwrapUnavailableError`); other Atlas
functionality is unaffected. Slice 2 seccomp-bpf remains deferred because it
requires an explicit external dependency decision.

## Graphify / Obsidian / NotebookLM guidance

For agent-facing knowledge navigation in this repo, prefer `AGENTS.md` (and the lowercase alias `agents.md`) as the canonical project guidance. Avoid creating a separate `CLAUDE.md` unless the workflow is truly Claude-specific.

- Run `./scripts/update-knowledge-graph.sh` from the repo root to update the code-only Graphify graph and rebuild the Obsidian export.
- Open `graphify-out/GRAPH_REPORT.md` first for architecture context before reading source code.
- Use `graphify query "<question>"`, `graphify explain "<concept>"`, and `graphify path "A" "B"` for focused, low-token exploration.
- Open `graphify-vault/` in Obsidian for graph-based navigation of nodes, links, and code/document relationships.
- Use `./scripts/prepare-notebooklm.sh` to generate a NotebookLM upload package from the current report and docs.
- To include the Obsidian vault notes in the NotebookLM package, run `./scripts/prepare-notebooklm.sh --include-vault`.
- Recommended Obsidian plugins: Dataview, Graph View, QuickAdd, Natural Language Dates, Search Extended.
- The daily Graphify path is intentionally `code-only` to avoid LLM API cost. A semantic rebuild is deliberate and must publish through `./scripts/run-graphify-quality-pipeline.sh --strict --backend <backend> --model <model>`; the lower-level `update-knowledge-graph-rag.sh` is not a quality verdict.
- The strict semantic path forces a full live-file scan while reusing safe cache entries, rejects failed/hollow/partial/invalid-confidence output and source drift, verifies real file-node IDs, restores the last published graph on failure, rolls back only unverified cache writes born after the publication baseline, exports Obsidian transactionally within the filesystem's actual `NAME_MAX`, and generates `graphify-out/cypher.txt`.
- Before that publication transaction, semantic misses are extracted and
  checkpointed one source at a time with incremental upstream cache writes
  disabled. A checkpoint is written only after exact-source filtering, schema
  validation, stable-content verification and a terminal response; later
  failures preserve earlier verified sources, and the next run retries only
  misses. Actual response usage is logged from each top-level callback; the
  checkpoint path disables adaptive retries because Graphify 0.9.11 omits the
  truncated parent attempt from its aggregate token usage.
- To load the generated graph into Neo4j, set `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`, then run `./scripts/neo4j-import.sh`.
- Graphify supports local and env-driven LLM backends: `OPENAI_BASE_URL`/`OPENAI_API_KEY`, `OLLAMA_BASE_URL`, `ANTHROPIC_BASE_URL`/`ANTHROPIC_API_KEY`, `GEMINI_BASE_URL`/`GEMINI_API_KEY`, or `claude-cli`.
- Example local Graphify GraphRAG setup:
  ```bash
  export OPENAI_BASE_URL=http://localhost:8080/v1
  export OPENAI_API_KEY=<your-key>
  export GRAPHIFY_BACKEND=openai
  export GRAPHIFY_MODEL=gpt-4.1-mini
  ./scripts/run-graphify-quality-pipeline.sh --strict
  ./scripts/neo4j-import.sh
  ```
- The GraphRAG scripts load `.env` through `safe_dotenv.py`; never source it as shell code.
- Use `--api-timeout`, `--max-workers`, and `--max-concurrency` with the strict quality wrapper to tune local Ollama or another backend.
- Keep `./scripts/update-knowledge-graph.sh` as the daily low-token maintenance path. Use the strict quality wrapper when you want richer semantic extraction and a Neo4j-ready export. Graphify 0.9.11 caches semantics by content only; any cache hit makes provenance `mixed_or_unverified`, so semantic edges remain hypotheses until confirmed by the fresh Kuzu/AST graph, code, or tests.
- Use `./scripts/neo4j-rag-query.sh [PATTERN]` after importing into Neo4j to verify the graph and explore GraphRAG neighborhood queries.
- Understand-Anything is a powerful complementary layer for semantic project understanding. It is best used in parallel with Graphify: Graphify for structural code/doc graphs, Understand-Anything for dashboard-driven concept discovery and browsing.
- Install local GraphRAG tooling with `./scripts/install-knowledge-stack.sh --all`.
- Use `scripts/install-knowledge-hooks.sh` to install a Git post-commit hook that keeps the Graphify code-only graph fresh after source or docs changes.
- VS Code tasks are available in `.vscode/tasks.json` for updating the knowledge graph, running the GraphRAG build, and preparing NotebookLM packages.
- The local environment now has Graphiti and the Neo4j Python driver installed in `.venv`. GraphRAG obtains backend credentials through its validated dotenv re-exec.
- Graphiti is a good next step if you want temporal GraphRAG and agent memory over changes. It pairs well with Neo4j and can consume the `graphify-out/cypher.txt` import as a stable knowledge layer.
- Suggested GraphRAG workflow:
  1. Maintain the base graph with `./scripts/update-knowledge-graph.sh`.
  2. Build the semantic GraphRAG graph when needed with `./scripts/run-graphify-quality-pipeline.sh --strict --backend <backend> --model <model>`.
  3. Validate with `./scripts/neo4j-rag-query.sh <term>`.
  4. Use Obsidian and NotebookLM for human-facing exploration and summaries.

## How To Resume

1. Activate the venv.
2. Run `atlas reality --json`.
3. Query the live graph for the code area you will touch (`graph_importers` /
   `graph_blast_radius` via the MCP trunk).
4. Read `WORK_LEDGER.md` and `docs/design/atlas_ecosystem_map.md`.
5. Read only the design doc named by the active node.
6. Prefer small reversible changes with tests.
