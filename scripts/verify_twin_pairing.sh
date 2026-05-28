#!/usr/bin/env bash
# ============================================================================
# verify_twin_pairing.sh — Comprueba el estado de la conexión Atlas ↔ Hermes.
#
# Ejecutar desde el laptop (donde vive Atlas Core):
#   bash scripts/verify_twin_pairing.sh
#
# Comprueba 6 cosas en orden:
#   1. Tailscale up + VPS reachable
#   2. Atlas Core local arranca y expone /api/health
#   3. Hermes-Agent VPS está active (systemctl --user)
#   4. Ollama VPS responde + listo (modelo cargado)
#   5. Hermes-Agent puede ALCANZAR Atlas (tool atlas_twin)
#   6. SOUL.md y config.yaml están donde deben + son legibles por Hermes
# ============================================================================
set -uo pipefail   # NOT -e: queremos seguir aunque algo falle

VPS_HOST="${VPS_HOST:-100.108.132.116}"
VPS_HOST_PUB="${VPS_HOST_PUB:-178.105.216.187}"
ATLAS_DASHBOARD_URL="${ATLAS_DASHBOARD_URL:-http://100.85.236.58:7331}"
HERMES_HOME=/root/.hermes

pass() { echo "  ✅ $*"; }
fail() { echo "  ❌ $*"; }
warn() { echo "  ⚠️  $*"; }

# ---------------------------------------------------------------------------
echo "── 1. Tailscale ──"
if tailscale status 2>&1 | grep -q hermes-vps; then
    pass "Tailscale mesh activa (hermes-vps visible)"
else
    fail "hermes-vps no en mesh (¿tailscale down?)"
fi
if timeout 3 ping -c 1 -W 2 "${VPS_HOST}" >/dev/null 2>&1; then
    pass "VPS responde por Tailscale ($VPS_HOST)"
else
    fail "VPS no responde por Tailscale"
fi

# ---------------------------------------------------------------------------
echo ""
echo "── 2. Atlas Core local (laptop) ──"
ATLAS_HEALTH=$(curl -s --max-time 3 "${ATLAS_DASHBOARD_URL}/api/health" 2>/dev/null || echo "")
if [[ -n "$ATLAS_HEALTH" ]]; then
    pass "Atlas dashboard /api/health responde"
    echo "$ATLAS_HEALTH" | python3 -c "import sys,json; h=json.load(sys.stdin); [print(f'     {k}: {h[k]}') for k in ('version','merkle_chain_ok','telegram_running','hermes_reachable')] " 2>/dev/null || true
else
    warn "Atlas no está corriendo en :7331. Para arrancarlo:"
    echo "       cd ~/proyectos/atlas-core && set -a; source .env; set +a; nohup .venv/bin/atlas serve > /tmp/atlas.log 2>&1 &"
fi

# ---------------------------------------------------------------------------
echo ""
echo "── 3. Hermes-Agent en VPS ──"
HERMES_STATE=$(ssh -o ConnectTimeout=5 root@${VPS_HOST_PUB} \
    'export XDG_RUNTIME_DIR=/run/user/0; systemctl --user is-active hermes-gateway.service' 2>&1 | tail -1)
if [[ "$HERMES_STATE" == "active" ]]; then
    pass "hermes-gateway.service: active"
else
    fail "hermes-gateway.service: $HERMES_STATE"
fi

# ---------------------------------------------------------------------------
echo ""
echo "── 4. Ollama en VPS ──"
OLLAMA_LIST=$(ssh -o ConnectTimeout=5 root@${VPS_HOST_PUB} 'ollama list 2>&1' | tail -5)
if echo "$OLLAMA_LIST" | grep -qE "qwen|llama|phi"; then
    pass "Ollama tiene modelo cargado:"
    echo "$OLLAMA_LIST" | sed 's/^/     /'
else
    fail "Ollama sin modelo: $OLLAMA_LIST"
fi
OLLAMA_API=$(ssh -o ConnectTimeout=5 root@${VPS_HOST_PUB} \
    'curl -s --max-time 2 http://127.0.0.1:11434/api/version 2>&1' | head -1)
if echo "$OLLAMA_API" | grep -q version; then
    pass "Ollama API responde: $OLLAMA_API"
else
    fail "Ollama API no responde: $OLLAMA_API"
fi

# ---------------------------------------------------------------------------
echo ""
echo "── 5. ¿Hermes puede llegar a Atlas? (twin pairing reverso) ──"
HERMES_TO_ATLAS=$(ssh -o ConnectTimeout=5 root@${VPS_HOST_PUB} \
    "curl -s -o /dev/null -w '%{http_code}' --max-time 5 ${ATLAS_DASHBOARD_URL}/api/health 2>&1" | tail -1)
if [[ "$HERMES_TO_ATLAS" == "200" ]]; then
    pass "Hermes-VPS → Atlas-laptop /api/health = 200 (Tailscale OK)"
elif [[ "$HERMES_TO_ATLAS" == "000" ]]; then
    warn "Hermes-VPS NO alcanza Atlas-laptop. Causa probable: atlas serve no corriendo"
    echo "       Arranca atlas en el laptop primero (paso 2)"
else
    warn "Hermes-VPS → Atlas: HTTP $HERMES_TO_ATLAS"
fi

# ---------------------------------------------------------------------------
echo ""
echo "── 6. Identity / SOUL en VPS ──"
ssh -o ConnectTimeout=5 root@${VPS_HOST_PUB} '
ls -la /root/.hermes/SOUL.md /root/.hermes/config.yaml 2>&1 | head -3
echo "---"
echo "SOUL.md primeras 5 líneas:"
head -5 /root/.hermes/SOUL.md 2>&1
echo "---"
echo "Identity en config.yaml:"
grep -A4 "^identity:" /root/.hermes/config.yaml 2>&1
' 2>&1 | sed 's/^/  /'

# ---------------------------------------------------------------------------
echo ""
echo "============= RESUMEN ============="
echo "Ahora pregúntale al bot en Telegram (lenguaje natural):"
echo ""
echo "  ▶ 'usa el tool atlas_twin para consultar /api/health de Atlas'"
echo "    → Si responde con merkle_chain_ok, gate_d_enabled, etc → ✅ twin OK"
echo ""
echo "  ▶ 'quién eres? cuáles son tus 3 reglas inviolables?'"
echo "    → Si menciona 'Atlas twin' y Governance L0 → ✅ SOUL.md cargado"
echo "    → Si dice solo 'Nous Research bot' → ❌ Hermes ignora SOUL.md"
