#!/usr/bin/env bash
# ============================================================================
# fix_hermes_context_length.sh — Sube el context_length de los providers
# a 128K para cumplir el mínimo de Hermes (64K para agentic).
#
# Error reportado en Telegram:
#   ValueError: Model llama-3.3-70b-versatile has a context window of
#   32,768 tokens, which is below the minimum 64,000 required by Hermes Agent.
#
# La causa fue mi config.yaml: puse `context_length: 32768` (mi error).
# Groq llama-3.3-70b-versatile soporta 131072. Subimos.
#
# También configuramos el chat actual como home channel para Telegram
# (evita el aviso "No home channel is set" en cada turno).
#
# Idempotente. Aplicar en VPS como root:
#   ssh root@<ip> 'bash -s' < scripts/fix_hermes_context_length.sh
# ============================================================================
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-656190718}"
log() { echo "[fix-ctx] $*"; }

log "1/3 Backup config.yaml actual"
cp "${HERMES_HOME}/config.yaml" "${HERMES_HOME}/config.yaml.bak.ctx.$(date +%s)"

log "2/3 Reescribir config.yaml con context_length: 131072"
cat > "${HERMES_HOME}/config.yaml" <<EOF
# Hermes-Agent — config v3 (multi-provider + 128K context, ADR-026 twin)

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

model:
  provider: custom:groq
  default: llama-3.3-70b-versatile
  context_length: 131072   # Groq llama-3.3-70b real max; fixes "below 64K" error

# Fallbacks: si el primario falla, Hermes salta al siguiente conservando contexto
fallback_providers:
  - provider: custom:groq
    model: llama-3.1-8b-instant
    context_length: 131072
  - provider: openrouter
    model: nvidia/llama-3.1-nemotron-70b-instruct:free
    context_length: 131072
  - provider: openrouter
    model: meta-llama/llama-3.3-70b-instruct:free
    context_length: 131072
  - provider: openrouter
    model: anthropic/claude-3.5-sonnet
    context_length: 200000
  - provider: gemini
    model: gemini-2.0-flash-exp
    context_length: 1048576
  - provider: huggingface
    model: Qwen/Qwen2.5-72B-Instruct
    context_length: 131072
  - provider: nvidia
    model: nvidia/nemotron-3-super-120b-a12b
    context_length: 131072
  # Último recurso: Ollama local. qwen2.5:1.5b por defecto soporta 32K,
  # pero exportamos OLLAMA_CONTEXT_LENGTH=64000 en el .env del servicio para
  # forzar el mínimo de Hermes.
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
    # Home channel: donde Hermes manda outputs de cron + cross-platform
    home_channel: ${TELEGRAM_CHAT_ID}

memory:
  enabled: true
  store_path: ${HERMES_HOME}/memories

tools:
  atlas_twin:
    enabled: true
    base_url: http://100.85.236.58:7331
    timeout_s: 10
    purpose: |
      Twin pairing with Atlas Core (laptop). Use it for audit log queries,
      governance checks, and tasks needing local capability tokens.

logging:
  level: info
  path: ${HERMES_HOME}/logs

# Ya aprobamos /reset etc. en sesión anterior; mantenemos sin reconfirmación
approvals:
  destructive_slash_confirm: false
EOF

# Asegurar OLLAMA_CONTEXT_LENGTH para el modelo local
if ! grep -q '^OLLAMA_CONTEXT_LENGTH=' "${HERMES_HOME}/.env"; then
    echo "OLLAMA_CONTEXT_LENGTH=64000" >> "${HERMES_HOME}/.env"
fi

log "3/3 Reiniciar hermes-gateway (user-level)"
export XDG_RUNTIME_DIR="/run/user/$(id -u root)"
systemctl --user restart hermes-gateway.service
sleep 6

echo ""
echo "============= ESTADO ============="
systemctl --user status hermes-gateway.service --no-pager 2>&1 | head -10
echo ""
echo "Últimos 20 logs:"
journalctl --user -u hermes-gateway.service --no-pager -n 20 2>&1 | tail -20
echo ""
echo "👉 Manda 'hola' al bot. Debe contestar con texto del LLM, no error."
