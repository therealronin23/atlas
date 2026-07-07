#!/usr/bin/env bash
# Pieza 3 — hook de routing determinista (Claude Code + Cursor).
set -euo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-${CURSOR_PROJECT_DIR:-.}}"
cd "$ROOT"
if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
if [ -n "${PYTHONPATH:-}" ]; then
  export PYTHONPATH="$ROOT/src:$PYTHONPATH"
else
  export PYTHONPATH="$ROOT/src"
fi
exec python scripts/capability_route_hook.py "$@"
