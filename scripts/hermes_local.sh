#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/atlas-hermes-local"
PID_FILE="${STATE_DIR}/hermes-local.pid"
LOG_FILE="${STATE_DIR}/hermes-local.log"

mkdir -p "${STATE_DIR}"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  source "${ROOT_DIR}/.env"
  set +a
fi

: "${HERMES_API_KEY:?HERMES_API_KEY no está definido en .env o entorno}"

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
  setsid bash -c '
    echo $$ > "'"${PID_FILE}"'"
    exec "'"${PYTHON_BIN}"'" "'"${AGENT_SCRIPT}"'" >>"'"${LOG_FILE}"'" 2>&1 </dev/null
  ' >/dev/null 2>&1 &
  sleep 1
  if ! is_running; then
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
