#!/usr/bin/env bash
# Consistent local Neo4j dump. The database is stopped briefly because the
# Community `neo4j-admin database dump` command cannot dump a mounted database.
set -euo pipefail
umask 077

usage() {
  cat >&2 <<'EOF'
Usage: scripts/neo4j-backup.sh [--daily|--weekly|--manual]

Creates an atomic Neo4j dump under backups/neo4j, keeps the latest ten, and
restarts the container if this script stopped it. Override with
NEO4J_CONTAINER, NEO4J_DATABASE, or NEO4J_BACKUP_DIR.
EOF
}

case "${1:---manual}" in
  --daily|--weekly|--manual) ;;
  -h|--help) usage; exit 0 ;;
  *) usage; exit 2 ;;
esac

command -v docker >/dev/null 2>&1 || {
  echo "ERROR: docker is required" >&2
  exit 1
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${NEO4J_BACKUP_DIR:-$REPO_ROOT/backups/neo4j}"
CONTAINER="${NEO4J_CONTAINER:-atlas-neo4j}"
DATABASE="${NEO4J_DATABASE:-neo4j}"
BACKUP_NAME="${DATABASE}_$(date -u +%Y-%m-%dT%H-%M-%SZ).dump"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

running="$(docker inspect --format '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" || {
  echo "ERROR: Neo4j container not found: $CONTAINER" >&2
  exit 1
}
image="$(docker inspect --format '{{.Config.Image}}' "$CONTAINER")"
if [ -z "$image" ]; then
  echo "ERROR: cannot determine image for $CONTAINER" >&2
  exit 1
fi

temporary="$(mktemp "$BACKUP_DIR/.neo4j-dump.XXXXXX")"
chmod 600 "$temporary"
stopped_by_us=0

cleanup() {
  rm -f "$temporary"
  if [ "$stopped_by_us" -eq 1 ]; then
    if ! docker start "$CONTAINER" >/dev/null; then
      echo "CRITICAL: backup failed and $CONTAINER could not be restarted" >&2
    fi
  fi
}
trap cleanup EXIT INT TERM

if [ "$running" = "true" ]; then
  docker stop --time 30 "$CONTAINER" >/dev/null
  stopped_by_us=1
fi

if ! docker run --rm \
  --volumes-from "$CONTAINER" \
  --entrypoint neo4j-admin \
  "$image" database dump "$DATABASE" --to-stdout >"$temporary"; then
  echo "ERROR: neo4j-admin dump failed; no backup was published" >&2
  exit 1
fi
if [ ! -s "$temporary" ]; then
  echo "ERROR: neo4j-admin produced an empty dump" >&2
  exit 1
fi

final_path="$BACKUP_DIR/$BACKUP_NAME"
mv "$temporary" "$final_path"
chmod 600 "$final_path"

if [ "$stopped_by_us" -eq 1 ]; then
  docker start "$CONTAINER" >/dev/null
  stopped_by_us=0
fi
trap - EXIT INT TERM

mapfile -t backups < <(
  find "$BACKUP_DIR" -maxdepth 1 -type f -name "${DATABASE}_*.dump" \
    -printf '%T@ %p\n' | sort -rn | cut -d ' ' -f 2-
)
for ((i = 10; i < ${#backups[@]}; i++)); do
  rm -f -- "${backups[$i]}"
done

size="$(du -h "$final_path" | awk '{print $1}')"
echo "Backup verified non-empty: $final_path ($size)"
