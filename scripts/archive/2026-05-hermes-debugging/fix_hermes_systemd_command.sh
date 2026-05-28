#!/usr/bin/env bash
# ============================================================================
# fix_hermes_systemd_command.sh — Corrige el ExecStart del systemd unit.
#
# El install y reconfigure scripts pusieron `hermes run` pero ese subcomando
# no existe. El daemon correcto es `hermes gateway run` (foreground, ideal
# para systemd).
#
# Idempotente. Aplica en el VPS como root:
#   ssh root@<ip> 'bash -s' < scripts/fix_hermes_systemd_command.sh
# ============================================================================
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
UNIT_FILE=/etc/systemd/system/hermes-agent.service

echo "[fix-cmd] 1/4 Validar binario y subcomando"
"${HERMES_HOME}/venv/bin/hermes" gateway --help >/dev/null 2>&1 \
    || { echo "ERROR: hermes gateway no disponible en venv"; exit 1; }
echo "  ✓ hermes gateway funciona"

echo "[fix-cmd] 2/4 Setup interactivo del gateway Telegram (asegura registro)"
# Run hermes gateway setup with stdin redirected (idempotent if already set up)
# This may print warnings but shouldn't fail; we ignore exit code.
HERMES_ACCEPT_HOOKS=1 "${HERMES_HOME}/venv/bin/hermes" gateway list 2>&1 | head -10 || true

echo "[fix-cmd] 3/4 Reescribir systemd unit con 'hermes gateway run'"
cat > "$UNIT_FILE" <<UNIT
[Unit]
Description=Hermes-Agent (Nous Research) — Telegram gateway + Atlas twin
After=network-online.target ollama.service
Wants=ollama.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/.hermes
EnvironmentFile=/root/.hermes/.env
# `hermes gateway run` runs all configured messaging gateways in foreground.
# Telegram polling lives here. Polling needs a long-running process.
ExecStart=/root/.hermes/venv/bin/hermes gateway run --accept-hooks
Restart=always
RestartSec=10
StandardOutput=append:/root/.hermes/logs/hermes.log
StandardError=append:/root/.hermes/logs/hermes.err

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload

echo "[fix-cmd] 4/4 Restart hermes-agent y verificar"
systemctl restart hermes-agent
sleep 6
STATE=$(systemctl is-active hermes-agent || true)
echo "  estado: $STATE"

echo ""
echo "============= ESTADO ============="
systemctl status hermes-agent --no-pager 2>&1 | head -12
echo ""
echo "Últimas líneas hermes.log:"
tail -20 /root/.hermes/logs/hermes.log 2>/dev/null || echo "  (sin log aún)"
echo ""
echo "stderr (si hay):"
tail -10 /root/.hermes/logs/hermes.err 2>/dev/null || true
