#!/usr/bin/env bash
# ============================================================================
# fix_hermes_hf_primary.sh — HuggingFace primario (es el único que aceptó el
# payload completo de Hermes en pruebas). Mejor latencia: respuesta en ~3-5s
# en vez de los ~30s de cascada por todos los providers cloud.
#
# Además: escribir SOUL.md con la identidad twin para que Hermes sepa qué es.
# ============================================================================
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-656190718}"
log() { echo "[fix-hf] $*"; }

log "1/4 Backup config.yaml"
cp "${HERMES_HOME}/config.yaml" "${HERMES_HOME}/config.yaml.bak.hf.$(date +%s)"

log "2/4 Reescribir config con HuggingFace primary"
cat > "${HERMES_HOME}/config.yaml" <<EOF
# Hermes-Agent — config v5 (HuggingFace primary, ADR-026 twin)

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

# HF autoroutea 20+ modelos open con failover interno. Solo en pruebas
# aceptó el payload completo de Hermes sin 413 ni rate-limit.
model:
  provider: huggingface
  default: Qwen/Qwen2.5-72B-Instruct
  context_length: 131072

# Fallbacks: si HF se cae, cualquiera de estos como respaldo
fallback_providers:
  - provider: huggingface
    model: meta-llama/Llama-3.3-70B-Instruct
    context_length: 131072
  - provider: gemini
    model: gemini-2.0-flash-exp
    context_length: 1048576
  - provider: openrouter
    model: meta-llama/llama-3.3-70b-instruct:free
    context_length: 131072
  - provider: openrouter
    model: anthropic/claude-3.5-sonnet
    context_length: 200000
  - provider: nvidia
    model: nvidia/nemotron-3-super-120b-a12b
    context_length: 131072
  - provider: custom:groq
    model: llama-3.3-70b-versatile
    context_length: 131072
  # Last resort: Ollama local en VPS
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

log "3/4 Escribir SOUL.md con identidad twin (Hermes lee esto al arrancar)"
cat > "${HERMES_HOME}/SOUL.md" <<'SOUL'
# Soy Hermes

Soy el gemelo VPS de **Atlas Core**, sistema operativo personal de inteligencia
de Tomás. Vivo en un Hetzner CPX22 vía Tailscale.

## Mi rol

- Ejecutor de Telegram para Tomás (@GodAtlas_bot).
- Razonamiento autónomo cuando Atlas (laptop) está dormido.
- Memoria persistente que sobrevive a reboots del laptop.
- Twin pairing con Atlas Core en `http://100.85.236.58:7331` para auditoría
  y capability tokens locales.

## Quién es Atlas

Atlas vive en el HP Omen de Tomás. Maneja:
- Governance L0 (constitución inmutable)
- Merkle SHA-256 audit chain
- Capability tokens (mínimo privilegio)
- KuzuDB para memoria semántica
- Pipeline Gate D con SLM classifier + InferenceHub
- ColdUpdateManager + SelfAuditLoop

Atlas y yo nos comunicamos via REST+HMAC sobre Tailscale (ADR-026).

## Cómo respondo

- En español, directo, sin formalidades innecesarias.
- Si me preguntan quién soy: soy Hermes, twin de Atlas. No un chatbot
  genérico.
- Si una tarea necesita herramientas locales del laptop de Tomás (git del
  workspace de Atlas, capability tokens, audit Merkle), invoco `atlas_twin`.
- Recuerdo lo que aprendo entre sesiones.

## Reglas inviolables

1. No ejecuto acciones destructivas sin aprobación explícita.
2. Respeto la Governance L0 de Atlas.
3. Todo lo que escribo a `memories/` es revisable por Tomás.
SOUL

log "4/4 Reiniciar hermes-gateway"
export XDG_RUNTIME_DIR="/run/user/$(id -u root)"
systemctl --user restart hermes-gateway.service
sleep 6

echo ""
echo "============= ESTADO ============="
systemctl --user is-active hermes-gateway.service
echo ""
echo "Primary ahora:"
grep -A3 '^model:' "${HERMES_HOME}/config.yaml" | head -5
echo ""
echo "Últimos logs:"
journalctl --user -u hermes-gateway.service --no-pager -n 10 2>&1 | tail -10
echo ""
echo "👉 Manda 'hola' al bot. Debe responder en ~3-5s (HF) sin cascada."
echo "👉 Manda 'quien eres?' — ahora con SOUL.md sabrá que es Hermes twin de Atlas."
