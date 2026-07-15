#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -f ".venv/bin/activate" ]; then
  echo "ERROR: .venv not found. Activate the project virtualenv or create it first." >&2
  exit 1
fi

source .venv/bin/activate

if [ -f ".env" ]; then
  set -a
  source ".env"
  set +a
fi

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
printf 'For a richer GraphRAG-ready workflow, use ./scripts/update-knowledge-graph-rag.sh --backend <backend> --model <model>.\n'

# Verify Graphify version (added 2026-07-14)
if command -v graphify &> /dev/null; then
  GRAPHIFY_VERSION=$(graphify --version 2>&1 | grep -oP 'graphify \K[\d.]+' || echo "unknown")
  if [ "$GRAPHIFY_VERSION" != "0.9.11" ]; then
    echo "ERROR: Graphify version mismatch"
    echo "  Expected: 0.9.11"
    echo "  Got: $GRAPHIFY_VERSION"
    echo "  Fix: pip install graphify==0.9.11"
    exit 1
  fi
fi
