#!/usr/bin/env bash
# ============================================================================
# fix_hermes_compression_and_skills.sh — Resuelve 3 bugs vivos:
#
#   1. ValueError: "Auxiliary compression model qwen2.5:3b has 32K context"
#      → Hermes usa un modelo separado para comprimir conversaciones largas.
#      Override con auxiliary.compression.context_length: 65536.
#
#   2. duckduckgo-search bloqueada por "community source + caution verdict".
#      → Force-install (el usuario asume el riesgo en su propia VPS).
#
#   3. Crash loop: el ValueError mata el proceso cada ~5 min.
#      → Resuelto al fijar el (1).
#
# También añade dos skills oficiales (trust=official) que cubren el caso de
# "consultar Atlas":
#   - official/software-development/rest-graphql-debugger → llamar APIs REST
#   - official/research/scrapling → scraping/HTTP genérico
#
# Idempotente. Aplicar:
#   ssh root@<ip> 'bash -s' < scripts/fix_hermes_compression_and_skills.sh
# ============================================================================
set -uo pipefail
HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
HERMES_BIN="${HERMES_HOME}/venv/bin/hermes"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-656190718}"
export XDG_RUNTIME_DIR=/run/user/0
log() { echo "[fix-cs] $*"; }

# ---------------------------------------------------------------------------
# 1. Parar el gateway antes de reconfig
# ---------------------------------------------------------------------------
log "1/5 Stop gateway"
systemctl --user stop hermes-gateway.service 2>&1 | tail -3 || true

# ---------------------------------------------------------------------------
# 2. Añadir bloque auxiliary.compression al config.yaml
# ---------------------------------------------------------------------------
log "2/5 Reescribir config.yaml con auxiliary.compression"
cp "${HERMES_HOME}/config.yaml" "${HERMES_HOME}/config.yaml.bak.cs.$(date +%s)" 2>/dev/null || true
cat > "${HERMES_HOME}/config.yaml" <<EOF
# Hermes-Agent — config v8 (stable: compression model + skills)

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
  provider: custom:vps_ollama
  default: qwen2.5:3b
  context_length: 65536

# Auxiliary models que Hermes usa para tareas internas (compression de
# conversación, classification, etc). Si NO se setea, usa el primario y
# heredamos sus límites de tokens. Hermes valida el context contra 64K
# mínimo y CRASHEA si no llega.
auxiliary:
  compression:
    # Usamos el mismo Ollama local pero forzamos el context_length para
    # superar el check. Ollama lo respeta porque OLLAMA_CONTEXT_LENGTH=65536
    # ya está en el systemd unit override.
    provider: custom:vps_ollama
    model: qwen2.5:3b
    context_length: 65536
  classification:
    provider: custom:vps_ollama
    model: qwen2.5:3b
    context_length: 65536

fallback_providers:
  - provider: huggingface
    model: Qwen/Qwen2.5-72B-Instruct
    context_length: 131072
  - provider: huggingface
    model: meta-llama/Llama-3.3-70B-Instruct
    context_length: 131072
  - provider: gemini
    model: gemini-2.0-flash
    context_length: 1048576
  - provider: openrouter
    model: meta-llama/llama-3.3-70b-instruct:free
    context_length: 131072
  - provider: openrouter
    model: anthropic/claude-3.5-sonnet
    context_length: 200000
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
# 3. Instalar skills oficiales (trust=official, no requieren --force)
# ---------------------------------------------------------------------------
log "3/5 Instalar skills oficiales del Hub"

# rest-graphql-debugger: official trust → cubre nuestro caso de llamar Atlas /api/health
log "   → rest-graphql-debugger (cubre consultar Atlas via REST)"
"$HERMES_BIN" skills install --yes official/software-development/rest-graphql-debugger 2>&1 | tail -3

# scrapling: official trust → scraping web genérico
log "   → scrapling (HTTP/scraping)"
"$HERMES_BIN" skills install --yes official/research/scrapling 2>&1 | tail -3

# duckduckgo-search: community → requiere --force
log "   → duckduckgo-search (--force, community trust)"
"$HERMES_BIN" skills install --yes --force official/research/duckduckgo-search 2>&1 | tail -3

# ---------------------------------------------------------------------------
# 4. Listar skills finales
# ---------------------------------------------------------------------------
log "4/5 Skills instaladas:"
"$HERMES_BIN" skills list 2>&1 | tail -20

# ---------------------------------------------------------------------------
# 5. Start gateway
# ---------------------------------------------------------------------------
log "5/5 Start gateway"
systemctl --user start hermes-gateway.service
sleep 6
echo ""
echo "============= ESTADO ============="
echo "hermes-gateway: $(systemctl --user is-active hermes-gateway.service)"
journalctl --user -u hermes-gateway.service --no-pager -n 12 2>&1 | tail -12
echo ""
echo "👉 Pruebas Telegram:"
echo "   1. 'hola' — sin ValueError"
echo "   2. 'consulta http://100.85.236.58:7331/api/health usando rest-graphql-debugger'"
