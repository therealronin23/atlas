#!/usr/bin/env bash
set -euo pipefail
# Monitor Graphify logs and switch provider if error thresholds exceeded.
cd "$(dirname "$0")/.."

# Bug 1 (2026-07-15): choose_fallback() nunca veia las API keys del .env
# porque nunca se cargaba tras el cd -- siempre caia al default openai:openai
# (modelo gpt-4o-mini, que NVIDIA no sirve). Mismo patron que
# run-graphify-quality-pipeline.sh.
if [ -f ".env" ]; then
  set -a
  source ".env"
  set +a
fi

LOG_MONITOR=/tmp/graphify_monitor.log
CHECK_INTERVAL=${GRAPHIFY_MONITOR_INTERVAL:-30}
INVALID_THRESHOLD=${GRAPHIFY_INVALID_THRESHOLD:-10}
HOLLOW_THRESHOLD=${GRAPHIFY_HOLLOW_THRESHOLD:-10}
# files to inspect (Bug 3a: /tmp/graphify_gemini_run.log estaba duplicado,
# doblando su contribucion a cada conteo)
WRAPPER_LOGS=(/tmp/graphify_run_async.log /tmp/graphify_gemini_run.log /tmp/graphify_nvidia_repo.log)
GRAPHIFY_LOG=graphify-out/logs/pipeline.log
STATE_FILE=${GRAPHIFY_MONITOR_STATE_FILE:-/tmp/graphify_monitor_state.json}

# Bug 3b: state helpers -- persisten el ultimo conteo ABSOLUTO visto por
# patron+fichero, para que count_pattern_delta pueda comparar solo el
# incremento desde la ultima pasada.
_state_get() {
  python3 - "$STATE_FILE" "$1" "$2" <<'PY'
import json
import sys
from pathlib import Path

state_path, pattern, path = sys.argv[1], sys.argv[2], sys.argv[3]
p = Path(state_path)
state = {}
if p.exists():
    try:
        state = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        state = {}
print(state.get(pattern + "||" + path, 0))
PY
}

_state_set() {
  python3 - "$STATE_FILE" "$1" "$2" "$3" <<'PY'
import json
import sys
from pathlib import Path

state_path, pattern, path, value = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
p = Path(state_path)
state = {}
if p.exists():
    try:
        state = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        state = {}
state[pattern + "||" + path] = value
p.write_text(json.dumps(state), encoding="utf-8")
PY
}

# helper: count NEW occurrences of a pattern across logs since the last check
# (Bug 3b: la version anterior contaba sobre el fichero completo acumulado en
# cada pasada del bucle, asi que una vez superado el umbral se quedaba
# "superado" para siempre aunque no hubiera fallos nuevos)
count_pattern_delta() {
  local pattern="$1"
  shift
  local total_delta=0
  for f in "$@"; do
    if [ -f "$f" ]; then
      local current previous delta
      current=$(grep -i -F "$pattern" "$f" 2>/dev/null | wc -l)
      previous=$(_state_get "$pattern" "$f")
      delta=$((current - previous))
      if [ "$delta" -lt 0 ]; then
        delta=0
      fi
      total_delta=$((total_delta + delta))
      _state_set "$pattern" "$f" "$current"
    fi
  done
  echo "$total_delta"
}
# helper: kill all running graphify extract processes (use explicit PIDs)
kill_graphify_extract() {
  local pids
  pids=$(pgrep -f "graphify extract" || true)
  if [ -n "$pids" ]; then
    echo "[monitor] killing graphify extract PIDs: $pids" >> "$LOG_MONITOR"
    for pid in $pids; do
      if [ -n "$pid" ]; then
        kill "$pid" 2>/dev/null || true
        sleep 1
      fi
    done
  fi
}
# choose fallback provider order when switching
choose_fallback() {
  # prefer NVIDIA via OpenAI-compatible mapping
  if [ -n "${NVIDIA_API_KEY:-}" ]; then
    echo "openai:nvidia"
    return
  fi
  if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    echo "claude:anthropic"
    return
  fi
  if [ -n "${OPENAI_API_KEY:-}" ]; then
    echo "openai:openai"
    return
  fi
  if [ -n "${OLLAMA_BASE_URL:-}" ]; then
    echo "ollama:local"
    return
  fi
  # fallback to gemini
  if [ -n "${GEMINI_API_KEY:-}" ]; then
    echo "gemini:gemini"
    return
  fi
  # default fallback
  echo "openai:openai"
}

# --- test-only entrypoints: evitan levantar el bucle infinito bajo pytest ---
if [ "${1:-}" = "--print-fallback-only" ]; then
  choose_fallback
  exit 0
fi

if [ "${1:-}" = "--count-pattern-delta" ]; then
  shift
  test_pattern="$1"
  shift
  count_pattern_delta "$test_pattern" "$@"
  exit 0
fi

if [ "${GRAPHIFY_MONITOR_TEST:-0}" = "1" ]; then
  exit 0
fi

echo "[monitor] starting at $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG_MONITOR"

# main loop
while true; do
  sleep "$CHECK_INTERVAL"
  # aggregate counts
  invalid=0
  invalid=$(count_pattern_delta "invalid JSON" "${WRAPPER_LOGS[@]}" "$GRAPHIFY_LOG")
  invalid=$((invalid + $(count_pattern_delta "returned invalid JSON" "${WRAPPER_LOGS[@]}" "$GRAPHIFY_LOG")))
  hollow=$(count_pattern_delta "hollow response" "${WRAPPER_LOGS[@]}" "$GRAPHIFY_LOG")
  echo "[monitor] $(date -u +%Y-%m-%dT%H:%M:%SZ) invalid=$invalid hollow=$hollow" >> "$LOG_MONITOR"

  if [ "$invalid" -gt "$INVALID_THRESHOLD" ] || [ "$hollow" -gt "$HOLLOW_THRESHOLD" ]; then
    echo "[monitor] threshold exceeded (invalid=$invalid hollow=$hollow) -> switching provider" >> "$LOG_MONITOR"
    # choose fallback
    fallback=$(choose_fallback)
    backend=${fallback%%:*}
    reason=${fallback#*:}
    # prepare env for NVIDIA mapping if chosen
    if [ "$backend" = "openai" ] && [ "${reason}" = "nvidia" ]; then
      export OPENAI_API_KEY="${OPENAI_API_KEY:-$NVIDIA_API_KEY}"
      export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://integrate.api.nvidia.com/v1}"
      model="${GRAPHIFY_OPENAI_MODEL:-meta/llama-3.3-70b-instruct}"
    elif [ "$backend" = "claude" ]; then
      model="${GRAPHIFY_CLAUDE_MODEL:-claude-2.1}" 
    elif [ "$backend" = "openai" ]; then
      model="${GRAPHIFY_OPENAI_MODEL:-gpt-4o-mini}"
    elif [ "$backend" = "ollama" ]; then
      model="${GRAPHIFY_OLLAMA_MODEL:-local}",
    elif [ "$backend" = "gemini" ]; then
      model="${GRAPHIFY_GEMINI_MODEL:-gemini-2.5}"
    else
      model="${GRAPHIFY_OPENAI_MODEL:-gpt-4o-mini}"
    fi

    # kill existing graphify extract processes
    kill_graphify_extract
    # launch conservative rerun with chosen backend
    echo "[monitor] launching conservative rerun with backend=$backend model=$model" >> "$LOG_MONITOR"
    ./scripts/run-graphify-quality-pipeline.sh --backend "$backend" --model "$model" --path . --token-budget 2000 --max-workers 1 --max-concurrency 1 --api-timeout 900 > /tmp/graphify_switched_run.log 2>&1 &
    echo $! > /tmp/graphify_switched.pid
    echo "[monitor] switched to $backend ($model), new PID $(cat /tmp/graphify_switched.pid)" >> "$LOG_MONITOR"
    # after switching, increase thresholds to avoid flapping
    INVALID_THRESHOLD=$((INVALID_THRESHOLD * 2))
    HOLLOW_THRESHOLD=$((HOLLOW_THRESHOLD * 2))
  fi

done
