#!/usr/bin/env bash
# ============================================================================
# install_hermes_deps_and_skill.sh — Completa el stack de tools de Hermes.
#
# El post-install original de Hermes warneó que faltaban Node.js, Chromium,
# ripgrep y ffmpeg → todas sus tools de navegación/búsqueda/voz están OFF.
# Por eso cuando le pides "consulta el dashboard de Atlas" responde que no
# tiene acceso. Sin esas deps Hermes es prácticamente solo un chat.
#
# Este script:
#   1. apt install Node.js (NodeSource), Chromium, ripgrep, ffmpeg
#   2. `hermes postinstall` para que detecte las nuevas deps
#   3. Crea un skill Python custom 'atlas_twin' que llama al dashboard de Atlas
#   4. Reinicia hermes-gateway
#
# Idempotente. Aplicar en VPS como root:
#   ssh root@<ip> 'bash -s' < scripts/install_hermes_deps_and_skill.sh
# ============================================================================
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
ATLAS_DASHBOARD_URL="${ATLAS_DASHBOARD_URL:-http://100.85.236.58:7331}"
log() { echo "[deps] $*"; }

# ---------------------------------------------------------------------------
# 1. System dependencies
# ---------------------------------------------------------------------------
log "1/5 Instalando deps del sistema (Node.js 20, ripgrep, ffmpeg, chromium)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq

# Node.js 20 LTS via NodeSource (más reciente que apt default)
if ! command -v node >/dev/null 2>&1; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null 2>&1
    apt-get install -y -qq nodejs >/dev/null
fi
echo "  ✓ node: $(node --version 2>/dev/null)"

apt-get install -y -qq ripgrep ffmpeg chromium-browser 2>&1 | tail -2 || \
    apt-get install -y -qq ripgrep ffmpeg 2>&1 | tail -2
echo "  ✓ ripgrep: $(rg --version 2>/dev/null | head -1)"
echo "  ✓ ffmpeg:  $(ffmpeg -version 2>/dev/null | head -1)"
echo "  ✓ chromium: $(chromium-browser --version 2>/dev/null || chromium --version 2>/dev/null || echo 'not installed')"

# ---------------------------------------------------------------------------
# 2. Re-run Hermes postinstall (registra las nuevas deps)
# ---------------------------------------------------------------------------
log "2/5 Re-ejecutar hermes postinstall"
"${HERMES_HOME}/venv/bin/hermes" postinstall 2>&1 | tail -8 || true

# ---------------------------------------------------------------------------
# 3. Skill Python para el twin con Atlas
# ---------------------------------------------------------------------------
log "3/5 Crear skill custom 'atlas_twin' en ${HERMES_HOME}/skills/"
mkdir -p "${HERMES_HOME}/skills/atlas_twin"
cat > "${HERMES_HOME}/skills/atlas_twin/__init__.py" <<'SKILL'
"""
atlas_twin — Hermes skill que llama al dashboard de Atlas Core (laptop).

Atlas vive en el HP Omen vía Tailscale en http://100.85.236.58:7331 (override
con ATLAS_DASHBOARD_URL env). Expone los endpoints:
  GET /api/health   → estado completo: governance, merkle, telegram, hermes_reachable
  GET /            → HTML dashboard (no usar desde skill)
  POST /api/hermes/webhook → callback inbound desde Hermes (HMAC)

Esta skill es read-only y solo expone /api/health para que Hermes pueda
informar al usuario sobre el estado del gemelo en el laptop.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def _atlas_url() -> str:
    return os.environ.get("ATLAS_DASHBOARD_URL", "http://100.85.236.58:7331").rstrip("/")


def atlas_health() -> dict[str, Any]:
    """Consulta el estado actual de Atlas Core (laptop) vía /api/health.

    Devuelve un dict con: version, uptime_s, merkle_chain_ok, governance_ok,
    hermes_reachable, telegram_running, gate_d_enabled, queue_depth, etc.

    Si Atlas está offline (laptop dormido), devuelve {"reachable": False}.
    """
    url = f"{_atlas_url()}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
            data["reachable"] = True
            return data
    except (urllib.error.URLError, TimeoutError) as exc:
        return {
            "reachable": False,
            "error": str(exc),
            "hint": "Atlas-laptop puede estar dormido o sin atlas serve corriendo.",
        }


def atlas_status_summary() -> str:
    """Resumen humano del estado de Atlas. Devuelve un string corto."""
    h = atlas_health()
    if not h.get("reachable"):
        return f"❌ Atlas no responde: {h.get('error', 'unknown')}"
    bits = [
        f"Atlas {h.get('version', '?')}",
        f"uptime {int(h.get('uptime_s', 0))}s",
        f"merkle {'✓' if h.get('merkle_chain_ok') else '✗'}",
        f"governance {'✓' if h.get('governance_ok') else '✗'}",
        f"hermes_reachable={h.get('hermes_reachable', '?')}",
        f"telegram_running={h.get('telegram_running', '?')}",
        f"gate_d={h.get('gate_d_enabled', '?')}",
        f"queue={h.get('queue_depth', 0)}",
    ]
    return " · ".join(bits)


# Hermes skill metadata
TOOLS = [
    {
        "name": "atlas_health",
        "description": (
            "Consulta el estado completo del gemelo Atlas Core en el laptop "
            "de Tomás vía Tailscale. Úsalo cuando te pregunten por Atlas, "
            "el dashboard, el merkle chain, el pipeline, o el estado del "
            "core local."
        ),
        "function": atlas_health,
    },
    {
        "name": "atlas_status_summary",
        "description": (
            "Devuelve un resumen humano de una sola línea del estado de Atlas. "
            "Más corto que atlas_health, útil para responder rápido al usuario."
        ),
        "function": atlas_status_summary,
    },
]
SKILL

cat > "${HERMES_HOME}/skills/atlas_twin/skill.yaml" <<SKILL_META
# Metadata del skill atlas_twin para que Hermes-Agent lo registre
name: atlas_twin
version: 1.0.0
description: |
  Twin pairing con Atlas Core (laptop). Permite a Hermes consultar el
  estado del gemelo via REST sobre Tailscale.
author: tomas.asin.gonzalez@gmail.com
entrypoint: __init__.py
tools:
  - atlas_health
  - atlas_status_summary
permissions:
  network:
    - "100.85.236.58:7331"
SKILL_META

log "  ✓ skill atlas_twin creado en ${HERMES_HOME}/skills/atlas_twin/"

# ---------------------------------------------------------------------------
# 4. Re-instalar skill via CLI de Hermes (idempotente)
# ---------------------------------------------------------------------------
log "4/5 Registrar skill con Hermes"
"${HERMES_HOME}/venv/bin/hermes" skills install "${HERMES_HOME}/skills/atlas_twin" 2>&1 | tail -5 || \
    log "  (hermes skills install no soportó la sintaxis, el skill puede que ya esté visible por convención)"
"${HERMES_HOME}/venv/bin/hermes" skills list 2>&1 | tail -15 || true

# ---------------------------------------------------------------------------
# 5. Reiniciar hermes-gateway
# ---------------------------------------------------------------------------
log "5/5 Reiniciar hermes-gateway"
export XDG_RUNTIME_DIR="/run/user/$(id -u root)"
systemctl --user restart hermes-gateway.service
sleep 6

echo ""
echo "============= ESTADO ============="
echo "hermes-gateway: $(systemctl --user is-active hermes-gateway.service)"
journalctl --user -u hermes-gateway.service --no-pager -n 12 2>&1 | tail -12
echo ""
echo "👉 Manda al bot:"
echo "   'qué estado tiene Atlas? usa el skill atlas_twin'"
echo ""
echo "   Si Atlas-laptop NO está corriendo, primero arráncalo:"
echo "     cd ~/proyectos/atlas-core && set -a; source .env; set +a"
echo "     nohup .venv/bin/atlas serve > /tmp/atlas.log 2>&1 &"
