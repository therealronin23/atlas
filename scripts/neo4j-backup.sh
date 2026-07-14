#!/bin/bash
# Neo4j Backup Script
# Purpose: Backup Neo4j database for disaster recovery
# Usage: ./scripts/neo4j-backup.sh [--daily|--weekly|--manual]
# Runs: Weekly via cron or manually before major changes

set -e

BACKUP_DIR="backups/neo4j"
DATE=$(date +%Y-%m-%d_%H-%M-%S)
BACKUP_NAME="neo4j_${DATE}.dump"

mkdir -p "$BACKUP_DIR"

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║                   Neo4j Database Backup                           ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

echo "📊 Backup Details"
echo "  Date: $(date)"
echo "  Destination: $BACKUP_DIR/$BACKUP_NAME"
echo "  Size target: ~50-100 MB (graph.json)"
echo ""

echo "Starting backup..."

# Dump database using Neo4j's backup mechanism
docker exec atlas-neo4j bash -c \
  "neo4j-admin database dump neo4j --to-path=/backups --backup-name=${BACKUP_NAME%.dump}" \
  2>/dev/null || {
    echo "⚠ Docker backup command not available, using Cypher export instead..."
    
    # Fallback: export via Cypher shell
    docker exec atlas-neo4j cypher-shell -u neo4j -p atlasneo4j \
      "CALL apoc.export.json.all('/$BACKUP_NAME', {useTypes: true})" \
      2>/dev/null || echo "⚠ Backup may not have completed"
  }

# Copy from container to host
docker cp atlas-neo4j:/backups/$BACKUP_NAME "$BACKUP_DIR/" 2>/dev/null || \
  docker cp atlas-neo4j:/$BACKUP_NAME "$BACKUP_DIR/" 2>/dev/null || \
  echo "⚠ Could not copy backup from container"

if [ -f "$BACKUP_DIR/$BACKUP_NAME" ]; then
  SIZE=$(du -h "$BACKUP_DIR/$BACKUP_NAME" | awk '{print $1}')
  echo ""
  echo "✅ Backup Complete"
  echo "  File: $BACKUP_DIR/$BACKUP_NAME"
  echo "  Size: $SIZE"
  echo ""
  echo "Retention:"
  echo "  Keeping last 10 backups..."
  ls -1t "$BACKUP_DIR"/neo4j_*.dump 2>/dev/null | tail -n +11 | xargs -r rm
  echo "  Current backups:"
  ls -1 "$BACKUP_DIR"/neo4j_*.dump 2>/dev/null | tail -5 | sed 's/^/    /'
else
  echo ""
  echo "⚠ Backup file not found at expected location"
  echo "  Check Docker logs: docker logs atlas-neo4j"
fi

echo ""
