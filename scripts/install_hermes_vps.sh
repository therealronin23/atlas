#!/usr/bin/env bash
#
# install_hermes_vps.sh — Atlas Core / Gate C / C1
#
# Despliega el stub de Hermes Agent en un VPS Ubuntu 22.04+ fresco.
# Idempotente: re-ejecutar es seguro.
#
# Pasos:
#   1) Docker Engine + Compose plugin (script oficial get.docker.com)
#   2) Usuario sistema 'hermes' + estructura /opt/hermes/{data,logs,config}
#   3) Genera /opt/hermes/.env con HERMES_API_KEY aleatorio si no existe
#   4) Copia scripts/hermes_agent_stub/* a /opt/hermes/agent
#   5) docker compose up -d
#   6) systemd unit para auto-arranque
#   7) Verifica el contenedor responde
#
# Uso (desde el VPS, como root):
#     curl -fsSL https://raw.githubusercontent.com/therealronin23/atlas/main/scripts/install_hermes_vps.sh | bash
#   o si ya has clonado el repo:
#     sudo bash scripts/install_hermes_vps.sh
#
# Variables opcionales del entorno:
#   HERMES_API_KEY    si ya existe, NO se sobreescribe; se usa el valor dado
#   HERMES_PORT       default 8443
#   HERMES_REPO_URL   default https://github.com/therealronin23/atlas.git
#   HERMES_REPO_REF   default main

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: ejecuta como root (sudo bash $0)" >&2
  exit 2
fi

HERMES_PORT="${HERMES_PORT:-8443}"
HERMES_REPO_URL="${HERMES_REPO_URL:-https://github.com/therealronin23/atlas.git}"
HERMES_REPO_REF="${HERMES_REPO_REF:-main}"
HERMES_HOME="/opt/hermes"
HERMES_USER="hermes"

log()  { echo "[$(date -u +%FT%TZ)] $*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1) Docker
# ---------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  log "Instalando Docker Engine..."
  curl -fsSL https://get.docker.com | sh
else
  log "Docker ya instalado: $(docker --version)"
fi

if ! docker compose version >/dev/null 2>&1; then
  fail "Docker Compose plugin no disponible. Reinstala Docker."
fi

# ---------------------------------------------------------------------------
# 2) Usuario y estructura
# ---------------------------------------------------------------------------
if ! id "${HERMES_USER}" >/dev/null 2>&1; then
  log "Creando usuario sistema '${HERMES_USER}'..."
  useradd --system --home-dir "${HERMES_HOME}" --shell /usr/sbin/nologin "${HERMES_USER}"
fi

install -d -m 0750 -o "${HERMES_USER}" -g "${HERMES_USER}" \
  "${HERMES_HOME}" \
  "${HERMES_HOME}/data" \
  "${HERMES_HOME}/logs" \
  "${HERMES_HOME}/agent"

# ---------------------------------------------------------------------------
# 3) .env (no sobreescribe)
# ---------------------------------------------------------------------------
ENV_FILE="${HERMES_HOME}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  if [[ -z "${HERMES_API_KEY:-}" ]]; then
    HERMES_API_KEY="$(head -c 32 /dev/urandom | base64 | tr -d '=+/' | head -c 43)"
    log "HERMES_API_KEY generado (guardalo en Atlas Core: HERMES_API_KEY=${HERMES_API_KEY})"
  fi
  umask 077
  cat > "${ENV_FILE}" <<EOF
HERMES_API_KEY=${HERMES_API_KEY}
HERMES_BIND_ADDR=0.0.0.0
HERMES_PORT=${HERMES_PORT}
EOF
  chown "${HERMES_USER}:${HERMES_USER}" "${ENV_FILE}"
  chmod 0640 "${ENV_FILE}"
else
  log ".env existente preservado en ${ENV_FILE}"
fi

# ---------------------------------------------------------------------------
# 4) Copiar artefactos del stub
# ---------------------------------------------------------------------------
SRC_DIR=""
if [[ -d "$(dirname "$0")/hermes_agent_stub" ]]; then
  SRC_DIR="$(cd "$(dirname "$0")/hermes_agent_stub" && pwd)"
elif [[ -d "/opt/hermes-src" ]]; then
  SRC_DIR="/opt/hermes-src/scripts/hermes_agent_stub"
else
  log "Clonando ${HERMES_REPO_URL}@${HERMES_REPO_REF} en /opt/hermes-src..."
  apt-get update -y && apt-get install -y --no-install-recommends git
  rm -rf /opt/hermes-src
  git clone --depth 1 --branch "${HERMES_REPO_REF}" "${HERMES_REPO_URL}" /opt/hermes-src
  SRC_DIR="/opt/hermes-src/scripts/hermes_agent_stub"
fi

[[ -d "${SRC_DIR}" ]] || fail "no encuentro hermes_agent_stub en ${SRC_DIR}"
install -m 0644 -o "${HERMES_USER}" -g "${HERMES_USER}" \
  "${SRC_DIR}/agent.py" "${SRC_DIR}/Dockerfile" "${SRC_DIR}/docker-compose.yml" \
  "${HERMES_HOME}/agent/"

# ---------------------------------------------------------------------------
# 5) Levantar contenedor
# ---------------------------------------------------------------------------
log "docker compose build + up..."
(cd "${HERMES_HOME}/agent" && docker compose up -d --build)

# ---------------------------------------------------------------------------
# 6) systemd unit
# ---------------------------------------------------------------------------
UNIT_FILE="/etc/systemd/system/hermes-agent.service"
if [[ ! -f "${UNIT_FILE}" ]]; then
  log "Creando unit ${UNIT_FILE}..."
  cat > "${UNIT_FILE}" <<EOF
[Unit]
Description=Hermes Agent (Atlas Core / Gate C stub)
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${HERMES_HOME}/agent
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable hermes-agent.service
fi

# ---------------------------------------------------------------------------
# 7) Verificacion
# ---------------------------------------------------------------------------
log "Esperando puerto ${HERMES_PORT}..."
for i in $(seq 1 10); do
  if (echo > /dev/tcp/127.0.0.1/${HERMES_PORT}) 2>/dev/null; then
    log "OK: puerto ${HERMES_PORT} abierto"
    break
  fi
  sleep 1
  [[ $i -eq 10 ]] && fail "el agente no escucha en ${HERMES_PORT} tras 10s"
done

cat <<EOF

============================================================
  Hermes Agent stub instalado.

  Configura en Atlas Core (.env o exports):
    HERMES_BASE_URL=http://<tailscale-ip>:${HERMES_PORT}
    HERMES_API_KEY=$(grep '^HERMES_API_KEY=' "${ENV_FILE}" | cut -d= -f2)

  Siguiente paso (Gate C / C2): instalar Tailscale en este VPS
  y en el host Atlas, y usar la IP Tailscale como HERMES_BASE_URL.

  Smoke test desde Atlas Core:
    HERMES_BASE_URL=... HERMES_API_KEY=... \\
    PYTHONPATH=src python scripts/hermes_smoke.py
============================================================
EOF
