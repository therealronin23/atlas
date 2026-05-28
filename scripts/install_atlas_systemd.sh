#!/usr/bin/env bash
# ============================================================================
# install_atlas_systemd.sh — Instalar Atlas Core como systemd-user service
# en el laptop. Atlas vivirá detrás de un systemd unit que sobrevive logouts
# y reboots (idéntico patrón a Hermes-Agent en el VPS).
#
# Idempotente. Desde el repo:
#   bash scripts/install_atlas_systemd.sh
# ============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="${USER:-$(whoami)}"
UNIT_DST="$HOME/.config/systemd/user/atlas-core.service"

log() { echo "[install-atlas-systemd] $*"; }

log "1/4 Copiar systemd-user unit"
mkdir -p "$(dirname "$UNIT_DST")"
sed "s|/home/ronin/proyectos/atlas-core|$REPO_ROOT|g" \
    "$REPO_ROOT/scripts/atlas-core.service" > "$UNIT_DST"
echo "  ✓ $UNIT_DST"

log "2/4 Habilitar linger (Atlas sobrevive al logout)"
sudo loginctl enable-linger "$USER_NAME" 2>/dev/null || \
    log "   (sudo loginctl falló — habilita linger manualmente)"

log "3/4 daemon-reload + enable --now"
systemctl --user daemon-reload
systemctl --user enable --now atlas-core.service
sleep 8

log "4/4 Verificar"
echo "  active: $(systemctl --user is-active atlas-core.service)"
echo "  enabled: $(systemctl --user is-enabled atlas-core.service)"
echo ""
echo "  health:"
timeout 5 curl -s --max-time 4 http://localhost:7331/api/health 2>&1 | head -c 300 | python3 -c "
import sys, json
data = sys.stdin.read()
try:
    h = json.loads(data)
    print(f'    ✓ Atlas {h[\"version\"]} merkle={h[\"merkle_chain_ok\"]} hermes_mode={h[\"hermes_mode\"]} gate_d={h[\"gate_d_enabled\"]}')
except:
    print(f'    ⚠️  Atlas aún arrancando (json parcial). Re-prueba en 10s con:')
    print(f'         curl -s http://localhost:7331/api/health | python3 -m json.tool')
" 2>&1

echo ""
echo "Comandos útiles:"
echo "  systemctl --user status atlas-core"
echo "  systemctl --user restart atlas-core"
echo "  journalctl --user -u atlas-core -f"
echo "  tail -f $REPO_ROOT/.atlas.log"
