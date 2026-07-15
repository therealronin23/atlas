#!/usr/bin/env bash
# Instala Atlas Core como servicio systemd de usuario y no declara éxito hasta
# que la unidad (y, si está habilitado, su health HTTP) estén realmente listos.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="${USER:-$(whoami)}"
UNIT_NAME="atlas-core.service"
UNIT_DST="$HOME/.config/systemd/user/$UNIT_NAME"
READY_TIMEOUT_SECONDS="${ATLAS_INSTALL_READY_TIMEOUT_SECONDS:-30}"

log() { echo "[install-atlas-systemd] $*"; }

if ! [[ "$READY_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: ATLAS_INSTALL_READY_TIMEOUT_SECONDS must be a positive integer" >&2
  exit 2
fi

log "1/4 Instalar la unidad de usuario"
mkdir -p "$(dirname "$UNIT_DST")"
sed "s|/home/ronin/proyectos/atlas-core|$REPO_ROOT|g" \
  "$REPO_ROOT/scripts/atlas-core.service" >"$UNIT_DST"
chmod 600 "$UNIT_DST"

log "2/4 Verificar linger"
linger="$(loginctl show-user "$USER_NAME" -p Linger --value 2>/dev/null || true)"
if [ "$linger" != "yes" ]; then
  if ! sudo loginctl enable-linger "$USER_NAME"; then
    echo "ERROR: linger is required for Atlas to survive logout" >&2
    exit 1
  fi
  linger="$(loginctl show-user "$USER_NAME" -p Linger --value 2>/dev/null || true)"
  if [ "$linger" != "yes" ]; then
    echo "ERROR: linger did not become active" >&2
    exit 1
  fi
fi

log "3/4 Recargar y arrancar"
systemctl --user daemon-reload
systemctl --user enable --now "$UNIT_NAME"
if ! systemctl --user is-enabled --quiet "$UNIT_NAME"; then
  echo "ERROR: $UNIT_NAME is not enabled" >&2
  exit 1
fi

dashboard_enabled=0
if [ -f "$REPO_ROOT/.env" ] \
  && grep -Eiq '^ATLAS_SERVE_DASHBOARD=(1|true|yes)[[:space:]]*$' "$REPO_ROOT/.env"; then
  dashboard_enabled=1
fi

health_file="$(mktemp)"
trap 'rm -f "$health_file"' EXIT
ready=0
for ((attempt = 1; attempt <= READY_TIMEOUT_SECONDS; attempt++)); do
  if systemctl --user is-active --quiet "$UNIT_NAME"; then
    if [ "$dashboard_enabled" -eq 0 ]; then
      ready=1
      break
    fi
    if curl -fsS --max-time 2 http://127.0.0.1:7331/api/health >"$health_file" \
      && python3 - "$health_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
if not isinstance(payload, dict) or not payload.get("version"):
    raise SystemExit(1)
PY
    then
      ready=1
      break
    fi
  fi
  sleep 1
done

if [ "$ready" -ne 1 ]; then
  echo "ERROR: $UNIT_NAME did not become ready in ${READY_TIMEOUT_SECONDS}s" >&2
  systemctl --user status "$UNIT_NAME" --no-pager >&2 || true
  exit 1
fi

log "4/4 Verificación completada"
systemctl --user is-active "$UNIT_NAME"
systemctl --user is-enabled "$UNIT_NAME"
if [ "$dashboard_enabled" -eq 1 ]; then
  python3 - "$health_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    health = json.load(handle)
print(
    f"Atlas {health.get('version')} "
    f"merkle={health.get('merkle_chain_ok')} "
    f"hermes_mode={health.get('hermes_mode')}"
)
PY
fi

echo "Logs: journalctl --user -u $UNIT_NAME -f"
