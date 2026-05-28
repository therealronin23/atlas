#!/bin/bash
set -uo pipefail
HOME_=/root/.hermes
HBIN=$HOME_/venv/bin/hermes
export XDG_RUNTIME_DIR=/run/user/0
log() { echo "[final] $*"; }

log "1/5 Stop gateway"
systemctl --user stop hermes-gateway.service 2>/dev/null || true

log "2/5 config.yaml — HuggingFace para compresión (131K context, sin Ollama detection issue)"
cp $HOME_/config.yaml $HOME_/config.yaml.bak.final.$(date +%s) 2>/dev/null || true
cat > $HOME_/config.yaml <<'YAML'
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

# CLAVE: compression model usa HF (Qwen2.5-72B, 131K context).
# El qwen2.5:3b local lo reporta como 32K aunque le pasemos
# OLLAMA_CONTEXT_LENGTH, y Hermes crashea con < 64K.
auxiliary:
  compression:
    provider: huggingface
    model: Qwen/Qwen2.5-72B-Instruct
    context_length: 131072
  classification:
    provider: huggingface
    model: Qwen/Qwen2.5-72B-Instruct
    context_length: 131072

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
    allowed_chat_ids: [656190718]
    home_channel: 656190718

memory:
  enabled: true
  store_path: /root/.hermes/memories

logging:
  level: info
  path: /root/.hermes/logs

approvals:
  destructive_slash_confirm: false
YAML

log "3/5 Instalar rest-graphql-debugger con identifier completo"
$HBIN skills install --yes official/software-development/rest-graphql-debugger 2>&1 | tail -3 || \
  $HBIN skills install --yes "official/software-development/rest-graphql-debugger" 2>&1 | tail -3 || \
  log "   skill no instalada (probable identifier mismatch en el Hub)"

log "4/5 Listar skills"
$HBIN skills list 2>&1 | tail -10

log "5/5 Start gateway"
systemctl --user start hermes-gateway.service
sleep 8
echo "=== ESTADO ==="
systemctl --user is-active hermes-gateway.service
echo "=== Last 15 log lines ==="
journalctl --user -u hermes-gateway.service --no-pager -n 15 | tail -15
