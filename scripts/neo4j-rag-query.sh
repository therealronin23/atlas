#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

usage() {
  cat <<'EOF' >&2
Usage: ./scripts/neo4j-rag-query.sh [PATTERN]

If PATTERN is provided, the script searches Neo4j node labels containing that term.
If no pattern is given, it returns a small sample of the graph.

Environment:
  NEO4J_URI      bolt URI for Neo4j import (default: bolt://localhost:7687)
  NEO4J_USER     Neo4j username (default: neo4j)
  NEO4J_PASSWORD Neo4j password (required)
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
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
  exit 2
fi

PARAM_ARGS=()
if [ "$#" -eq 1 ]; then
  PATTERN="$1"
  PYTHON_BIN="python3"
  if [ -x .venv/bin/python ]; then
    PYTHON_BIN=.venv/bin/python
  fi
  PARAM_LITERAL="$($PYTHON_BIN - "$PATTERN" <<'PY'
import sys

value = sys.argv[1]
escaped = (
    value.replace("\\", "\\\\")
    .replace("'", "\\'")
    .replace("\r", "\\r")
    .replace("\n", "\\n")
)
print("{pattern: '" + escaped + "'}")
PY
)"
  PARAM_ARGS=(-P "$PARAM_LITERAL")
  QUERY='MATCH (n)
WHERE toLower(coalesce(n.label, "")) CONTAINS toLower($pattern)
WITH n LIMIT 10
OPTIONAL MATCH (n)-[r]-(m)
RETURN n.id AS node_id, n.label AS node_label, type(r) AS relation,
       m.id AS neighbor_id, m.label AS neighbor_label
LIMIT 100'
else
  QUERY='MATCH (n)-[r]-(m)
RETURN n.id AS node_id, n.label AS node_label, type(r) AS relation,
       m.id AS neighbor_id, m.label AS neighbor_label
LIMIT 20'
fi

if command -v cypher-shell >/dev/null 2>&1; then
  echo "Running GraphRAG validation query against Neo4j at $NEO4J_URI..."
  printf '%s\n' "$QUERY" | \
    NEO4J_PASSWORD="$NEO4J_PASSWORD" \
    cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" \
      --access-mode read --transaction-timeout 10s --format plain \
      "${PARAM_ARGS[@]}"
  exit 0
fi

if command -v docker >/dev/null 2>&1; then
  echo "cypher-shell not found locally. Falling back to Docker image neo4j:latest."
  printf '%s\n' "$QUERY" | docker run --rm --network host -i \
    -e NEO4J_URI="$NEO4J_URI" \
    -e NEO4J_USERNAME="$NEO4J_USER" \
    -e NEO4J_PASSWORD="$NEO4J_PASSWORD" \
    --entrypoint cypher-shell \
    neo4j:latest --access-mode read --transaction-timeout 10s --format plain \
    "${PARAM_ARGS[@]}"
  exit 0
fi

echo "ERROR: Neither cypher-shell nor docker is installed. Install one to query Neo4j." >&2
exit 1
