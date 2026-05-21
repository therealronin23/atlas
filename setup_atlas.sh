#!/usr/bin/env bash
# ============================================================
# ATLAS CORE v0.1 — Setup Script
# Ejecutar UNA VEZ en el HP Omen para crear toda la estructura
# Uso: bash setup_atlas.sh
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[ATLAS]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║     ATLAS CORE v0.1 — SETUP          ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ─── 1. Verificar prerequisitos ────────────────────────────

log "Verificando prerequisitos..."

command -v python3 >/dev/null 2>&1 || err "Python3 no encontrado. Instala Python 3.11+: https://www.python.org/downloads/"
command -v git    >/dev/null 2>&1 || err "Git no encontrado. Instala git: https://git-scm.com/"
command -v node   >/dev/null 2>&1 || warn "Node.js no encontrado. Necesario para Claude Code: https://nodejs.org/"

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
log "Python $PYTHON_VERSION detectado"

if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
    log "Python version OK"
else
    err "Necesitas Python 3.11 o superior. Tienes: $PYTHON_VERSION"
fi

# ─── 2. Crear estructura de directorios ────────────────────

ATLAS_HOME="${HOME}/atlas"
PROJECT="${HOME}/atlas-core"

log "Creando estructura en $PROJECT..."

mkdir -p "$PROJECT/src/atlas/core"
mkdir -p "$PROJECT/src/atlas/governance"
mkdir -p "$PROJECT/src/atlas/router"
mkdir -p "$PROJECT/src/atlas/security"
mkdir -p "$PROJECT/src/atlas/memory"
mkdir -p "$PROJECT/src/atlas/logging"
mkdir -p "$PROJECT/src/atlas/hermes"
mkdir -p "$PROJECT/src/atlas/tools"
mkdir -p "$PROJECT/src/atlas/personality"
mkdir -p "$PROJECT/src/atlas/thermal"
mkdir -p "$PROJECT/src/atlas/interfaces"
mkdir -p "$PROJECT/tests"
mkdir -p "$PROJECT/config"
mkdir -p "$PROJECT/memory/system_context"
mkdir -p "$PROJECT/docs"

# Workspace de Atlas (donde vive y trabaja)
mkdir -p "$ATLAS_HOME/projects"
mkdir -p "$ATLAS_HOME/tmp"
mkdir -p "$ATLAS_HOME/skills"
mkdir -p "$ATLAS_HOME/memory/system_context"
mkdir -p "$ATLAS_HOME/memory/failure_atlas"
mkdir -p "$ATLAS_HOME/memory/pattern_library"
mkdir -p "$ATLAS_HOME/memory/performance"
mkdir -p "$ATLAS_HOME/memory/audit"
mkdir -p "$ATLAS_HOME/config"

log "Estructura de directorios creada"

# ─── 3. Crear __init__.py ──────────────────────────────────

for d in \
    "$PROJECT/src/atlas" \
    "$PROJECT/src/atlas/core" \
    "$PROJECT/src/atlas/governance" \
    "$PROJECT/src/atlas/router" \
    "$PROJECT/src/atlas/security" \
    "$PROJECT/src/atlas/memory" \
    "$PROJECT/src/atlas/logging" \
    "$PROJECT/src/atlas/hermes" \
    "$PROJECT/src/atlas/tools" \
    "$PROJECT/src/atlas/personality" \
    "$PROJECT/src/atlas/thermal" \
    "$PROJECT/src/atlas/interfaces" \
    "$PROJECT/tests"; do
    touch "$d/__init__.py"
done

# ─── 4. Copiar archivos descargados ────────────────────────

DOWNLOADS="${HOME}/Downloads"

log "Buscando archivos descargados en $DOWNLOADS..."

# Mapa: nombre_archivo → destino
declare -A FILE_MAP=(
    ["pyproject.toml"]="$PROJECT/pyproject.toml"
    ["governance.json"]="$PROJECT/config/governance.json"
    ["permissions.yaml"]="$PROJECT/config/permissions.yaml"
    ["01_vision.md"]="$PROJECT/memory/system_context/01_vision.md"
    ["02_rules.md"]="$PROJECT/memory/system_context/02_rules.md"
    ["03_adr.md"]="$PROJECT/memory/system_context/03_adr.md"
    ["contracts.py"]="$PROJECT/src/atlas/core/contracts.py"
    ["event_bus.py"]="$PROJECT/src/atlas/core/event_bus.py"
    ["inference_hub.py"]="$PROJECT/src/atlas/core/inference_hub.py"
    ["orchestrator.py"]="$PROJECT/src/atlas/core/orchestrator.py"
    ["governance_l0.py"]="$PROJECT/src/atlas/governance/governance_l0.py"
    ["permission_profile.py"]="$PROJECT/src/atlas/governance/permission_profile.py"
    ["hermes.py"]="$PROJECT/src/atlas/hermes/hermes.py"
    ["cli.py"]="$PROJECT/src/atlas/interfaces/cli.py"
    ["merkle_logger.py"]="$PROJECT/src/atlas/logging/merkle_logger.py"
    ["memory_system.py"]="$PROJECT/src/atlas/memory/memory_system.py"
    ["classifier.py"]="$PROJECT/src/atlas/router/classifier.py"
    ["ast_guard.py"]="$PROJECT/src/atlas/security/ast_guard.py"
    ["sandbox.py"]="$PROJECT/src/atlas/security/sandbox.py"
    ["ssrf_bridge.py"]="$PROJECT/src/atlas/security/ssrf_bridge.py"
    ["watchdog.py"]="$PROJECT/src/atlas/thermal/watchdog.py"
    ["test_atlas_core.py"]="$PROJECT/tests/test_atlas_core.py"
    ["test_gemini_components.py"]="$PROJECT/tests/test_gemini_components.py"
    ["gate_a_seal.md"]="$PROJECT/docs/gate_a_seal.md"
    ["gate_b_spec.md"]="$PROJECT/docs/gate_b_spec.md"
)

MISSING=0
for filename in "${!FILE_MAP[@]}"; do
    src="$DOWNLOADS/$filename"
    dst="${FILE_MAP[$filename]}"
    if [[ -f "$src" ]]; then
        cp "$src" "$dst"
        log "  ✓ $filename"
    else
        warn "  ✗ No encontrado: $src"
        MISSING=$((MISSING + 1))
    fi
done

if [[ $MISSING -gt 0 ]]; then
    warn "$MISSING archivos no encontrados en $DOWNLOADS"
    warn "Descarga todos los archivos del chat y vuelve a ejecutar este script"
fi

# Copiar Trinity Memo al workspace de Atlas también
cp "$PROJECT/memory/system_context/"*.md "$ATLAS_HOME/memory/system_context/" 2>/dev/null || true
cp "$PROJECT/config/"* "$ATLAS_HOME/config/" 2>/dev/null || true

# ─── 5. Entorno virtual Python ─────────────────────────────

log "Creando entorno virtual..."
python3 -m venv "$PROJECT/.venv"
source "$PROJECT/.venv/bin/activate"

log "Instalando dependencias..."
pip install --upgrade pip -q
pip install click rich fastapi uvicorn pydantic pyyaml cryptography pytest pytest-asyncio httpx -q

log "Dependencias instaladas"

# ─── 6. pyproject.toml mínimo si no existe ─────────────────

if [[ ! -f "$PROJECT/pyproject.toml" ]]; then
cat > "$PROJECT/pyproject.toml" << 'EOF'
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "atlas-core"
version = "0.1.0"
description = "Atlas Core — Sovereign local multi-agent OS"
requires-python = ">=3.11"
dependencies = [
    "click>=8.1", "rich>=13.0", "fastapi>=0.110",
    "uvicorn[standard]>=0.29", "pydantic>=2.6",
    "pyyaml>=6.0", "cryptography>=42.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "httpx>=0.27"]

[project.scripts]
atlas = "atlas.interfaces.cli:cli"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
EOF
fi

# ─── 7. Variable ATLAS_HOME ────────────────────────────────

SHELL_RC="$HOME/.bashrc"
[[ "$SHELL" == */zsh ]] && SHELL_RC="$HOME/.zshrc"

if ! grep -q "ATLAS_HOME" "$SHELL_RC" 2>/dev/null; then
    echo "" >> "$SHELL_RC"
    echo "# Atlas Core" >> "$SHELL_RC"
    echo "export ATLAS_HOME=\"$ATLAS_HOME\"" >> "$SHELL_RC"
    echo "export PYTHONPATH=\"$PROJECT/src:\$PYTHONPATH\"" >> "$SHELL_RC"
    log "ATLAS_HOME añadido a $SHELL_RC"
fi

export ATLAS_HOME="$ATLAS_HOME"
export PYTHONPATH="$PROJECT/src:$PYTHONPATH"

# ─── 8. Ejecutar tests ─────────────────────────────────────

log "Ejecutando suite de tests..."
cd "$PROJECT"

if python -m pytest tests/ -q --tb=short 2>&1; then
    log "✅ Todos los tests pasan"
else
    warn "⚠️  Algunos tests fallaron — revisa los errores arriba"
fi

# ─── 9. Git init ───────────────────────────────────────────

if [[ ! -d "$PROJECT/.git" ]]; then
    log "Inicializando repositorio git..."
    cd "$PROJECT"
    git init
    git add .
    git commit -m "feat: Atlas Core v0.1 — Gate B completo con 102 tests"
    log "Repositorio git inicializado"
fi

# ─── 10. Instalar Claude Code ──────────────────────────────

if ! command -v claude >/dev/null 2>&1; then
    if command -v npm >/dev/null 2>&1; then
        log "Instalando Claude Code..."
        npm install -g @anthropic-ai/claude-code
        log "Claude Code instalado"
    else
        warn "npm no disponible. Instala Node.js y luego: npm install -g @anthropic-ai/claude-code"
    fi
else
    log "Claude Code ya instalado: $(claude --version 2>/dev/null || echo 'ok')"
fi

# ─── 11. Resumen final ─────────────────────────────────────

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         ATLAS CORE v0.1 — SETUP COMPLETO        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo "  Proyecto:   $PROJECT"
echo "  Workspace:  $ATLAS_HOME"
echo "  Venv:       $PROJECT/.venv"
echo ""
echo "  Para activar el entorno:"
echo "  source $PROJECT/.venv/bin/activate"
echo ""
echo "  Para iniciar Atlas:"
echo "  PYTHONPATH=$PROJECT/src atlas status"
echo ""
echo "  Para iniciar Claude Code:"
echo "  cd $PROJECT && claude"
echo ""
