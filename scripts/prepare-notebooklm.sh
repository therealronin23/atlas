#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

OUT_DIR="notebooklm-package"
VAULT_ROOT="graphify-vault"
INCLUDE_VAULT=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --out)
      shift
      OUT_DIR="${1:-$OUT_DIR}"
      ;;
    --vault-root)
      shift
      VAULT_ROOT="${1:-$VAULT_ROOT}"
      ;;
    --include-vault)
      INCLUDE_VAULT=true
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
  shift
done

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR/docs"
mkdir -p "$OUT_DIR/graphify"

cp graphify-out/GRAPH_REPORT.md "$OUT_DIR/00-Graphify-Report.md"
cp README.md "$OUT_DIR/01-Repository-README.md" 2>/dev/null || true
cp pyproject.toml "$OUT_DIR/02-Package-Metadata.md" 2>/dev/null || true

if [ -d docs ]; then
  find docs -maxdepth 2 -type f -name '*.md' -print0 | while IFS= read -r -d '' file; do
    dest="$OUT_DIR/$file"
    mkdir -p "$(dirname "$dest")"
    cp "$file" "$dest"
  done
fi

if [ "$INCLUDE_VAULT" = true ] && [ -d "$VAULT_ROOT" ]; then
  mkdir -p "$OUT_DIR/vault"
  echo "Including Obsidian vault from $VAULT_ROOT into $OUT_DIR/vault"
  cp -r "$VAULT_ROOT"/* "$OUT_DIR/vault/"
fi

cat > "$OUT_DIR/README.md" <<'EOF'
# NotebookLM package for atlas-core

This package is optimized for NotebookLM ingestion:

1. Start with `00-Graphify-Report.md` for architecture and graph context.
2. Read `01-Repository-README.md` and `docs/*.md` for project-specific design.
3. Use the Obsidian vault only if you need node-level code/document connections.

If the vault is included, the notes are copied into `vault/`.

To include the full Obsidian vault, rerun with `--include-vault`.
EOF

printf 'NotebookLM package prepared at %s\n' "$(pwd)/$OUT_DIR"
if [ "$INCLUDE_VAULT" = true ]; then
  printf 'Included Obsidian vault notes from %s\n' "$(pwd)/$VAULT_ROOT"
else
  printf 'If you want the full Obsidian vault, rerun with --include-vault.\n'
fi
