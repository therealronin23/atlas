#!/usr/bin/env bash
# ============================================================================
# fix_hermes_install_unit.sh — Recupera el systemd unit de Hermes-Agent.
#
# El finalize_hermes_vps.sh ANTERIOR llamó `hermes gateway service install`
# (subcomando inexistente) y borró la unit custom antes de fallar. Resultado:
# sin unit registrada. Este script reinstala usando el subcomando correcto:
# `hermes gateway install` y arranca el servicio.
#
# Idempotente. Aplicar en VPS como root:
#   ssh root@<ip> 'bash -s' < scripts/fix_hermes_install_unit.sh
# ============================================================================
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
HERMES_BIN="${HERMES_HOME}/venv/bin/hermes"
log() { echo "[fix-unit] $*"; }

if [[ ! -x "$HERMES_BIN" ]]; then
    echo "ERROR: $HERMES_BIN no existe" >&2
    exit 1
fi

log "1/4 Limpiar units residuales (custom + posibles intentos previos)"
systemctl stop hermes-agent hermes-gateway 2>/dev/null || true
rm -f /etc/systemd/system/hermes-agent.service /etc/systemd/system/hermes-gateway.service
systemctl daemon-reload

log "2/4 Instalar systemd unit oficial vía 'hermes gateway install'"
"$HERMES_BIN" gateway install 2>&1 | tail -15 || true

log "3/4 Identificar la unit que Hermes registró"
NEW_UNIT=$(systemctl list-unit-files --no-pager --type=service 2>/dev/null \
    | grep -iE "^hermes" | awk '{print $1}' | head -1)
if [[ -z "$NEW_UNIT" ]]; then
    log "  (no se detectó unit todavía, buscando en /etc/systemd/system/)"
    NEW_UNIT=$(find /etc/systemd/system/ -maxdepth 1 -name "*hermes*.service" -printf "%f\n" | head -1)
fi
log "  unit: ${NEW_UNIT:-(none)}"

if [[ -z "$NEW_UNIT" ]]; then
    log "  WARNING: Hermes no generó systemd unit. Intentando 'hermes gateway start' (fallback)"
    "$HERMES_BIN" gateway start 2>&1 | tail -10 || true
fi

log "4/4 Arrancar y verificar"
if [[ -n "$NEW_UNIT" ]]; then
    systemctl enable "$NEW_UNIT" 2>&1 | tail -3 || true
    systemctl start "$NEW_UNIT"
    sleep 6
    echo ""
    echo "============= ESTADO ============="
    echo "Unit: $NEW_UNIT"
    systemctl status "$NEW_UNIT" --no-pager 2>&1 | head -15
    echo ""
    echo "Últimos 20 logs:"
    journalctl -u "$NEW_UNIT" --no-pager -n 20 2>&1 | tail -20
fi

echo ""
echo "============= Allowlist Telegram ============="
grep -E '^TELEGRAM_ALLOWED_USERS' "${HERMES_HOME}/.env" 2>/dev/null || \
    echo "  ✗ TELEGRAM_ALLOWED_USERS no está en .env"
echo ""
echo "👉 Manda /start a @GodAtlas_bot en Telegram"
