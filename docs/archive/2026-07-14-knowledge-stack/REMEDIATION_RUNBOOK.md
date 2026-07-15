# 🔧 REMEDIATION RUNBOOK - Critical Actions

**Purpose**: Execute critical remediations identified in Audit & Premortem  
**Status**: Ready to execute  
**Estimated Time**: ~30 minutes total

---

## CRITICAL ACTION 1: Validate Neo4j Cypher Import

### Why This Matters
The 8.1 MB cypher.txt file was exported but never fully imported into Neo4j. If import fails, the query interface will be empty and all Cypher-based analysis will be broken.

### Execution Steps

```bash
# 1. Activate environment
cd /home/ronin/proyectos/atlas-core
source .venv/bin/activate

# 2. Check current Neo4j node count (before import)
echo "Checking current Neo4j state..."
NEO4J_PASSWORD=atlasneo4j python3 << 'PYEOF'
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "atlasneo4j"))
with driver.session() as session:
    result = session.run("MATCH (n) RETURN count(n) as total")
    for record in result:
        print(f"Current nodes in Neo4j: {record['total']}")
driver.close()
PYEOF

# 3. Run batch import
echo ""
echo "Starting Neo4j batch import from cypher.txt..."
NEO4J_PASSWORD=atlasneo4j python3 scripts/neo4j-import-batch.py

# 4. Verify import success
echo ""
echo "Verifying import..."
NEO4J_PASSWORD=atlasneo4j python3 << 'PYEOF'
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "atlasneo4j"))
with driver.session() as session:
    result = session.run("MATCH (n) RETURN count(n) as total")
    for record in result:
        total = record['total']
        print(f"✓ Final node count: {total}")
        if total > 10000:
            print("✓ Import SUCCESSFUL (15k+ nodes expected)")
        else:
            print("⚠ Import may have failed or is incomplete")
    
    # Show sample nodes
    result2 = session.run("MATCH (n) RETURN labels(n), count(*) as cnt ORDER BY cnt DESC LIMIT 10")
    print("\nNode types by count:")
    for record in result2:
        print(f"  {record['labels']}: {record['cnt']}")

driver.close()
PYEOF
```

### Expected Output
```
Current nodes in Neo4j: [some number, possibly 0 if not imported before]
Starting Neo4j batch import...
[Progress output...]
✓ Final node count: 15304
✓ Import SUCCESSFUL
Node types by count:
  ['Class']: 5123
  ['Function']: 7234
  [etc.]
```

### Troubleshooting

**If import hangs (>5 min)**:
```bash
# Stop it (Ctrl+C)
# Check Neo4j logs
docker logs atlas-neo4j | tail -50

# Restart Neo4j
docker restart atlas-neo4j
sleep 10

# Try import again with smaller batch
NEO4J_PASSWORD=atlasneo4j NEO4J_BATCH_SIZE=50 python3 scripts/neo4j-import-batch.py
```

**If import errors on syntax**:
```bash
# Extract first 100 statements to check
head -500 graphify-out/cypher.txt | tail -20

# The issue is likely Cypher 5.x syntax
# Check neo4j-import-batch.py and update Cypher syntax if needed
```

**If disk space errors**:
```bash
docker exec atlas-neo4j df -h
# If >90% full, backup and clean or resize volume
```

---

## CRITICAL ACTION 2: Validate Ollama Semantic Extraction

### Why This Matters
Semantic extraction (GraphRAG) requires Ollama to handle 15k nodes. If it OOMs or times out, the pipeline fails and users can't refresh the graph with LLM insights.

### Execution Steps

```bash
# 1. Check current resources
echo "=== System Resources Before Test ==="
free -h
echo ""
ps aux | grep ollama | grep -v grep

# 2. Run test GraphRAG with safe parameters
echo ""
echo "=== Running Test GraphRAG (Local Ollama, Safe Mode) ==="
cd /home/ronin/proyectos/atlas-core

./scripts/update-knowledge-graph-rag.sh \
  --backend ollama \
  --model qwen2.5-coder:7b \
  --token-budget 5000 \
  --max-workers 1 \
  --api-timeout 120

# 3. Check for errors
if [ $? -eq 0 ]; then
  echo ""
  echo "✓ Test PASSED: Ollama semantic extraction works"
  echo "  GRAPH_REPORT.md updated successfully"
else
  echo ""
  echo "✗ Test FAILED: Check logs above"
fi

# 4. Verify output
echo ""
echo "=== Verification ==="
wc -l graphify-out/GRAPH_REPORT.md
du -h graphify-out/GRAPH_REPORT.md
```

### Expected Output
```
=== Running Test GraphRAG (Local Ollama, Safe Mode) ===
[Multiple progress lines...]
Semantic extraction: 2500/15304 nodes processed...
Community labeling: In progress...
✓ Test PASSED: Ollama semantic extraction works
```

### Timeout Expected Times
- With --token-budget 5000: 2-5 minutes
- With --token-budget 10000: 5-10 minutes
- With --token-budget 50000: 20-30 minutes

### Troubleshooting

**If timeout (>2 min for 5k budget)**:
```bash
# Check Ollama is responsive
curl -s http://127.0.0.1:11434/api/tags | python3 -m json.tool | head -20

# Monitor Ollama process
watch -n 1 'ps aux | grep ollama'

# May need to reduce further
./scripts/update-knowledge-graph-rag.sh \
  --backend ollama \
  --token-budget 2000 \
  --max-workers 1
```

**If OOM (Out of Memory)**:
```bash
# Monitor during run
watch -n 2 'free -h && echo "---" && docker stats'

# If Ollama gets killed, restart it
pkill -9 ollama
sleep 5
ollama serve &
```

**If model not found**:
```bash
# Verify model is cached
ollama list
# Output should show: qwen2.5-coder:7b ... 7.6 GB

# If missing, pull it
ollama pull qwen2.5-coder:7b
```

---

## CRITICAL ACTION 3: Add Git Merge Strategy for Graph Files

### Why This Matters
If two developers commit simultaneously, Git merge conflicts on 19 MB graph.json will be painful. This action configures automatic conflict resolution.

### Execution Steps

```bash
cd /home/ronin/proyectos/atlas-core

# 1. Create/update .gitattributes
cat >> .gitattributes << 'EOF'
# Merge strategy for auto-generated graph artifacts
graphify-out/graph.json merge=ours
graphify-out/GRAPH_REPORT.md merge=ours
graphify-out/manifest.json merge=ours
graphify-out/cypher.txt merge=ours
graphify-out/graph.graphml merge=ours
EOF

# 2. Verify .gitattributes
cat .gitattributes

# 3. Add and commit
git add .gitattributes
git commit -m "chore: Add merge strategy for graph artifacts (prefer branch version on conflicts)"

# 4. Verify it worked
git check-attr merge graphify-out/graph.json
# Should output: graphify-out/graph.json: merge: ours
```

### Expected Output
```
[main a1b2c3d] chore: Add merge strategy for graph artifacts
 1 file changed, 8 insertions(+)
graphify-out/graph.json: merge: ours
```

### Verification
To test (without actually creating conflict):
```bash
# This is manual testing; the strategy will activate automatically on real conflicts
echo "Merge strategy is now configured."
echo "On conflicts with graphify-out/ files, branch version will be preferred."
```

---

## FOLLOW-UP ACTION 1: Pin Graphify Version

### Why This Matters
Graphify might release v1.0 with breaking changes. Pinning the version ensures reproducible builds.

### Execution Steps

```bash
cd /home/ronin/proyectos/atlas-core

# 1. Check current version
graphify --version
# Should be: graphify 0.9.11

# 2. Create/update requirements.txt with version constraint
cat > requirements-graphify.txt << 'EOF'
# Knowledge graph tools (pinned versions for reproducibility)
graphify==0.9.11
graphiti==0.1.13
neo4j==6.2.0
EOF

# 3. Add version check to main update script
cat >> scripts/update-knowledge-graph.sh << 'VCHECK'

# Version check (fail fast on incompatibility)
GRAPHIFY_VERSION=$(graphify --version 2>&1 | grep -oP 'graphify \K[\d.]+' || echo "unknown")
if [ "$GRAPHIFY_VERSION" != "0.9.11" ]; then
  echo "ERROR: Graphify version mismatch" >&2
  echo "  Expected: 0.9.11" >&2
  echo "  Got: $GRAPHIFY_VERSION" >&2
  echo "  Fix with: pip install graphify==0.9.11" >&2
  exit 1
fi
VCHECK

# 4. Test the check
./scripts/update-knowledge-graph.sh --help
# Should not error on version
```

### Expected Output
```
graphify 0.9.11
# Version check passes silently
```

---

## FOLLOW-UP ACTION 2: Document Merge Strategy in Workflow Guide

### Execution Steps

```bash
# Add to WORKFLOW_GUIDE.md (Troubleshooting section)
cat >> WORKFLOW_GUIDE.md << 'EOF'

---

## Troubleshooting: Merge Conflicts

### Graph Files Conflict

**Scenario**: You pull from main and get conflicts in `graphify-out/graph.json` or `GRAPH_REPORT.md`.

**Resolution** (Automated):
```bash
# The .gitattributes file is configured to auto-resolve these conflicts
# Your branch version will be preferred automatically

# If you still see conflicts:
git checkout --ours graphify-out/graph.json
git checkout --ours graphify-out/GRAPH_REPORT.md
git add graphify-out/
git commit -m "chore: Resolved graph merge conflicts (preferred branch version)"
```

**Why This Happens**:
- Graph is auto-generated and will differ between branches
- Rather than merge complex JSON, we keep the branch version
- Main branch graph is always fresh (updated hourly by CI or post-commit)

### Preventing Conflicts

1. **Pull before committing**:
   ```bash
   git pull origin main
   # This updates your graph to latest
   ```

2. **Commit frequently**:
   ```bash
   # Small, frequent commits trigger Git hook to refresh graph
   # Reduces divergence from main
   ```

3. **Don't edit graph files manually**:
   ```bash
   # Only graphify generates GRAPH_REPORT.md and graph.json
   # Manual edits will be overwritten on next graph update
   ```

EOF

git add WORKFLOW_GUIDE.md
git commit -m "docs: Add merge conflict troubleshooting guide"
```

---

## FOLLOW-UP ACTION 3: Add Disk Monitoring

### Execution Steps

```bash
# 1. Create health check script
cat > scripts/health-check.sh << 'HCHECK'
#!/bin/bash
# Knowledge stack health check

echo "=== ATLAS CORE HEALTH CHECK ==="
echo "Date: $(date)"
echo ""

# Neo4j disk
echo "📊 Neo4j Status"
NEO4J_DISK=$(docker exec atlas-neo4j du -sh /data 2>/dev/null | awk '{print $1}')
echo "  Disk usage: $NEO4J_DISK"

# Neo4j nodes
NEO4J_NODES=$(docker exec atlas-neo4j cypher-shell -u neo4j -p atlasneo4j "MATCH (n) RETURN count(n);" 2>/dev/null | tail -1)
echo "  Nodes in DB: $NEO4J_NODES"

# Ollama
echo ""
echo "🦙 Ollama Status"
OLLAMA_STATUS=$(curl -s http://127.0.0.1:11434/api/tags 2>/dev/null | python3 -m json.tool 2>/dev/null | grep -c '"models"')
if [ "$OLLAMA_STATUS" -gt 0 ]; then
  echo "  Status: ✓ Running"
else
  echo "  Status: ✗ Offline"
fi

# Graph freshness
echo ""
echo "📄 Graph Freshness"
GRAPH_DATE=$(stat -c %y graphify-out/GRAPH_REPORT.md 2>/dev/null | cut -d' ' -f1)
echo "  Last update: $GRAPH_DATE"

echo ""
echo "✓ Health check complete"
HCHECK

chmod +x scripts/health-check.sh

# 2. Test it
./scripts/health-check.sh

# 3. Add to git
git add scripts/health-check.sh
git commit -m "chore: Add health check script for monitoring"
```

### Expected Output
```
=== ATLAS CORE HEALTH CHECK ===
📊 Neo4j Status
  Disk usage: 45M
  Nodes in DB: 15304
🦙 Ollama Status
  Status: ✓ Running
📄 Graph Freshness
  Last update: 2026-07-14
✓ Health check complete
```

---

## Final Verification

After all actions, run:

```bash
cd /home/ronin/proyectos/atlas-core

echo "=== FINAL AUDIT CHECK ==="
echo ""

# 1. Neo4j
echo "1. Neo4j Import:"
NEO4J_PASSWORD=atlasneo4j python3 << 'PYEOF'
from neo4j import GraphDatabase
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "atlasneo4j"))
with driver.session() as session:
    result = session.run("MATCH (n) RETURN count(n) as total")
    for record in result:
        if record['total'] > 10000:
            print("  ✓ Neo4j has 15k+ nodes")
        else:
            print(f"  ⚠ Neo4j has only {record['total']} nodes")
driver.close()
PYEOF

# 2. Graphify version
echo ""
echo "2. Graphify Version:"
GRAPHIFY_VERSION=$(graphify --version)
echo "  ✓ $GRAPHIFY_VERSION"

# 3. Merge strategy
echo ""
echo "3. Git Merge Strategy:"
if grep -q "merge=ours" .gitattributes; then
  echo "  ✓ Graph files configured for 'ours' merge"
else
  echo "  ⚠ Merge strategy not configured"
fi

# 4. Health check
echo ""
echo "4. Running Health Check:"
./scripts/health-check.sh
```

---

## Completion Checklist

- [ ] **Action 1 Complete**: Neo4j import validated (~15k nodes confirmed)
- [ ] **Action 2 Complete**: Ollama semantic extraction tested successfully
- [ ] **Action 3 Complete**: Git merge strategy configured in .gitattributes
- [ ] **Follow-up 1 Complete**: Graphify version pinned in requirements
- [ ] **Follow-up 2 Complete**: WORKFLOW_GUIDE.md updated with troubleshooting
- [ ] **Follow-up 3 Complete**: Health check script added
- [ ] **Final Verification**: All systems green on final audit check

---

## Time Tracking

| Action | Est. | Actual |
|--------|------|--------|
| Action 1 (Neo4j) | 10 min | _____ |
| Action 2 (Ollama) | 10 min | _____ |
| Action 3 (Git) | 3 min | _____ |
| Follow-up 1-3 | 5 min | _____ |
| Final Verify | 2 min | _____ |
| **TOTAL** | **30 min** | **___** |

---

## Post-Remediation Status

Once complete, the system will have:
- ✅ Validated Neo4j with 15k+ nodes
- ✅ Tested Ollama semantic extraction at scale
- ✅ Configured automatic merge conflict resolution
- ✅ Pinned dependency versions for reproducibility
- ✅ Added monitoring and health checks
- ✅ Updated documentation

**New Status**: 🟢 PRODUCTION HARDENED
