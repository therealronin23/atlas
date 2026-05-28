#!/usr/bin/env bash
# ============================================================================
# fix_hermes_local_primary.sh — Ollama qwen2.5:3b primario en VPS.
#
# Objetivo: exprimir el VPS al máximo. qwen2.5:3b es lo más grande que cabe
# en 4 GB de RAM con 64K contexto cuando activamos KV-cache quantization.
# Conversación gratis 24/7, latencia 3-5 tok/s (lenta pero siempre disponible).
# HuggingFace queda como fallback rápido para cuando local no llega.
#
# Si qwen2.5:3b causa OOM en uso real, el script tiene plan B: vuelve a 1.5b
# automáticamente.
#
# Idempotente. Aplicar en VPS como root:
#   ssh root@<ip> 'bash -s' < scripts/fix_hermes_local_primary.sh
# ============================================================================
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-656190718}"
TARGET_MODEL="${TARGET_MODEL:-qwen2.5:3b}"
FALLBACK_MODEL="qwen2.5:1.5b"
log() { echo "[fix-local] $*"; }

# ---------------------------------------------------------------------------
# 1. Cuantizar KV cache (mitad+) y subir context para Ollama
# ---------------------------------------------------------------------------
log "1/5 Configurar Ollama systemd con KV cache q4 + contexto 64K"
mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/atlas-twin.conf <<'OLLAMA'
[Service]
# Reduce el KV cache 4x → cabe más context en menos RAM
Environment="OLLAMA_KV_CACHE_TYPE=q4_0"
Environment="OLLAMA_CONTEXT_LENGTH=65536"
# Solo 1 modelo cargado a la vez en CPX22 (4 GB)
Environment="OLLAMA_MAX_LOADED_MODELS=1"
# Bind Tailscale + local (para que Atlas en laptop también pueda usar)
Environment="OLLAMA_HOST=0.0.0.0:11434"
OLLAMA
systemctl daemon-reload
systemctl restart ollama
sleep 3

# ---------------------------------------------------------------------------
# 2. Pull del modelo target (~2 GB descarga)
# ---------------------------------------------------------------------------
log "2/5 Descargar ${TARGET_MODEL} (~2 GB, tarda 1-3 min)"
if ! ollama pull "${TARGET_MODEL}" 2>&1 | tail -5; then
    log "  WARN: fallo al descargar ${TARGET_MODEL}. Sigue con ${FALLBACK_MODEL}"
    TARGET_MODEL="${FALLBACK_MODEL}"
fi
ollama list | head -10

# ---------------------------------------------------------------------------
# 3. Probar que el modelo carga sin OOM (test rápido)
# ---------------------------------------------------------------------------
log "3/5 Smoke test del modelo (un prompt corto)"
SMOKE=$(timeout 60 ollama run "${TARGET_MODEL}" "responde solo OK" 2>&1 | head -3 || echo "TIMEOUT")
echo "  → $SMOKE"
if echo "$SMOKE" | grep -qiE "out of memory|oom|cannot allocate|killed"; then
    log "  OOM detectado con ${TARGET_MODEL} → revirtiendo a ${FALLBACK_MODEL}"
    TARGET_MODEL="${FALLBACK_MODEL}"
fi
log "  modelo final: ${TARGET_MODEL}"

# ---------------------------------------------------------------------------
# 4. Reescribir config.yaml con local primary + HF/cloud fallback
# ---------------------------------------------------------------------------
log "4/5 Reescribir config.yaml (Ollama primary)"
cp "${HERMES_HOME}/config.yaml" "${HERMES_HOME}/config.yaml.bak.local.$(date +%s)"
cat > "${HERMES_HOME}/config.yaml" <<EOF
# Hermes-Agent — config v6 (Ollama local primary, ADR-026 twin)
#
# Filosofía: aprovechamos el VPS al máximo. Conversación normal va por el
# modelo local de Ollama (gratis, 24/7, sin rate-limits). Cuando local no
# llega (tareas que requieren razonamiento profundo o contexto enorme),
# saltamos a HuggingFace primero y al resto de proveedores cloud después.

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
  default: ${TARGET_MODEL}
  context_length: 65536   # alineado con OLLAMA_CONTEXT_LENGTH

# Fallbacks ordenados: HF (el único cloud que aceptó payload completo) primero,
# luego Gemini directo (free tier generoso), luego OpenRouter + Groq como
# salidas de emergencia. Atlas siempre puede ser consultado vía tool.
fallback_providers:
  - provider: huggingface
    model: Qwen/Qwen2.5-72B-Instruct
    context_length: 131072
  - provider: huggingface
    model: meta-llama/Llama-3.3-70B-Instruct
    context_length: 131072
  - provider: gemini
    model: gemini-2.0-flash-exp
    context_length: 1048576
  - provider: openrouter
    model: anthropic/claude-3.5-sonnet
    context_length: 200000
  - provider: openrouter
    model: meta-llama/llama-3.3-70b-instruct:free
    context_length: 131072
  - provider: nvidia
    model: nvidia/nemotron-3-super-120b-a12b
    context_length: 131072
  - provider: custom:groq
    model: llama-3.3-70b-versatile
    context_length: 131072

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

# ---------------------------------------------------------------------------
# 5. Reiniciar y verificar
# ---------------------------------------------------------------------------
log "5/5 Reiniciar hermes-gateway"
export XDG_RUNTIME_DIR="/run/user/$(id -u root)"
systemctl --user restart hermes-gateway.service
sleep 6

echo ""
echo "============= ESTADO ============="
echo "Modelo local activo: ${TARGET_MODEL}"
echo ""
echo "Memoria usada por Ollama (después de cargar modelo):"
ps -o pid,rss,cmd -C ollama 2>&1 | head -5
echo ""
echo "Memoria libre del VPS:"
free -h | head -3
echo ""
echo "hermes-gateway: $(systemctl --user is-active hermes-gateway.service)"
journalctl --user -u hermes-gateway.service --no-pager -n 12 2>&1 | tail -12
echo ""
echo "👉 Manda 'hola' al bot."
echo "   - Si responde en ~5-15s con texto del LLM local → 🎯 funcionando"
echo "   - Si tarda ~30s y dice 'switching to fallback' → ${TARGET_MODEL} es muy grande,"
echo "     revierte con: ssh root@vps 'ollama rm ${TARGET_MODEL} && bash <(curl ...)/fix_hermes_local_primary.sh'"
echo "     pero con TARGET_MODEL=${FALLBACK_MODEL}"
