#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -d ".git/hooks" ]; then
  echo "ERROR: .git/hooks directory not found. Run this from a Git repository root." >&2
  exit 1
fi

HOOK_FILE=".git/hooks/post-commit"
cat > "$HOOK_FILE" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
CHANGED=$(git diff-tree --no-commit-id --name-only -r HEAD)
if printf '%s\n' "$CHANGED" | grep -Eq '^(src/|docs/|README\.md$|AGENTS\.md$|agents\.md$|scripts/|.*\.md$)'; then
  printf 'Detected knowledge artefact changes in this commit. Running lightweight Graphify update...\n'
  ./scripts/update-knowledge-graph.sh
fi
EOF

chmod +x "$HOOK_FILE"
echo "Installed Git hook: $HOOK_FILE"
echo "The post-commit hook will run ./scripts/update-knowledge-graph.sh after commits that touch source, docs, scripts, or .md files."
