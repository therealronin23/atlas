#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
GIT_HOOK_DIR="$(git rev-parse --git-dir)/hooks"
mkdir -p "$GIT_HOOK_DIR"
ln -sf "$(pwd)/scripts/hooks/post-commit" "$GIT_HOOK_DIR/post-commit"
chmod +x "scripts/hooks/post-commit"
printf 'Installed git hook: %s/post-commit\n' "$GIT_HOOK_DIR"
printf 'Run ./scripts/update-knowledge-graph.sh manually or let the hook run it on commit.\n'
