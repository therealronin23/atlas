#!/usr/bin/env bash
# ============================================================================
# fix_hermes_paths_vps.sh — Corrige el deploy del 2026-05-27:
#   bug A: install_hermes_agent_vps.sh asumió HERMES_HOME=/home/$USER/.hermes
#          pero cuando se ejecuta como root, /home/root/ no existe. Hermes-Agent
#          puso sus datos en /root/.hermes (correcto) pero el systemd unit y
#          el .env quedaron en /home/root/.hermes (inalcanzables) → daemon en
#          loop "activating".
#   bug B: `ollama pull qwen2.5:1.5b` corrió antes de que el daemon estuviera
#          listo en la primera invocación, así que el modelo no se descargó.
#
# Idempotente. Ejecutar en el VPS como root:
#   ssh root@178.105.216.187 'bash -s' < scripts/fix_hermes_paths_vps.sh
# ============================================================================
set -euo pipefail

REAL_HOME=/root/.hermes
WRONG_HOME=/home/root/.hermes

echo "[fix] 1/5  Consolidar archivos en $REAL_HOME"
mkdir -p "$REAL_HOME"/{logs,memories}
if [[ -d "$WRONG_HOME" ]]; then
    cp -an "$WRONG_HOME/." "$REAL_HOME/" 2>/dev/null || true
fi
ls "$REAL_HOME" | head -8

echo "[fix] 2/5  Reescribir systemd unit con paths correctos"
cat > /etc/systemd/system/hermes-agent.service <<UNIT
[Unit]
Description=Hermes-Agent (Nous Research) — Telegram executor + Atlas twin
After=network-online.target ollama.service
Wants=ollama.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/.hermes
EnvironmentFile=/root/.hermes/.env
ExecStart=/root/.hermes/venv/bin/hermes run --config /root/.hermes/config.yaml
Restart=always
RestartSec=10
StandardOutput=append:/root/.hermes/logs/hermes.log
StandardError=append:/root/.hermes/logs/hermes.err

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload

echo "[fix] 3/5  Descargar modelo Ollama qwen2.5:1.5b"
sleep 1
ollama pull qwen2.5:1.5b 2>&1 | tail -3

echo "[fix] 4/5  Reiniciar hermes-agent"
systemctl restart hermes-agent
sleep 6
STATE=$(systemctl is-active hermes-agent || true)
echo "  estado: $STATE"

echo "[fix] 5/5  Limpiar /home/root vacío"
[[ -d /home/root ]] && rmdir -p /home/root 2>/dev/null || true

echo ""
echo "============= ESTADO FINAL ============="
echo "hermes-agent: $(systemctl is-active hermes-agent)"
echo "ollama:       $(systemctl is-active ollama)"
echo ""
echo "Modelos Ollama:"
ollama list 2>&1 | head -5
echo ""
echo "Últimas líneas de log de Hermes-Agent:"
tail -15 /root/.hermes/logs/hermes.log 2>/dev/null || echo "  (sin log aún)"
echo ""
echo "stderr (si hay):"
tail -10 /root/.hermes/logs/hermes.err 2>/dev/null || true
