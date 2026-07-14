# Atlas Core knowledge stack instructions

## Current state

- Graphify is installed inside the project virtual environment at `.venv`.
- A code-only Graphify build has already been generated for this repo.
- Current outputs are:
  - `graphify-out/graph.json`
  - `graphify-out/GRAPH_REPORT.md`
  - `graphify-out/cypher.txt` (Neo4j import)
  - `graphify-vault/` (Obsidian vault export)

## Priority workflow

1. Read `graphify-out/GRAPH_REPORT.md` first. It contains the current architecture summary, community hubs, and freshness metadata.
2. Open `graphify-vault/` as an Obsidian vault for code/document node navigation.
3. Use `scripts/update-knowledge-graph.sh` to refresh Graphify and Obsidian together.
4. Use `scripts/prepare-notebooklm.sh` to build a NotebookLM package from the current report and docs.

## Update command

```bash
cd /home/ronin/proyectos/atlas-core
./scripts/update-knowledge-graph.sh
```

For a custom vault location:

```bash
./scripts/update-knowledge-graph.sh /path/to/obsidian-vault
```

## VS Code integration

Use the VS Code task:

- `Update Knowledge Graph`
- `Prepare NotebookLM Package`

Open the command palette and run `Tasks: Run Task`.

## NotebookLM preparation

The NotebookLM package should start with:

- `graphify-out/GRAPH_REPORT.md`
- `README.md`
- key files under `docs/`
- optionally, curated notes from `graphify-vault/`

Run:

```bash
./scripts/prepare-notebooklm.sh
```

Then upload the generated `notebooklm-package/` folder.

## Obsidian vault recommendations

- Use `graphify-vault/` as the workspace root.
- Recommended plugins:
  - Dataview
  - Graph View (built-in)
  - QuickAdd
  - Natural Language Dates
  - Search Extended / Search Plus
  - Markdown Table Formatter

## Hooks and automation

Install the git hook once:

```bash
cd /home/ronin/proyectos/atlas-core
./scripts/install-git-hooks.sh
```

The hook updates Graphify after commits that touch source, docs, or metadata.

## Low-token, high-efficiency strategy

- Keep Graphify as the primary structural layer: `graphify-out/GRAPH_REPORT.md` and `graphify-vault/`.
- Use NotebookLM for summaries and audio, not as the first source of truth.
- Prefer direct Graphify graph queries for code reasoning, then fall back to document notes.
- If you need multi-hop reasoning later, import `graphify-out/cypher.txt` into Neo4j and use Cypher-backed GraphRAG.

## Notes on current configuration

- The current build is `code-only` to avoid LLM API dependency and token cost.
- To include docs/papers in the graph, set one of the supported API keys and rerun the update script.
- `graphify-out/graph.json` is the canonical local graph state for the repository.

## Quick reference for Claude/Code tools

- Read `GRAPH_REPORT.md` before opening code files.
- Use `graphify query "<question>"` for focused graph-based exploration.
- Use `graphify path "A" "B"` and `graphify explain "X"` for link-level reasoning.
- Keep `graphify-vault/` open in Obsidian for human navigation and note context.
