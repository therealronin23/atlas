#!/usr/bin/env bash
# ============================================================================
# fix_hermes_user_unit.sh — Hermes registró su unit como USER-LEVEL.
#
# `hermes gateway install` creó:
#   /root/.config/systemd/user/hermes-gateway.service
# (no /etc/systemd/system/, que es donde miraba nuestro script).
#
# Para que un user-level systemd corra sin login activo hay que habilitar
# 'linger' en el usuario. Si no, systemd-user muere cuando root se desloguea.
#
# Idempotente. Aplicar en VPS como root:
#   ssh root@<ip> 'bash -s' < scripts/fix_hermes_user_unit.sh
# ============================================================================
set -euo pipefail

UNIT_PATH=/root/.config/systemd/user/hermes-gateway.service
HERMES_HOME=/root/.hermes

log() { echo "[fix-user-unit] $*"; }

if [[ ! -f "$UNIT_PATH" ]]; then
    echo "ERROR: $UNIT_PATH no existe" >&2
    exit 1
fi
log "✓ Encontrada unit user-level: $UNIT_PATH"

log "1/4 Habilitar linger en root (sobrevive a logout)"
loginctl enable-linger root
loginctl show-user root --property=Linger

log "2/4 Reload + enable + start (systemctl --user)"
# Necesitamos XDG_RUNTIME_DIR seteado para que systemctl --user funcione
export XDG_RUNTIME_DIR="/run/user/$(id -u root)"
mkdir -p "$XDG_RUNTIME_DIR"
systemctl --user daemon-reload
systemctl --user enable hermes-gateway.service
systemctl --user restart hermes-gateway.service

sleep 6

log "3/4 Estado del servicio"
systemctl --user status hermes-gateway.service --no-pager 2>&1 | head -15

log "4/4 Últimos logs"
journalctl --user -u hermes-gateway.service --no-pager -n 25 2>&1 | tail -25

echo ""
echo "============= CONFIG ============="
echo "Allowlist Telegram:"
grep -E '^TELEGRAM_ALLOWED_USERS' "${HERMES_HOME}/.env" 2>/dev/null || echo "  ✗ NO configurada"
echo ""
echo "Providers en config.yaml (chain primary + fallbacks):"
grep -E "^\s*(provider|model|default):" "${HERMES_HOME}/config.yaml" 2>/dev/null | head -25
echo ""
echo "============= COMANDOS ÚTILES POR SI TIENES QUE TOCAR DESPUÉS ============="
echo "  ssh root@... 'systemctl --user status hermes-gateway'"
echo "  ssh root@... 'systemctl --user restart hermes-gateway'"
echo "  ssh root@... 'journalctl --user -u hermes-gateway -f'"
echo ""
echo "👉 Ahora manda /start a @GodAtlas_bot en Telegram."
