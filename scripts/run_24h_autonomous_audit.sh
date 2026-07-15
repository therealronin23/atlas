#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="${ATLAS_CORE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"
DOTENV_PATH="$(readlink -f "$ROOT/.env" 2>/dev/null || printf '%s' "$ROOT/.env")"
if [[ -f "$DOTENV_PATH" && "${ATLAS_SAFE_DOTENV_FILE:-}" != "$DOTENV_PATH" ]]; then
  export ATLAS_SAFE_DOTENV_FILE="$DOTENV_PATH"
  SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
  exec python3 "$(dirname "$SCRIPT_PATH")/safe_dotenv.py" "$DOTENV_PATH" -- \
    bash "$SCRIPT_PATH" "$@"
fi

if [[ -d ".venv" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

export PYTHONPATH="${PYTHONPATH:-$ROOT/src}"
export MYPYPATH="${MYPYPATH:-$ROOT/src}"
export ATLAS_AUDIT_COMPUTER_USE="${ATLAS_AUDIT_COMPUTER_USE:-1}"

# Postmortem 2026-05-29: el CLI escribe en la cadena Merkle del workspace
# (incluso en operaciones de lectura). Con el servicio autónomo corriendo, dos
# escritores sobre la misma cadena la corrompen. El audit corre SIEMPRE sobre
# un HOME aislado; ATLAS_AUDIT_HOME permite elegir cuál, pero nunca el vivo.
export ATLAS_HOME="${ATLAS_AUDIT_HOME:-$ROOT/.atlas-audit-home}"
LIVE_HOME="$(readlink -f "${HOME}/atlas" 2>/dev/null || echo "${HOME}/atlas")"
if [[ "$(readlink -f "$ATLAS_HOME" 2>/dev/null || echo "$ATLAS_HOME")" == "$LIVE_HOME" ]]; then
  echo "FATAL: ATLAS_AUDIT_HOME apunta al workspace vivo ($LIVE_HOME); abortando" >&2
  exit 1
fi
mkdir -p "$ATLAS_HOME"
chmod 700 "$ATLAS_HOME"

mkdir -p "$ROOT/logs" "$ROOT/docs"
chmod 700 "$ROOT/logs"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$ROOT/logs/autonomous_audit_24h_${STAMP}.log"
PID_FILE="$ROOT/logs/autonomous_audit_24h.pid"
LOCK_FILE="$ROOT/logs/autonomous_audit_24h.lock"

# systemd serializa su propia unidad, pero el mismo runner también se puede
# lanzar a mano.  El lock evita dos auditorías simultáneas y no depende de que
# un PID file histórico esté limpio.
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "FATAL: ya hay una auditoría autónoma de 24h en ejecución" >&2
  exit 1
fi

printf '%s\n' "$$" >"$PID_FILE"
cleanup() {
  if [[ -f "$PID_FILE" ]] && [[ "$(<"$PID_FILE")" == "$$" ]]; then
    rm -f "$PID_FILE"
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

log_step() {
  printf '\n[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1"
}

{
  log_step "Atlas 24h autonomous audit started"
  log_step "Strict reality preflight (state only; tests run once, sharded, below)"
  atlas reality --strict --json \
    > "$ROOT/docs/reality_latest.json"

  log_step "Complete audit script"
  python scripts/audit_complete.py

  log_step "Static security audit"
  atlas security-audit src/atlas --json \
    > "$ROOT/docs/security_audit_latest.json"

  log_step "Cold self-audit and update proposal cycle"
  atlas self-audit run --hours 24 --profile full --cycle-minutes 60

  log_step "Final strict reality check (state only)"
  atlas reality --strict --json \
    > "$ROOT/docs/reality_after_24h.json"

  log_step "Atlas 24h autonomous audit completed"
} 2>&1 | tee -a "$LOG"
