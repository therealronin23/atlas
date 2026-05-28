#!/bin/bash
set -uo pipefail
HOME_=/root/.hermes
export XDG_RUNTIME_DIR=/run/user/0
log() { echo "[hf-primary] $*"; }

log "1/3 Stop gateway + backup"
systemctl --user stop hermes-gateway.service 2>/dev/null || true
cp $HOME_/config.yaml $HOME_/config.yaml.bak.hfprim.$(date +%s) 2>/dev/null || true

log "2/3 HF primary, sin OpenRouter (quota exhausted)"
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

# HF Qwen2.5-72B es el único que aceptó payload + se mantuvo. Primario.
model:
  provider: huggingface
  default: Qwen/Qwen2.5-72B-Instruct
  context_length: 131072

auxiliary:
  compression:
    provider: huggingface
    model: Qwen/Qwen2.5-72B-Instruct
    context_length: 131072
  classification:
    provider: huggingface
    model: Qwen/Qwen2.5-72B-Instruct
    context_length: 131072

# Fallback chain. OpenRouter QUITADO (free key exhausted, HTTP 403).
# Cuando rellenes quota o renueve mes, vuelve a añadirlo.
fallback_providers:
  - provider: huggingface
    model: meta-llama/Llama-3.3-70B-Instruct
    context_length: 131072
  - provider: gemini
    model: gemini-2.0-flash
    context_length: 1048576
  - provider: custom:groq
    model: llama-3.3-70b-versatile
    context_length: 131072
  - provider: custom:vps_ollama
    model: qwen2.5:1.5b
    context_length: 64000

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

log "3/3 Start gateway"
systemctl --user start hermes-gateway.service
sleep 6
echo "=== ESTADO ==="
systemctl --user is-active hermes-gateway.service
ps -C python -o pid,etime,rss --sort=-rss | head -3
echo ""
echo "=== Logs ==="
journalctl --user -u hermes-gateway.service --no-pager -n 12 | tail -12
