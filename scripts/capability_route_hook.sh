#!/usr/bin/env bash
# Pieza 3 — hook de routing determinista (Claude Code + Cursor).
set -euo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-${CURSOR_PROJECT_DIR:-.}}"
cd "$ROOT"
if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
export PYTHONPATH=src
exec python scripts/capability_route_hook.py "$@"
