#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

OUT_DIR="${1:-notebooklm-package}"
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

cat > "$OUT_DIR/README.md" <<'EOF'
# NotebookLM package for atlas-core

This package is optimized for NotebookLM ingestion:

1. Start with `00-Graphify-Report.md` for architecture and graph context.
2. Read `01-Repository-README.md` and `docs/*.md` for project-specific design.
3. Use the Obsidian vault only if you need node-level code/document connections.

To include the full Obsidian vault, add `--include-vault` and use the generated notes carefully.
EOF

printf 'NotebookLM package prepared at %s\n' "$(pwd)/$OUT_DIR"
printf 'If you want to include the Obsidian vault notes, copy them from graphify-vault/ separately.\n'
