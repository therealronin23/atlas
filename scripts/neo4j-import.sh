#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

usage() {
  cat <<'EOF' >&2
Usage: ./scripts/neo4j-import.sh [options]

Atomically replace the derived Neo4j graph with Graphify's parameterized JSON
export. The previous graph is rolled back if import or count verification fails.

Options:
  --file PATH               Graphify JSON file (default: graphify-out/graph.json)
  -h, --help                Show this help text

Environment:
  NEO4J_URI                 bolt URI for Neo4j import (default: bolt://localhost:7687)
  NEO4J_USER                Neo4j username (default: neo4j)
  NEO4J_PASSWORD            Neo4j password (required)
EOF
}

GRAPH_FILE="graphify-out/graph.json"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --file)
      if [ "$#" -lt 2 ]; then
        echo "ERROR: --file requires a path." >&2
        usage
        exit 2
      fi
      GRAPH_FILE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [ ! -f "$GRAPH_FILE" ]; then
  echo "ERROR: Graphify JSON file not found: $GRAPH_FILE" >&2
  echo "Run ./scripts/update-knowledge-graph.sh or ./scripts/update-knowledge-graph-rag.sh first." >&2
  exit 1
fi

if [ -z "${NEO4J_PASSWORD:-}" ]; then
  echo "ERROR: NEO4J_PASSWORD is not set." >&2
  echo "Set it in the environment before running the script." >&2
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "ERROR: .venv/bin/python is unavailable." >&2
  exit 1
fi

if [ ! -f scripts/neo4j-import-batch.py ]; then
  echo "ERROR: scripts/neo4j-import-batch.py is unavailable." >&2
  exit 1
fi

exec .venv/bin/python scripts/neo4j-import-batch.py "$GRAPH_FILE" --replace
