#!/usr/bin/env bash
# ============================================================================
# fix_hermes_413_payload.sh — Resuelve el 413 "Request payload too large".
#
# Síntoma: aunque pongamos context_length: 131072, Groq devuelve HTTP 413
# porque su límite de TOKENS POR REQUEST en free tier es mucho menor que el
# context window del modelo (~8-12K input típico). Hermes carga tools+skills
# + system prompt grande → supera el cap inmediato.
#
# Fix: invertir la chain. OpenRouter primario (acepta payloads grandes con
# llama-3.3-70b-instruct:free) y Groq queda como fallback rápido para
# mensajes cortos.
#
# Idempotente. Aplicar en VPS como root:
#   ssh root@<ip> 'bash -s' < scripts/fix_hermes_413_payload.sh
# ============================================================================
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-656190718}"
log() { echo "[fix-413] $*"; }

log "1/3 Backup config.yaml"
cp "${HERMES_HOME}/config.yaml" "${HERMES_HOME}/config.yaml.bak.413.$(date +%s)"

log "2/3 Reescribir con OpenRouter primario (payload-friendly)"
cat > "${HERMES_HOME}/config.yaml" <<EOF
# Hermes-Agent — config v4 (OpenRouter primary, ADR-026 twin)
#
# Cambio de v3: Groq baja a fallback porque su free-tier limita el payload
# por request (~8-12K) aunque el context del modelo sea 128K. OpenRouter es
# más laxo con free models y soporta los payloads grandes de Hermes.

identity:
  name: Hermes
  role: "Telegram executor + Atlas twin in VPS"
  twin: atlas-core

custom_providers:
  - name: groq
    base_url: https://api.groq.com/openai/v1
    key_env: GROQ_API_KEY
  - name: vps_ollama
    base_url: http://127.0.0.1:11434/v1
    key_env: OPENAI_API_KEY

# Primary: OpenRouter free llama-3.3-70b. Más tolerante con payload grande.
model:
  provider: openrouter
  default: meta-llama/llama-3.3-70b-instruct:free
  context_length: 131072

# Fallback chain ordenada por tolerancia de payload + velocidad
fallback_providers:
  # 1. Otros free de OpenRouter (mismo provider, distintos modelos)
  - provider: openrouter
    model: nvidia/llama-3.1-nemotron-70b-instruct:free
    context_length: 131072
  - provider: openrouter
    model: google/gemini-2.0-flash-exp:free
    context_length: 1048576
  # 2. OpenRouter pago (Claude — payload grande, calidad alta)
  - provider: openrouter
    model: anthropic/claude-3.5-sonnet
    context_length: 200000
  # 3. Gemini directo (free tier muy generoso, payload grande)
  - provider: gemini
    model: gemini-2.0-flash-exp
    context_length: 1048576
  # 4. HuggingFace (autoroutea, payload tolerante)
  - provider: huggingface
    model: Qwen/Qwen2.5-72B-Instruct
    context_length: 131072
  # 5. NVIDIA NIM
  - provider: nvidia
    model: nvidia/nemotron-3-super-120b-a12b
    context_length: 131072
  # 6. Groq llama-3.3-70b (ultra-rápido para payloads pequeños)
  - provider: custom:groq
    model: llama-3.3-70b-versatile
    context_length: 131072
  - provider: custom:groq
    model: llama-3.1-8b-instant
    context_length: 131072
  # 7. Last resort: Ollama local en VPS
  - provider: custom:vps_ollama
    model: qwen2.5:1.5b
    context_length: 64000

openrouter:
  provider_routing:
    sort: price
    data_collection: deny
    require_parameters: true

messaging:
  telegram:
    enabled: true
    allowed_chat_ids:
      - ${TELEGRAM_CHAT_ID}
    home_channel: ${TELEGRAM_CHAT_ID}

memory:
  enabled: true
  store_path: ${HERMES_HOME}/memories

tools:
  atlas_twin:
    enabled: true
    base_url: http://100.85.236.58:7331
    timeout_s: 10

logging:
  level: info
  path: ${HERMES_HOME}/logs

approvals:
  destructive_slash_confirm: false
EOF

log "3/3 Reiniciar hermes-gateway"
export XDG_RUNTIME_DIR="/run/user/$(id -u root)"
systemctl --user restart hermes-gateway.service
sleep 6

echo ""
echo "============= ESTADO ============="
systemctl --user is-active hermes-gateway.service
journalctl --user -u hermes-gateway.service --no-pager -n 15 2>&1 | tail -15
echo ""
echo "Primary model ahora:"
grep -A2 '^model:' "${HERMES_HOME}/config.yaml" | head -4
echo ""
echo "👉 Manda 'hola' al bot. Si vuelve 413, el problema NO es el tier sino"
echo "   que Hermes carga demasiados tools/skills. En ese caso ajustamos:"
echo "   sed -i 's/atlas_twin/_atlas_twin_disabled/' ~/.hermes/config.yaml"
echo "   para desactivar tools y bajar el payload."
