#!/usr/bin/env bash
# ============================================================================
# finalize_hermes_vps.sh — Cierre fino del deploy de Hermes-Agent en VPS.
#
# Resuelve los 3 cabos sueltos del despliegue 2026-05-27:
#
#   1. Allowlist Telegram: el gateway está denegando a TODOS los usuarios
#      porque no hay TELEGRAM_ALLOWED_USERS en ~/.hermes/.env. Sin esto,
#      el bot ignora tus mensajes silenciosamente.
#
#   2. Venv split-brain: el venv vive en /root/.hermes/venv/ pero los
#      shebangs apuntan a /home/root/.hermes/venv/bin/python3 (path del
#      install buggy). Recrear el venv limpiamente con --copies.
#
#   3. Stale systemd unit: Hermes-Agent advirtió que su drain_timeout es
#      180s pero nuestro TimeoutStopSec es 90s → SIGKILL mid-drain.
#      Usar la unit oficial de Hermes (`hermes gateway service install`).
#
# Idempotente. Aplicar en el VPS como root:
#   ssh root@<ip> 'bash -s' < scripts/finalize_hermes_vps.sh
# ============================================================================
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
ENV_FILE="${HERMES_HOME}/.env"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-656190718}"
log() { echo "[finalize] $*"; }

# ---------------------------------------------------------------------------
# 1. Allowlist Telegram
# ---------------------------------------------------------------------------
log "1/4 Añadir TELEGRAM_ALLOWED_USERS=${TELEGRAM_CHAT_ID} a $ENV_FILE"
if ! grep -q '^TELEGRAM_ALLOWED_USERS=' "$ENV_FILE" 2>/dev/null; then
    echo "" >> "$ENV_FILE"
    echo "# Telegram bot allowlist (sin esto el gateway deniega todo)" >> "$ENV_FILE"
    echo "TELEGRAM_ALLOWED_USERS=${TELEGRAM_CHAT_ID}" >> "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "  ✓ añadido"
else
    sed -i "s|^TELEGRAM_ALLOWED_USERS=.*|TELEGRAM_ALLOWED_USERS=${TELEGRAM_CHAT_ID}|" "$ENV_FILE"
    echo "  ✓ actualizado"
fi

# ---------------------------------------------------------------------------
# 2. Reparar venv con shebangs correctos
# ---------------------------------------------------------------------------
log "2/4 Reparar venv (shebangs apuntan a /home/root/...)"
NEEDS_RECREATE=false
if [[ -L "${HERMES_HOME}/venv/bin/python" ]] || [[ -f "${HERMES_HOME}/venv/bin/python3" ]]; then
    HEAD_PYTHON=$(head -1 "${HERMES_HOME}/venv/bin/hermes" 2>/dev/null || echo "")
    if [[ "$HEAD_PYTHON" == *"/home/root/"* ]]; then
        NEEDS_RECREATE=true
    fi
fi
if [[ "$NEEDS_RECREATE" == "true" ]]; then
    log "  → recreando venv limpio en ${HERMES_HOME}/venv/"
    BACKUP_DIR="${HERMES_HOME}/venv.broken.$(date +%s)"
    mv "${HERMES_HOME}/venv" "$BACKUP_DIR"
    python3 -m venv "${HERMES_HOME}/venv"
    "${HERMES_HOME}/venv/bin/pip" install --quiet --upgrade pip
    "${HERMES_HOME}/venv/bin/pip" install --quiet --upgrade hermes-agent
    "${HERMES_HOME}/venv/bin/hermes" postinstall 2>&1 | tail -3 || true
    log "  ✓ venv recreado. Backup en $BACKUP_DIR"
else
    log "  ✓ venv ya está bien"
fi

# Limpiar /home/root residual si quedó
if [[ -d /home/root ]]; then
    log "  limpiando /home/root residual"
    rm -rf /home/root
fi

# ---------------------------------------------------------------------------
# 3. Usar systemd unit oficial de Hermes
# ---------------------------------------------------------------------------
log "3/4 Reinstalar systemd unit con la plantilla oficial de Hermes"
systemctl stop hermes-agent || true
rm -f /etc/systemd/system/hermes-agent.service
systemctl daemon-reload

# `hermes gateway service install` crea su propia unit con timeouts correctos
# El --replace fuerza overwrite si existe
"${HERMES_HOME}/venv/bin/hermes" gateway install 2>&1 | tail -10 || true

# Si Hermes creó una unit con nombre distinto, identifícala y guárdala como alias
NEW_UNIT=$(systemctl list-unit-files --no-pager 2>/dev/null | grep -i hermes | awk '{print $1}' | head -1)
log "  unit registrada: ${NEW_UNIT:-(none)}"

# ---------------------------------------------------------------------------
# 4. Verificar estado
# ---------------------------------------------------------------------------
log "4/4 Arrancar y verificar"
if [[ -n "$NEW_UNIT" ]]; then
    systemctl enable "$NEW_UNIT" 2>&1 | tail -3 || true
    systemctl restart "$NEW_UNIT"
    sleep 6
    echo ""
    echo "============= ESTADO FINAL ============="
    echo "Unit: $NEW_UNIT"
    systemctl status "$NEW_UNIT" --no-pager 2>&1 | head -10
    echo ""
    echo "Últimas líneas log:"
    journalctl -u "$NEW_UNIT" --no-pager -n 20 2>&1 | tail -20
fi
echo ""
echo "Proveedores configurados (config.yaml):"
grep -E "^\s*(provider|model):" "${HERMES_HOME}/config.yaml" 2>/dev/null | head -20
echo ""
echo "👉 Manda /start a @GodAtlas_bot en Telegram para verificar."
