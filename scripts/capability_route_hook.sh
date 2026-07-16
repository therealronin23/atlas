#!/usr/bin/env bash
# Pieza 3 — hook de routing determinista (Claude Code + Cursor + Codex).
set -euo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-${CURSOR_PROJECT_DIR:-}}"
if [ -z "$ROOT" ]; then
  ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fi
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
