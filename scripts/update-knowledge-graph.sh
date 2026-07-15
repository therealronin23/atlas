#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
DOTENV_PATH="$ROOT_DIR/.env"
if [[ -f "$DOTENV_PATH" && "${ATLAS_SAFE_DOTENV_FILE:-}" != "$DOTENV_PATH" ]]; then
  export ATLAS_SAFE_DOTENV_FILE="$DOTENV_PATH"
  exec python3 "$ROOT_DIR/scripts/safe_dotenv.py" "$DOTENV_PATH" -- \
    bash "$(readlink -f "${BASH_SOURCE[0]}")" "$@"
fi

if [ ! -f ".venv/bin/activate" ]; then
  echo "ERROR: .venv not found. Activate the project virtualenv or create it first." >&2
  exit 1
fi

source .venv/bin/activate

# NetworkX's fallback community detector iterates hash-backed collections.
# Pinning the hash seed keeps unchanged graphs stable across processes.
export PYTHONHASHSEED=0

if ! command -v graphify >/dev/null 2>&1; then
  echo "ERROR: graphify is not installed in the active virtualenv." >&2
  exit 1
fi

GRAPHIFY_VERSION="$(graphify --version 2>&1 | awk 'NR == 1 {print $2}')"
if [ "$GRAPHIFY_VERSION" != "0.9.11" ]; then
  echo "ERROR: Graphify version mismatch" >&2
  echo "  Expected: 0.9.11" >&2
  echo "  Got: ${GRAPHIFY_VERSION:-unknown}" >&2
  exit 1
fi

VAULT_DIR="${1:-graphify-vault}"
mkdir -p "$VAULT_DIR"

printf 'Updating Graphify output to %s and Obsidian vault to %s\n' "$(pwd)/graphify-out" "$(pwd)/$VAULT_DIR"

if [ -f graphify-out/graph.json ]; then
  graphify update .
else
  graphify extract . --code-only --no-cluster
fi

# No LLM labels on the daily path, and no visualization rewrite: the current
# graph is above Graphify's HTML limit and an implicit viz pass deletes the
# previously generated tracked graph.html.
graphify cluster-only . --no-label --no-viz
graphify export obsidian --dir "$VAULT_DIR"
graphify export neo4j

printf '\nDone.\n- Graph report: %s/GRAPH_REPORT.md\n- Obsidian vault: %s\n- Neo4j import: %s/cypher.txt\n' "$(pwd)/graphify-out" "$(pwd)/$VAULT_DIR" "$(pwd)/graphify-out"
printf '\nNOTE: This is currently a code-only graph. To include docs/papers extraction, export nodes with an LLM backend by setting GEMINI_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY and re-running the script.\n'
printf 'For a richer GraphRAG-ready workflow, use ./scripts/update-knowledge-graph-rag.sh --backend <backend> --model <model>.\n'
