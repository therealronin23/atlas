#!/usr/bin/env bash
# Lanzador de workspace-mcp SIN secretos en argv/config (mitigación del
# hallazgo del audit 2026-07-16: el cliente Claude pasa la config MCP entera
# como argumento de línea de comandos, y /proc/<pid>/cmdline es legible —
# cualquier secreto inline en la config del conector queda expuesto).
#
# Uso: apuntar el conector google-workspace a ESTE script en vez de a
# `uvx workspace-mcp` con GOOGLE_OAUTH_CLIENT_SECRET inline. El secreto vive
# en un fichero 0600 fuera del repo y se inyecta al hijo vía safe_dotenv.py
# (el mecanismo bendecido del repo — jamás `source` de shell, ver
# tests/test_safe_dotenv.py). Runbook completo:
# docs/operations/oauth_rotation_google_workspace.md
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRET_FILE="${GOOGLE_OAUTH_SECRET_FILE:-$HOME/.config/atlas/google-oauth.env}"

if [[ ! -f "$SECRET_FILE" ]]; then
  cat >&2 <<EOF
ERROR: falta $SECRET_FILE
Créalo (0600) con:
  GOOGLE_OAUTH_CLIENT_ID=<id>.apps.googleusercontent.com
  GOOGLE_OAUTH_CLIENT_SECRET=<secreto ROTADO, jamás el expuesto>
EOF
  exit 78
fi

perms="$(stat -c '%a' "$SECRET_FILE")"
if [[ "$perms" != "600" && "$perms" != "400" ]]; then
  echo "ERROR: $SECRET_FILE debe ser 0600/0400 (es $perms)" >&2
  exit 78
fi

exec python3 "$ROOT_DIR/scripts/safe_dotenv.py" "$SECRET_FILE" -- \
  uvx workspace-mcp "$@"
