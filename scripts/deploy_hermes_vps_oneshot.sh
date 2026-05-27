#!/usr/bin/env bash
# ============================================================================
# deploy_hermes_vps_oneshot.sh — Wrapper que dispara la instalación remota
# del Hermes-Agent en la VPS desde el laptop, leyendo secretos del .env local.
#
# Uso (UNO solo, desde ~/proyectos/atlas-core/):
#   bash scripts/deploy_hermes_vps_oneshot.sh
#
# Lee TODO de .env. No expone secretos en `ps` (pasa por env del SSH).
# Idempotente. Al final imprime el HERMES_API_KEY para pegar en .env local.
# ============================================================================
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
VPS_HOST="${VPS_HOST:-100.108.132.116}"
VPS_USER="${VPS_USER:-root}"   # Hetzner Ubuntu cloud image; ronin/ubuntu no existen como usuarios locales
SCRIPT_REL="scripts/install_hermes_agent_vps.sh"

# Si Tailscale SSH está en check-mode, la primera conexión imprime una URL de
# autenticación. Avisamos al usuario para que no piense que se ha colgado.
cat <<NOTE
Nota: si Tailscale SSH del VPS está en check-mode, verás un mensaje del estilo
  "Tailscale SSH requires an additional check. To authenticate, visit: https://..."
Abre ese link en tu navegador (ya estás logged-in en Tailscale), apruebas la
sesión, y el deploy continúa solo. Es un click, una vez.
NOTE

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE no existe. Lánzalo desde ~/proyectos/atlas-core/" >&2
    exit 1
fi

# Cargar .env (no exporta a la shell padre; solo a esta y al ssh)
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${TELEGRAM_BOT_TOKEN:?Falta TELEGRAM_BOT_TOKEN en $ENV_FILE}"
: "${OPENROUTER_API_KEY:?Falta OPENROUTER_API_KEY en $ENV_FILE}"
: "${GROQ_API_KEY:?Falta GROQ_API_KEY en $ENV_FILE}"
NVIDIA_API_KEY="${NVIDIA_API_KEY:-}"
GEMINI_API_KEY="${GEMINI_API_KEY:-}"
HF_TOKEN="${HF_TOKEN:-}"
ATLAS_DASHBOARD_URL="${ATLAS_DASHBOARD_URL:-http://100.85.236.58:7331}"

echo "→ Copiando install script al VPS (${VPS_USER}@${VPS_HOST})"
scp -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
    "$SCRIPT_REL" "${VPS_USER}@${VPS_HOST}:~/install_hermes_agent_vps.sh"

echo "→ Ejecutando instalación remota (toma ~5-10 minutos: apt + ollama + modelo)"
ssh -o ConnectTimeout=10 "${VPS_USER}@${VPS_HOST}" \
    "TELEGRAM_BOT_TOKEN='${TELEGRAM_BOT_TOKEN}' \
     OPENROUTER_API_KEY='${OPENROUTER_API_KEY}' \
     GROQ_API_KEY='${GROQ_API_KEY}' \
     NVIDIA_API_KEY='${NVIDIA_API_KEY}' \
     GEMINI_API_KEY='${GEMINI_API_KEY}' \
     HF_TOKEN='${HF_TOKEN}' \
     ATLAS_DASHBOARD_URL='${ATLAS_DASHBOARD_URL}' \
     bash ~/install_hermes_agent_vps.sh"

echo ""
echo "============================================"
echo "✓ Hermes-Agent instalado en el VPS."
echo ""
echo "Pasos finales (manual):"
echo "  1) Copia el HERMES_API_KEY=... impreso arriba a tu .env local"
echo "  2) Verifica:   ssh ${VPS_USER}@${VPS_HOST} 'systemctl status hermes-agent --no-pager'"
echo "  3) Manda /start a @GodAtlas_bot en Telegram — debe responder Hermes (no Atlas)"
echo "  4) Reinicia atlas serve local: pkill -f 'atlas serve'; bash scripts/launch_atlas.sh"
echo "============================================"
