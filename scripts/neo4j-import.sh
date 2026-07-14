#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

usage() {
  cat <<'EOF' >&2
Usage: ./scripts/neo4j-import.sh [options]

Options:
  --file PATH               Cypher import file (default: graphify-out/cypher.txt)
  -h, --help                Show this help text

Environment:
  NEO4J_URI                 bolt URI for Neo4j import (default: bolt://localhost:7687)
  NEO4J_USER                Neo4j username (default: neo4j)
  NEO4J_PASSWORD            Neo4j password (required)
EOF
  exit 1
}

CYPHER_FILE="graphify-out/cypher.txt"
NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --file)
      shift
      CYPHER_FILE="${1:-$CYPHER_FILE}"
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      ;;
  esac
  shift
done

if [ ! -f "$CYPHER_FILE" ]; then
  echo "ERROR: Cypher file not found: $CYPHER_FILE" >&2
  echo "Run ./scripts/update-knowledge-graph.sh or ./scripts/update-knowledge-graph-rag.sh first." >&2
  exit 1
fi

if [ -z "$NEO4J_PASSWORD" ]; then
  echo "ERROR: NEO4J_PASSWORD is not set." >&2
  echo "Set NEO4J_PASSWORD in your environment, or pass it via env before running the script." >&2
  exit 1
fi

if command -v cypher-shell >/dev/null 2>&1; then
  echo "Importing $CYPHER_FILE into Neo4j at $NEO4J_URI using cypher-shell..."
  cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" < "$CYPHER_FILE"
  exit 0
fi

if command -v docker >/dev/null 2>&1; then
  echo "cypher-shell not found locally. Falling back to Docker image neo4j:latest."
  docker run --rm --network host \
    -v "$(pwd)/$(dirname "$CYPHER_FILE"):/graphify-out" \
    neo4j:latest sh -c "cypher-shell -a '$NEO4J_URI' -u '$NEO4J_USER' -p '$NEO4J_PASSWORD' < '/graphify-out/$(basename "$CYPHER_FILE")'"
  exit 0
fi

echo "ERROR: Neither cypher-shell nor docker is installed. Install one of them to import into Neo4j." >&2
exit 1
