#!/bin/bash
set -uo pipefail
HOME_=/root/.hermes
export XDG_RUNTIME_DIR=/run/user/0
log() { echo "[fix] $*"; }

log "1/4 Reparar Ollama: vuelta a loopback 127.0.0.1"
mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/atlas-twin.conf <<'OLLAMA'
[Service]
Environment="OLLAMA_KV_CACHE_TYPE=q4_0"
Environment="OLLAMA_CONTEXT_LENGTH=65536"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
# Restored to 127.0.0.1 — 0.0.0.0 was breaking the loopback alias
Environment="OLLAMA_HOST=127.0.0.1:11434"
OLLAMA
systemctl daemon-reload
systemctl restart ollama
sleep 4
echo "Ollama version check:"
curl -sf http://127.0.0.1:11434/api/version 2>&1 | head -1

log "2/4 Stop hermes-gateway y reescribir config"
systemctl --user stop hermes-gateway.service 2>/dev/null || true
cp $HOME_/config.yaml $HOME_/config.yaml.bak.groq.$(date +%s) 2>/dev/null || true

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

# Groq primary: tiene 30 req/min libres (suficiente para Telegram)
# y la latencia es ~500 tok/s — el más rápido.
model:
  provider: custom:groq
  default: llama-3.3-70b-versatile
  context_length: 131072

# Compression: Groq también, pero con modelo más pequeño para ahorrar quota.
auxiliary:
  compression:
    provider: custom:groq
    model: llama-3.1-8b-instant
    context_length: 131072
  classification:
    provider: custom:groq
    model: llama-3.1-8b-instant
    context_length: 131072

# Fallbacks: HF y OpenRouter QUITADOS (quota mensual exhausta).
# Gemini sólo en última instancia (también limitado), Ollama local final.
fallback_providers:
  - provider: custom:groq
    model: llama-3.1-8b-instant
    context_length: 131072
  - provider: gemini
    model: gemini-2.0-flash
    context_length: 1048576
  - provider: nvidia
    model: nvidia/nemotron-3-super-120b-a12b
    context_length: 131072
  - provider: custom:vps_ollama
    model: qwen2.5:3b
    context_length: 65536
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

log "3/4 Start gateway"
systemctl --user start hermes-gateway.service
sleep 6

log "4/4 Estado"
systemctl --user is-active hermes-gateway.service
ps -C python -o pid,etime,rss --sort=-rss | head -3
echo ""
echo "Memoria libre:"
free -h | head -2
echo ""
echo "Últimos logs (no errores graves esperados):"
journalctl --user -u hermes-gateway.service --no-pager --since "30 sec ago" 2>&1 | tail -8
