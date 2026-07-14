#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

usage() {
  cat <<'EOF' >&2
Usage: ./scripts/neo4j-rag-query.sh [PATTERN]

If PATTERN is provided, the script searches Neo4j node names containing that term.
If no pattern is given, it returns a small sample of the graph.

Environment:
  NEO4J_URI      bolt URI for Neo4j import (default: bolt://localhost:7687)
  NEO4J_USER     Neo4j username (default: neo4j)
  NEO4J_PASSWORD Neo4j password (required)
EOF
  exit 1
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
fi

NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-}"

if [ -z "$NEO4J_PASSWORD" ]; then
  echo "ERROR: NEO4J_PASSWORD is not set." >&2
  echo "Set NEO4J_PASSWORD in your environment before running this script." >&2
  exit 1
fi

if [ "$#" -gt 1 ]; then
  echo "ERROR: Only one optional PATTERN argument is supported." >&2
  usage
fi

if [ "$#" -eq 1 ]; then
  PATTERN="$1"
  QUERY="MATCH p=(n)-[*..3]-(m) WHERE toLower(n.name) CONTAINS toLower(\"$PATTERN\") RETURN p LIMIT 20"
else
  QUERY="MATCH p=(n)-[*..2]-(m) RETURN p LIMIT 20"
fi

if command -v cypher-shell >/dev/null 2>&1; then
  echo "Running GraphRAG validation query against Neo4j at $NEO4J_URI..."
  echo "$QUERY" | cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD"
  exit 0
fi

if command -v docker >/dev/null 2>&1; then
  echo "cypher-shell not found locally. Falling back to Docker image neo4j:latest."
  printf '%s\n' "$QUERY" | docker run --rm --network host -i \
    -e NEO4J_AUTH="${NEO4J_USER}/${NEO4J_PASSWORD}" \
    neo4j:latest sh -c "cypher-shell -a '$NEO4J_URI' -u '$NEO4J_USER' -p '$NEO4J_PASSWORD'"
  exit 0
fi

echo "ERROR: Neither cypher-shell nor docker is installed. Install one to query Neo4j." >&2
exit 1
