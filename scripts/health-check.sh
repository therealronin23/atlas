#!/bin/bash
# Knowledge Stack Health Check
# Monitors: Neo4j, Ollama, Graph freshness, Disk usage
# Run weekly: ./scripts/health-check.sh

set -e

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║         ATLAS CORE KNOWLEDGE STACK - HEALTH CHECK                 ║"
echo "║                     $(date '+%Y-%m-%d %H:%M:%S')                        ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

health_status="HEALTHY"

# ========================================================================
# 1. Neo4j Database Health
# ========================================================================

echo "📊 Neo4j Database"
if docker ps --filter "name=atlas-neo4j" --format "{{.Status}}" | grep -q "Up"; then
  echo -e "  ${GREEN}✓${NC} Container status: RUNNING"
  
  # Check connectivity
  if NEO4J_PASSWORD=atlasneo4j python3 << 'PYEOF' 2>/dev/null; then
from neo4j import GraphDatabase
try:
    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "atlasneo4j"), connection_timeout=5)
    with driver.session() as session:
        result = session.run("MATCH (n) RETURN count(n) as total")
        for record in result:
            total = record['total']
            print(f"  ✓ Connectivity: OK")
            print(f"  ✓ Nodes in DB: {total}")
            if total < 10000:
                print(f"  ⚠ WARNING: Expected 15k+ nodes")
    driver.close()
except Exception as e:
    print(f"  ✗ Connection failed: {e}")
PYEOF
  then
    :
  else
    echo -e "  ${RED}✗${NC} Connection failed"
    health_status="DEGRADED"
  fi
  
  # Check disk usage
  NEO4J_DISK=$(docker exec atlas-neo4j du -sh /data 2>/dev/null | awk '{print $1}')
  echo "  ✓ Disk usage: $NEO4J_DISK"
else
  echo -e "  ${RED}✗${NC} Container NOT RUNNING"
  health_status="CRITICAL"
fi

echo ""

# ========================================================================
# 2. Ollama LLM Health
# ========================================================================

echo "🦙 Ollama Local LLM"
if curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo -e "  ${GREEN}✓${NC} Service running"
  
  # Count models
  MODELS=$(curl -s http://127.0.0.1:11434/api/tags 2>/dev/null | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data.get('models', [])))" 2>/dev/null || echo "?")
  echo "  ✓ Models available: $MODELS"
else
  echo -e "  ${RED}✗${NC} Service offline"
  health_status="DEGRADED"
fi

echo ""

# ========================================================================
# 3. Graph Freshness
# ========================================================================

echo "📄 Graph Freshness"
if [ -f graphify-out/GRAPH_REPORT.md ]; then
  LAST_UPDATE=$(stat -c %y graphify-out/GRAPH_REPORT.md 2>/dev/null | cut -d' ' -f1-2)
  HOURS_SINCE=$(( ($(date +%s) - $(stat -c %Y graphify-out/GRAPH_REPORT.md 2>/dev/null)) / 3600 ))
  
  echo "  ✓ Last update: $LAST_UPDATE"
  echo "  ✓ Hours since: $HOURS_SINCE"
  
  if [ $HOURS_SINCE -lt 24 ]; then
    echo -e "  ${GREEN}✓${NC} Graph is fresh (< 24 hours)"
  elif [ $HOURS_SINCE -lt 168 ]; then
    echo -e "  ${YELLOW}⚠${NC} Graph is aging ($HOURS_SINCE hours old)"
  else
    echo -e "  ${RED}✗${NC} Graph is stale (> 7 days)"
    health_status="DEGRADED"
  fi
else
  echo -e "  ${RED}✗${NC} GRAPH_REPORT.md not found"
  health_status="CRITICAL"
fi

echo ""

# ========================================================================
# 4. Disk Space
# ========================================================================

echo "💾 Disk Space"
DISK_USAGE=$(df /home | tail -1 | awk '{print $5}' | sed 's/%//')
echo "  • /home usage: ${DISK_USAGE}%"

if [ "$DISK_USAGE" -lt 80 ]; then
  echo -e "  ${GREEN}✓${NC} Disk space: OK"
elif [ "$DISK_USAGE" -lt 90 ]; then
  echo -e "  ${YELLOW}⚠${NC} Disk space: WARNING (${DISK_USAGE}%)"
  health_status="DEGRADED"
else
  echo -e "  ${RED}✗${NC} Disk space: CRITICAL (${DISK_USAGE}%)"
  health_status="CRITICAL"
fi

echo ""

# ========================================================================
# 5. Git Hook Status
# ========================================================================

echo "🔧 Automation"
if [ -x .git/hooks/post-commit ]; then
  echo -e "  ${GREEN}✓${NC} Git hook: INSTALLED"
else
  echo -e "  ${RED}✗${NC} Git hook: NOT INSTALLED"
  health_status="DEGRADED"
fi

echo ""

# ========================================================================
# Summary
# ========================================================================

echo "╔════════════════════════════════════════════════════════════════════╗"
if [ "$health_status" = "HEALTHY" ]; then
  echo -e "║                    STATUS: ${GREEN}✓ HEALTHY${NC}                           ║"
  EXIT_CODE=0
elif [ "$health_status" = "DEGRADED" ]; then
  echo -e "║                   STATUS: ${YELLOW}⚠ DEGRADED${NC}                          ║"
  EXIT_CODE=1
else
  echo -e "║                   STATUS: ${RED}✗ CRITICAL${NC}                          ║"
  EXIT_CODE=2
fi
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

exit $EXIT_CODE
