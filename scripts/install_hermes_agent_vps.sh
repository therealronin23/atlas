#!/usr/bin/env bash
# ============================================================================
# install_hermes_agent_vps.sh — Provision Hermes-Agent (Nous Research) + Ollama
# en el VPS, reemplazando al stub original.
#
# Arquitectura twin (ADR-026):
#   - VPS (este host): Hermes-Agent autónomo que maneja Telegram + Ollama local
#   - Laptop (Atlas Core): orquestador de pipeline + memoria + auditoría
#
# Idempotente: re-ejecutar es seguro, no destruye configuración existente.
#
# Uso:
#   scp scripts/install_hermes_agent_vps.sh ronin@<vps-tailscale-ip>:~/
#   ssh ronin@<vps-tailscale-ip> "TELEGRAM_BOT_TOKEN=... OPENROUTER_API_KEY=... \
#       NVIDIA_API_KEY=... GROQ_API_KEY=... GEMINI_API_KEY=... HF_TOKEN=... \
#       bash ~/install_hermes_agent_vps.sh"
# ============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Vars
# ---------------------------------------------------------------------------
HERMES_USER="${HERMES_USER:-$USER}"
HERMES_HOME="${HERMES_HOME:-/home/${HERMES_USER}/.hermes}"
HERMES_PYBIN="${HERMES_PYBIN:-python3}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:1.5b}"   # ~1GB RAM, decente en CPU
LOG_PREFIX="[hermes-install]"

log() { echo "${LOG_PREFIX} $*"; }

# Secretos pasados por env (no se hardcodean)
: "${TELEGRAM_BOT_TOKEN:?Falta TELEGRAM_BOT_TOKEN}"
: "${OPENROUTER_API_KEY:?Falta OPENROUTER_API_KEY}"
NVIDIA_API_KEY="${NVIDIA_API_KEY:-}"
GROQ_API_KEY="${GROQ_API_KEY:-}"
GEMINI_API_KEY="${GEMINI_API_KEY:-}"
HF_TOKEN="${HF_TOKEN:-}"
ATLAS_DASHBOARD_URL="${ATLAS_DASHBOARD_URL:-http://100.85.236.58:7331}"

# ---------------------------------------------------------------------------
# 1) Dependencias del sistema
# ---------------------------------------------------------------------------
log "Actualizando apt + dependencias base"
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv \
    curl wget jq \
    git \
    > /dev/null

# ---------------------------------------------------------------------------
# 2) Ollama (inferencia local en CPU del VPS — aprovecha la RAM pagada)
# ---------------------------------------------------------------------------
if ! command -v ollama >/dev/null 2>&1; then
    log "Instalando Ollama (CPU only)"
    curl -fsSL https://ollama.com/install.sh | sh
else
    log "Ollama ya instalado: $(ollama --version 2>/dev/null | head -1)"
fi

# Asegurar daemon corriendo
if ! systemctl is-active --quiet ollama 2>/dev/null; then
    sudo systemctl enable ollama || true
    sudo systemctl start ollama || true
fi

log "Descargando modelo Ollama: ${OLLAMA_MODEL}"
ollama pull "${OLLAMA_MODEL}" || log "WARN: fallo al descargar ${OLLAMA_MODEL}, sigue"

# ---------------------------------------------------------------------------
# 3) Hermes-Agent (Nous Research)
# ---------------------------------------------------------------------------
log "Instalando Hermes-Agent vía pip"
mkdir -p "${HERMES_HOME}"

# Venv aislado para no contaminar el sistema
if [[ ! -d "${HERMES_HOME}/venv" ]]; then
    ${HERMES_PYBIN} -m venv "${HERMES_HOME}/venv"
fi
source "${HERMES_HOME}/venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet --upgrade hermes-agent

# Postinstall (idempotente)
hermes postinstall || true
deactivate

# ---------------------------------------------------------------------------
# 4) Configuración Hermes-Agent
# ---------------------------------------------------------------------------
log "Escribiendo ~/.hermes/.env (secretos)"
cat > "${HERMES_HOME}/.env" <<EOF
# Hermes-Agent — secretos
# OJO: contiene tokens. Permisos 600.

# Provider primario: OpenRouter (300+ modelos frontier)
OPENROUTER_API_KEY=${OPENROUTER_API_KEY}

# Providers fallback
${NVIDIA_API_KEY:+NVIDIA_API_KEY=${NVIDIA_API_KEY}}
${GROQ_API_KEY:+GROQ_API_KEY=${GROQ_API_KEY}}
${GEMINI_API_KEY:+GEMINI_API_KEY=${GEMINI_API_KEY}}
${HF_TOKEN:+HF_TOKEN=${HF_TOKEN}}

# Telegram bot
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}

# Ollama local (CPU del VPS) — dummy key required by OpenAI-compatible adapter
OPENAI_API_KEY=ollama-dummy-key

# Atlas Core (laptop) reachable via Tailscale para handshake gemelo
ATLAS_DASHBOARD_URL=${ATLAS_DASHBOARD_URL}
EOF
chmod 600 "${HERMES_HOME}/.env"

log "Escribiendo ~/.hermes/config.yaml"
cat > "${HERMES_HOME}/config.yaml" <<EOF
# Hermes-Agent — config primario (ADR-026 twin con Atlas Core)

# Identidad del agente
identity:
  name: Hermes
  role: "Telegram executor + Atlas twin in VPS"
  twin: atlas-core

# Modelo principal: OpenRouter para tareas que necesitan contexto largo
model:
  provider: openrouter
  default: anthropic/claude-3.5-sonnet
  context_window: 200000

# Fallback chain (en caso de quota/error en primario)
fallback_models:
  - provider: openrouter
    model: nvidia/llama-3.1-nemotron-70b-instruct:free
  - provider: openrouter
    model: meta-llama/llama-3.3-70b-instruct:free
  - provider: custom
    base_url: http://localhost:11434/v1
    model: ${OLLAMA_MODEL}

# Telegram gateway
messaging:
  telegram:
    enabled: true
    # Token vive en ~/.hermes/.env
    allowed_chat_ids:
      - 656190718

# Memoria persistente (parte del valor de Hermes-Agent vs un bot simple)
memory:
  enabled: true
  store_path: ${HERMES_HOME}/memories

# Tool gateway — incluye un cliente Atlas Core para handshake gemelo
tools:
  atlas_twin:
    enabled: true
    base_url: ${ATLAS_DASHBOARD_URL}
    timeout_s: 10
    purpose: |
      Twin pairing with Atlas Core (the local orchestrator on the user's
      laptop). Use Atlas for audit log queries, governance checks, and
      tasks that require local capability tokens.

# Logs y observabilidad
logging:
  level: info
  path: ${HERMES_HOME}/logs
EOF

# ---------------------------------------------------------------------------
# 5) Systemd unit (auto-restart, supervivencia al reboot)
# ---------------------------------------------------------------------------
log "Creando systemd unit hermes-agent.service"
sudo tee /etc/systemd/system/hermes-agent.service > /dev/null <<EOF
[Unit]
Description=Hermes-Agent (Nous Research) — Telegram executor + Atlas twin
After=network-online.target ollama.service
Wants=ollama.service

[Service]
Type=simple
User=${HERMES_USER}
WorkingDirectory=${HERMES_HOME}
EnvironmentFile=${HERMES_HOME}/.env
ExecStart=${HERMES_HOME}/venv/bin/hermes run --config ${HERMES_HOME}/config.yaml
Restart=always
RestartSec=10
StandardOutput=append:${HERMES_HOME}/logs/hermes.log
StandardError=append:${HERMES_HOME}/logs/hermes.err

[Install]
WantedBy=multi-user.target
EOF

mkdir -p "${HERMES_HOME}/logs" "${HERMES_HOME}/memories"
sudo systemctl daemon-reload
sudo systemctl enable hermes-agent.service
sudo systemctl restart hermes-agent.service

# ---------------------------------------------------------------------------
# 6) Generar HERMES_API_KEY para el handshake con Atlas (HMAC)
# ---------------------------------------------------------------------------
HERMES_API_KEY_FILE="${HERMES_HOME}/atlas_handshake.key"
if [[ ! -f "${HERMES_API_KEY_FILE}" ]]; then
    log "Generando HERMES_API_KEY (HMAC compartido con Atlas)"
    openssl rand -hex 32 > "${HERMES_API_KEY_FILE}"
    chmod 600 "${HERMES_API_KEY_FILE}"
fi
HERMES_API_KEY=$(cat "${HERMES_API_KEY_FILE}")

# ---------------------------------------------------------------------------
# 7) Estado final
# ---------------------------------------------------------------------------
log "================ INSTALACIÓN COMPLETA ================"
log "Hermes-Agent: $(systemctl is-active hermes-agent.service)"
log "Ollama:       $(systemctl is-active ollama 2>/dev/null || echo unknown)"
log "Modelo local: ${OLLAMA_MODEL}"
log "Config:       ${HERMES_HOME}/config.yaml"
log "Secretos:     ${HERMES_HOME}/.env (perms 600)"
log "Logs:         ${HERMES_HOME}/logs/hermes.log"
log ""
log "PEGA ESTO EN TU .env LOCAL (~/proyectos/atlas-core/.env):"
echo ""
echo "HERMES_API_KEY=${HERMES_API_KEY}"
echo ""
log "Y verifica con:"
log "  curl -s http://100.108.132.116:7331/api/health   # si Hermes expone HTTP"
log "  systemctl status hermes-agent                    # estado del daemon"
log "  tail -20 ${HERMES_HOME}/logs/hermes.log"
