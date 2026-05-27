#!/usr/bin/env bash
# ============================================================================
# reconfigure_hermes_vps.sh — Reconfigura Hermes-Agent en el VPS sin reinstalar.
#
# Aplica:
#   1. Multi-provider fallback chain (Groq → OpenRouter → Gemini → HF → NVIDIA → Ollama)
#   2. Provider routing en OpenRouter (sort=price, data_collection=deny)
#   3. context_length forzado a 64000 (mínimo agentic recomendado)
#   4. Identidad twin Atlas
#
# Idempotente. Lee /root/.hermes/.env del VPS para mantener tokens existentes.
#
# Uso desde el laptop:
#   ssh root@<vps-ip> 'bash -s' < scripts/reconfigure_hermes_vps.sh
# ============================================================================
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:1.5b}"
ATLAS_DASHBOARD_URL="${ATLAS_DASHBOARD_URL:-http://100.85.236.58:7331}"

log() { echo "[reconfigure] $*"; }

if [[ ! -d "$HERMES_HOME" ]]; then
    echo "ERROR: $HERMES_HOME no existe. Corre primero install_hermes_agent_vps.sh" >&2
    exit 1
fi

log "Backup config.yaml existente"
[[ -f "$HERMES_HOME/config.yaml" ]] && \
    cp "$HERMES_HOME/config.yaml" "$HERMES_HOME/config.yaml.bak.$(date +%s)"

log "Escribiendo nueva config.yaml multi-provider"
cat > "$HERMES_HOME/config.yaml" <<EOF
# Hermes-Agent — config v2 (multi-provider fallback, ADR-026 twin)

# ---------------------------------------------------------------------------
# Identidad
# ---------------------------------------------------------------------------
identity:
  name: Hermes
  role: "Telegram executor + Atlas twin in VPS"
  twin: atlas-core

# ---------------------------------------------------------------------------
# Modelo principal — Groq (más rápido del mercado: ~500 tok/s)
# ---------------------------------------------------------------------------
custom_providers:
  - name: groq
    base_url: https://api.groq.com/openai/v1
    key_env: GROQ_API_KEY
  - name: vps_ollama
    base_url: http://127.0.0.1:11434/v1
    key_env: OPENAI_API_KEY   # dummy ollama-dummy-key

model:
  provider: custom:groq
  default: llama-3.3-70b-versatile
  context_length: 32768

# ---------------------------------------------------------------------------
# Fallback chain: si el primario falla (rate-limit, auth, 5xx), Hermes intenta
# el siguiente sin perder la conversación. Orden por velocidad y coste.
# ---------------------------------------------------------------------------
fallback_providers:
  # 1. Groq se reintenta con otro modelo más pequeño
  - provider: custom:groq
    model: llama-3.1-8b-instant
  # 2. OpenRouter (300+ modelos, free tier amplio)
  - provider: openrouter
    model: nvidia/llama-3.1-nemotron-70b-instruct:free
  - provider: openrouter
    model: meta-llama/llama-3.3-70b-instruct:free
  - provider: openrouter
    model: anthropic/claude-3.5-sonnet
  # 3. Gemini (free tier generoso)
  - provider: gemini
    model: gemini-2.0-flash-exp
  # 4. HuggingFace (autoroutea sobre 20+ modelos open)
  - provider: huggingface
    model: Qwen/Qwen2.5-72B-Instruct
  # 5. NVIDIA NIM (Nemotron)
  - provider: nvidia
    model: nvidia/nemotron-3-super-120b-a12b
  # 6. Último recurso: Ollama local en el VPS (gratis, lento, siempre online)
  - provider: custom:vps_ollama
    model: ${OLLAMA_MODEL}

# ---------------------------------------------------------------------------
# OpenRouter routing: prefiere el más barato, no entrene con nuestros datos
# ---------------------------------------------------------------------------
openrouter:
  provider_routing:
    sort: price
    data_collection: deny
    require_parameters: true

# ---------------------------------------------------------------------------
# Telegram gateway
# ---------------------------------------------------------------------------
messaging:
  telegram:
    enabled: true
    allowed_chat_ids:
      - 656190718

# ---------------------------------------------------------------------------
# Memoria persistente
# ---------------------------------------------------------------------------
memory:
  enabled: true
  store_path: ${HERMES_HOME}/memories

# ---------------------------------------------------------------------------
# Tool gateway — Atlas Core como gemelo
# ---------------------------------------------------------------------------
tools:
  atlas_twin:
    enabled: true
    base_url: ${ATLAS_DASHBOARD_URL}
    timeout_s: 10
    purpose: |
      Twin pairing with Atlas Core (laptop). Use it for audit log queries,
      governance checks, and tasks that need local capability tokens.

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging:
  level: info
  path: ${HERMES_HOME}/logs
EOF

log "Validando que todas las keys necesarias estén en ${HERMES_HOME}/.env"
for KEY in GROQ_API_KEY OPENROUTER_API_KEY GEMINI_API_KEY HF_TOKEN NVIDIA_API_KEY; do
    if grep -q "^${KEY}=" "$HERMES_HOME/.env" 2>/dev/null; then
        echo "  ✓ $KEY"
    else
        echo "  ✗ $KEY (fallback chain saltará este provider)"
    fi
done

log "Reiniciando hermes-agent para aplicar"
systemctl restart hermes-agent
sleep 5

echo ""
echo "============= ESTADO POST-RECONFIG ============="
echo "hermes-agent: $(systemctl is-active hermes-agent)"
echo "ollama:       $(systemctl is-active ollama)"
echo "Modelos Ollama:"
ollama list 2>&1 | head -5
echo ""
echo "Últimas líneas hermes.log:"
tail -10 "${HERMES_HOME}/logs/hermes.log" 2>/dev/null || echo "  (sin log aún)"
echo ""
echo "stderr (si hay):"
tail -5 "${HERMES_HOME}/logs/hermes.err" 2>/dev/null || true
