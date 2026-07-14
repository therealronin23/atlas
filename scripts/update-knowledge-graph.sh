#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -f ".venv/bin/activate" ]; then
  echo "ERROR: .venv not found. Activate the project virtualenv or create it first." >&2
  exit 1
fi

source .venv/bin/activate

VAULT_DIR="${1:-graphify-vault}"
mkdir -p "$VAULT_DIR"

printf 'Updating Graphify output to %s and Obsidian vault to %s\n' "$(pwd)/graphify-out" "$(pwd)/$VAULT_DIR"

if [ -f graphify-out/graph.json ]; then
  graphify . --update --code-only
else
  graphify . --code-only
fi

graphify . --cluster-only --code-only
graphify export obsidian --dir "$VAULT_DIR"
graphify export neo4j

printf '\nDone.\n- Graph report: %s/GRAPH_REPORT.md\n- Obsidian vault: %s\n- Neo4j import: %s/cypher.txt\n' "$(pwd)/graphify-out" "$(pwd)/$VAULT_DIR" "$(pwd)/graphify-out"
printf '\nNOTE: This is currently a code-only graph. To include docs/papers extraction, export nodes with an LLM backend by setting GEMINI_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY and re-running the script.\n'
