#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOTENV_PATH="$ROOT_DIR/.env"
if [[ -f "$DOTENV_PATH" && "${ATLAS_SAFE_DOTENV_FILE:-}" != "$DOTENV_PATH" ]]; then
  export ATLAS_SAFE_DOTENV_FILE="$DOTENV_PATH"
  exec python3 "$ROOT_DIR/scripts/safe_dotenv.py" "$DOTENV_PATH" -- \
    bash "$(readlink -f "${BASH_SOURCE[0]}")" "$@"
fi
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/atlas-hermes-local"
PID_FILE="${STATE_DIR}/hermes-local.pid"
LOG_FILE="${STATE_DIR}/hermes-local.log"

mkdir -p "${STATE_DIR}"
chmod 700 "${STATE_DIR}"

: "${HERMES_API_KEY:?HERMES_API_KEY no está definido en .env o entorno}"
if (( ${#HERMES_API_KEY} < 32 )); then
  echo "HERMES_API_KEY debe contener al menos 32 caracteres" >&2
  exit 1
fi

export HERMES_BIND_ADDR="${HERMES_BIND_ADDR:-127.0.0.1}"
export HERMES_PORT="${HERMES_PORT:-8443}"

PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
AGENT_SCRIPT="${ROOT_DIR}/scripts/hermes_agent_stub/agent.py"

is_running() {
  if [[ ! -f "${PID_FILE}" ]]; then
    return 1
  fi
  local pid
  pid="$(cat "${PID_FILE}")"
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null
}

start() {
  if is_running; then
    echo "Hermes local ya está activo (pid $(cat "${PID_FILE}"))"
    return 0
  fi
  setsid "${PYTHON_BIN}" "${AGENT_SCRIPT}" >>"${LOG_FILE}" 2>&1 </dev/null &
  local spawned_pid=$!
  printf '%s\n' "${spawned_pid}" >"${PID_FILE}"
  sleep 1
  if ! is_running; then
    rm -f "${PID_FILE}"
    echo "Hermes local no arrancó. Revisa ${LOG_FILE}" >&2
    return 1
  fi
  echo "Hermes local activo en http://${HERMES_BIND_ADDR}:${HERMES_PORT} (pid $(cat "${PID_FILE}"))"
}

stop() {
  if ! is_running; then
    rm -f "${PID_FILE}"
    echo "Hermes local no está activo"
    return 0
  fi
  local pid
  pid="$(cat "${PID_FILE}")"
  kill "${pid}"
  rm -f "${PID_FILE}"
  echo "Hermes local detenido"
}

status() {
  if is_running; then
    echo "Hermes local activo en http://${HERMES_BIND_ADDR}:${HERMES_PORT} (pid $(cat "${PID_FILE}"))"
    return 0
  fi
  echo "Hermes local detenido"
  return 1
}

logs() {
  touch "${LOG_FILE}"
  tail -n 40 "${LOG_FILE}"
}

case "${1:-status}" in
  start) start ;;
  stop) stop ;;
  restart) stop || true; start ;;
  status) status ;;
  logs) logs ;;
  *)
    echo "Uso: $0 {start|stop|restart|status|logs}" >&2
    exit 2
    ;;
esac
