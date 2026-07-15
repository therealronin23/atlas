#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF' >&2
Usage: ./scripts/install-knowledge-hooks.sh

Install Graphify's maintained post-commit and post-checkout hooks in Git's
effective hooks path.
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

if [ "$#" -ne 0 ]; then
  echo "ERROR: this command accepts no arguments." >&2
  usage
  exit 2
fi

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "ERROR: not inside a Git repository." >&2
  exit 1
fi

if [ ! -x .venv/bin/graphify ]; then
  echo "ERROR: .venv/bin/graphify is unavailable." >&2
  exit 1
fi

GRAPHIFY_VERSION="$(.venv/bin/graphify --version 2>&1 | awk 'NR == 1 {print $2}')"
if [ "$GRAPHIFY_VERSION" != "0.9.11" ]; then
  echo "ERROR: Graphify version mismatch (expected 0.9.11, got ${GRAPHIFY_VERSION:-unknown})." >&2
  exit 1
fi

# Use Graphify's maintained installer.  It honours core.hooksPath, composes
# with existing hooks, pins the working interpreter and launches rebuilds in a
# detached, locked process.  The previous local template wrote .git/hooks even
# when Git was configured to use .githooks, so the installed hook was inert.
.venv/bin/graphify hook install

echo "Graphify knowledge hooks installed in Git's effective hooks directory."
