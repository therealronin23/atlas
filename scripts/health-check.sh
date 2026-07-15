#!/usr/bin/env bash
# Read-only health check for the local knowledge stack.
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'
health_status="HEALTHY"

mark_degraded() {
  if [ "$health_status" = "HEALTHY" ]; then
    health_status="DEGRADED"
  fi
}

mark_critical() {
  health_status="CRITICAL"
}

PYTHON_BIN=""
if [ -x .venv/bin/python ]; then
  PYTHON_BIN=.venv/bin/python
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
fi

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║         ATLAS CORE KNOWLEDGE STACK - HEALTH CHECK                 ║"
echo "║                     $(date '+%Y-%m-%d %H:%M:%S')                        ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo

echo "📊 Neo4j Database"
NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-}"
CONTAINER_RUNNING=false

if command -v docker >/dev/null 2>&1 \
  && docker ps --filter "name=^/atlas-neo4j$" --format "{{.Status}}" 2>/dev/null | grep -q "^Up"; then
  CONTAINER_RUNNING=true
  echo -e "  ${GREEN}✓${NC} Container status: RUNNING"
  if [ -z "$NEO4J_PASSWORD" ]; then
    CONTAINER_AUTH="$(
      docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' atlas-neo4j 2>/dev/null \
        | sed -n 's/^NEO4J_AUTH=//p' \
        | head -n 1
    )"
    if [ -n "$CONTAINER_AUTH" ] && [ "$CONTAINER_AUTH" != "none" ] \
      && [ "${CONTAINER_AUTH#*/}" != "$CONTAINER_AUTH" ]; then
      NEO4J_USER="${CONTAINER_AUTH%%/*}"
      NEO4J_PASSWORD="${CONTAINER_AUTH#*/}"
    fi
  fi
else
  echo -e "  ${YELLOW}⚠${NC} Local atlas-neo4j container is not running"
  mark_degraded
fi

NEO4J_COUNTS=""
if [ -z "$PYTHON_BIN" ]; then
  echo -e "  ${RED}✗${NC} Python is unavailable for the Neo4j probe"
  mark_degraded
elif [ -z "$NEO4J_PASSWORD" ]; then
  echo -e "  ${YELLOW}⚠${NC} NEO4J_PASSWORD is not configured; connectivity was not claimed"
  mark_degraded
else
  NEO4J_COUNTS="$(
    NEO4J_URI="$NEO4J_URI" NEO4J_USER="$NEO4J_USER" NEO4J_PASSWORD="$NEO4J_PASSWORD" \
      "$PYTHON_BIN" <<'PY' 2>/dev/null
import json
import os

from neo4j import GraphDatabase, Query

driver = GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    connection_timeout=5,
)
try:
    with driver.session() as session:
        nodes = session.run(Query("MATCH (n) RETURN count(n) AS count", timeout=8.0)).single(strict=True)["count"]
        relationships = session.run(Query("MATCH ()-[r]->() RETURN count(r) AS count", timeout=8.0)).single(strict=True)["count"]
    print(json.dumps({"nodes": int(nodes), "relationships": int(relationships)}))
finally:
    driver.close()
PY
  )"
  if [ -n "$NEO4J_COUNTS" ]; then
    NEO4J_NODES="$(printf '%s' "$NEO4J_COUNTS" | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["nodes"])')"
    NEO4J_RELATIONSHIPS="$(printf '%s' "$NEO4J_COUNTS" | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["relationships"])')"
    echo -e "  ${GREEN}✓${NC} Connectivity: OK"
    echo "  • Database: $NEO4J_NODES nodes, $NEO4J_RELATIONSHIPS relationships"
  else
    echo -e "  ${RED}✗${NC} Connectivity failed"
    mark_degraded
  fi
fi

if [ "$CONTAINER_RUNNING" = true ]; then
  NEO4J_DISK="$(docker exec atlas-neo4j du -sh /data 2>/dev/null | awk '{print $1}')"
  echo "  • Disk usage: ${NEO4J_DISK:-unknown}"
fi

if [ -n "$NEO4J_COUNTS" ] && [ -n "$PYTHON_BIN" ] && [ -f graphify-out/graph.json ]; then
  GRAPH_COUNTS="$("$PYTHON_BIN" - <<'PY' 2>/dev/null
import json
from pathlib import Path

graph = json.loads(Path("graphify-out/graph.json").read_text(encoding="utf-8"))
print(f"{len(graph.get('nodes', []))} {len(graph.get('links', []))}")
PY
  )"
  read -r GRAPH_NODES GRAPH_RELATIONSHIPS <<< "$GRAPH_COUNTS"
  if [ "${GRAPH_NODES:-}" = "${NEO4J_NODES:-}" ] \
    && [ "${GRAPH_RELATIONSHIPS:-}" = "${NEO4J_RELATIONSHIPS:-}" ]; then
    echo -e "  ${GREEN}✓${NC} Neo4j has count parity with graphify-out/graph.json"
    echo "    Content identity is not proven by this count-only check"
  else
    echo -e "  ${RED}✗${NC} Neo4j is out of sync with Graphify"
    echo "    Graphify: ${GRAPH_NODES:-unknown} nodes, ${GRAPH_RELATIONSHIPS:-unknown} relationships"
    mark_degraded
  fi
fi
echo

echo "🦙 Ollama Local LLM"
if command -v curl >/dev/null 2>&1 \
  && curl -sSf --max-time 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo -e "  ${GREEN}✓${NC} Service running"
  if [ -n "$PYTHON_BIN" ]; then
    MODELS="$(
      curl -sSf --max-time 3 http://127.0.0.1:11434/api/tags 2>/dev/null \
        | "$PYTHON_BIN" -c 'import json,sys; print(len(json.load(sys.stdin).get("models", [])))' 2>/dev/null
    )"
    echo "  • Models available: ${MODELS:-unknown}"
  fi
else
  echo -e "  ${YELLOW}⚠${NC} Service offline"
  mark_degraded
fi
echo

echo "📄 Graph Freshness"
if [ -f graphify-out/GRAPH_REPORT.md ]; then
  LAST_UPDATE="$(stat -c %y graphify-out/GRAPH_REPORT.md 2>/dev/null | cut -d' ' -f1-2)"
  HOURS_SINCE=$(( ( $(date +%s) - $(stat -c %Y graphify-out/GRAPH_REPORT.md) ) / 3600 ))
  BUILT_COMMIT="$(sed -n 's/^- Built from commit: `\([^`]*\)`.*/\1/p' graphify-out/GRAPH_REPORT.md | head -n 1)"
  CURRENT_COMMIT="$(git rev-parse --short=8 HEAD 2>/dev/null || true)"
  NEWER_INPUT="$(find src tests docs schemas scripts -type f \
    -newer graphify-out/GRAPH_REPORT.md -print -quit 2>/dev/null || true)"
  echo "  • Last update: $LAST_UPDATE ($HOURS_SINCE hours ago)"
  echo "  • Built commit: ${BUILT_COMMIT:-unknown}; HEAD: ${CURRENT_COMMIT:-unknown}"

  if [ -z "$BUILT_COMMIT" ] || [ -z "$CURRENT_COMMIT" ] \
    || [ "$BUILT_COMMIT" != "$CURRENT_COMMIT" ]; then
    echo -e "  ${RED}✗${NC} Graph report does not describe the current HEAD"
    mark_degraded
  elif [ -n "$NEWER_INPUT" ]; then
    echo -e "  ${YELLOW}⚠${NC} Graph report predates a corpus file: $NEWER_INPUT"
    mark_degraded
  elif [ "$HOURS_SINCE" -lt 24 ]; then
    echo -e "  ${GREEN}✓${NC} Graph report is current"
  elif [ "$HOURS_SINCE" -lt 168 ]; then
    echo -e "  ${YELLOW}⚠${NC} Graph report is aging"
    mark_degraded
  else
    echo -e "  ${RED}✗${NC} Graph report is stale"
    mark_degraded
  fi
else
  echo -e "  ${RED}✗${NC} GRAPH_REPORT.md not found"
  mark_critical
fi
echo

echo "💾 Disk Space"
DISK_USAGE="$(df /home | tail -1 | awk '{print $5}' | sed 's/%//')"
echo "  • /home usage: ${DISK_USAGE}%"
if [ "$DISK_USAGE" -lt 80 ]; then
  echo -e "  ${GREEN}✓${NC} Disk space: OK"
elif [ "$DISK_USAGE" -lt 90 ]; then
  echo -e "  ${YELLOW}⚠${NC} Disk space: WARNING"
  mark_degraded
else
  echo -e "  ${RED}✗${NC} Disk space: CRITICAL"
  mark_critical
fi
echo

echo "🔧 Automation"
HOOKS_PATH="$(git config --get core.hooksPath 2>/dev/null || true)"
if [ -z "$HOOKS_PATH" ]; then
  HOOKS_PATH="$(git rev-parse --git-path hooks 2>/dev/null || true)"
elif [[ "$HOOKS_PATH" != /* ]]; then
  HOOKS_PATH="$(pwd)/$HOOKS_PATH"
fi
POST_COMMIT="${HOOKS_PATH%/}/post-commit"
if [ -x "$POST_COMMIT" ] && grep -q '# graphify-hook-start' "$POST_COMMIT" 2>/dev/null; then
  echo -e "  ${GREEN}✓${NC} Graphify post-commit hook is active in Git's effective hooks path"
else
  echo -e "  ${YELLOW}⚠${NC} Graphify post-commit hook is not active in Git's effective hooks path"
  mark_degraded
fi
echo

echo "╔════════════════════════════════════════════════════════════════════╗"
case "$health_status" in
  HEALTHY)
    echo -e "║                    STATUS: ${GREEN}✓ HEALTHY${NC}                           ║"
    EXIT_CODE=0
    ;;
  DEGRADED)
    echo -e "║                   STATUS: ${YELLOW}⚠ DEGRADED${NC}                          ║"
    EXIT_CODE=1
    ;;
  *)
    echo -e "║                   STATUS: ${RED}✗ CRITICAL${NC}                          ║"
    EXIT_CODE=2
    ;;
esac
echo "╚════════════════════════════════════════════════════════════════════╝"
echo
exit "$EXIT_CODE"
