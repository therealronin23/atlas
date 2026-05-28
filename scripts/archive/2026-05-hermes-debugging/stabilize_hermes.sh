#!/usr/bin/env bash
# ============================================================================
# stabilize_hermes.sh — Para el crash loop + instala skills reales del Hub.
#
# Problemas vivos:
#   1. Crash loop: el modelo intenta web_search pero NO hay tools instaladas →
#      Hermes da "Unknown tool, sending error to model" 3 veces y crashea.
#   2. Gemini 404: `gemini-2.0-flash-exp` no es un nombre de modelo válido en
#      el endpoint v1beta. Cambiamos a `gemini-2.0-flash` (estable).
#   3. SKILL system mal entendido: la forma correcta es `hermes skills
#      install <identifier>` desde el Skills Hub remoto, no Python local.
#
# Fix:
#   - Vuelve a Ollama primary (qwen2.5:3b, modelos pequeños no abusan tools)
#   - Quita gemini-2.0-flash-exp del fallback chain
#   - Instala 2 skills oficiales del Hub para que Hermes tenga capability real:
#       * duckduckgo-search → web_search funcional
#       * http-request o similar → llamadas HTTP arbitrarias (que cubrirá
#         consultar Atlas hasta que tengamos tap propio)
#
# Idempotente. Aplicar en VPS como root:
#   ssh root@<ip> 'bash -s' < scripts/stabilize_hermes.sh
# ============================================================================
set -uo pipefail
HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
HERMES_BIN="${HERMES_HOME}/venv/bin/hermes"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-656190718}"
export XDG_RUNTIME_DIR=/run/user/0
log() { echo "[stab] $*"; }

# ---------------------------------------------------------------------------
# 1. Detener el servicio para no inundar logs durante la reconfig
# ---------------------------------------------------------------------------
log "1/5 Stop hermes-gateway (corta el crash loop)"
systemctl --user stop hermes-gateway.service 2>&1 | tail -3 || true

# ---------------------------------------------------------------------------
# 2. Reescribir config.yaml: Ollama primary, sin Gemini roto
# ---------------------------------------------------------------------------
log "2/5 Reescribir config.yaml estable"
cp "${HERMES_HOME}/config.yaml" "${HERMES_HOME}/config.yaml.bak.stab.$(date +%s)" 2>/dev/null || true
cat > "${HERMES_HOME}/config.yaml" <<EOF
# Hermes-Agent — config v7 (estable, sin crash loop)

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

# Ollama primary: qwen2.5:3b es lo más grande que cabe en CPX22 con KV-q4.
# Los modelos pequeños son menos propensos a alucinar tools inexistentes.
model:
  provider: custom:vps_ollama
  default: qwen2.5:3b
  context_length: 65536

# Fallbacks ordenados por estabilidad observada hoy
fallback_providers:
  - provider: huggingface
    model: Qwen/Qwen2.5-72B-Instruct
    context_length: 131072
  - provider: huggingface
    model: meta-llama/Llama-3.3-70B-Instruct
    context_length: 131072
  # gemini-2.0-flash (sin -exp) es el modelo estable
  - provider: gemini
    model: gemini-2.0-flash
    context_length: 1048576
  - provider: openrouter
    model: meta-llama/llama-3.3-70b-instruct:free
    context_length: 131072
  - provider: openrouter
    model: anthropic/claude-3.5-sonnet
    context_length: 200000
  - provider: custom:groq
    model: llama-3.3-70b-versatile
    context_length: 131072
  - provider: custom:vps_ollama
    model: qwen2.5:1.5b
    context_length: 64000

openrouter:
  provider_routing:
    sort: price
    data_collection: deny

messaging:
  telegram:
    enabled: true
    allowed_chat_ids:
      - ${TELEGRAM_CHAT_ID}
    home_channel: ${TELEGRAM_CHAT_ID}

memory:
  enabled: true
  store_path: ${HERMES_HOME}/memories

logging:
  level: info
  path: ${HERMES_HOME}/logs

approvals:
  destructive_slash_confirm: false
EOF

# ---------------------------------------------------------------------------
# 3. Instalar skills oficiales del Hub (las que cubren llamar a Atlas)
# ---------------------------------------------------------------------------
log "3/5 Instalar skills oficiales del Hub"

# DuckDuckGo: web_search funcional
log "   → duckduckgo-search"
"$HERMES_BIN" skills install --yes official/research/duckduckgo-search 2>&1 | tail -5 || true

# Buscar la skill que cubre HTTP requests arbitrarios (probable: 'curl' o 'http-fetch')
log "   → buscando skills HTTP genéricas"
"$HERMES_BIN" skills search http 2>&1 | head -20
"$HERMES_BIN" skills search curl 2>&1 | head -10
"$HERMES_BIN" skills search rest 2>&1 | head -10

# ---------------------------------------------------------------------------
# 4. Listar lo que quedó instalado
# ---------------------------------------------------------------------------
log "4/5 Skills instaladas ahora:"
"$HERMES_BIN" skills list 2>&1 | tail -15

# ---------------------------------------------------------------------------
# 5. Arrancar
# ---------------------------------------------------------------------------
log "5/5 Start hermes-gateway"
systemctl --user start hermes-gateway.service
sleep 6
echo ""
echo "============= ESTADO ============="
echo "hermes-gateway: $(systemctl --user is-active hermes-gateway.service)"
echo ""
echo "Últimos logs:"
journalctl --user -u hermes-gateway.service --no-pager -n 15 2>&1 | tail -15
echo ""
echo "👉 Pruebas en Telegram:"
echo "   1. 'hola' — debe responder sin cascada"
echo "   2. 'busca en duckduckgo qué es Tailscale' — prueba duckduckgo-search"
echo "   3. 'consulta http://100.85.236.58:7331/api/health' — si tenemos http skill"
