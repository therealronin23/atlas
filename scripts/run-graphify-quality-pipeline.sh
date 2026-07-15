#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
DOTENV_PATH="$ROOT_DIR/.env"
if [[ -f "$DOTENV_PATH" && "${ATLAS_SAFE_DOTENV_FILE:-}" != "$DOTENV_PATH" ]]; then
  export ATLAS_SAFE_DOTENV_FILE="$DOTENV_PATH"
  exec python3 "$ROOT_DIR/scripts/safe_dotenv.py" "$DOTENV_PATH" -- \
    bash "$(readlink -f "${BASH_SOURCE[0]}")" "$@"
fi

if [ ! -f ".venv/bin/activate" ]; then
  echo "ERROR: .venv not found. Activate the project virtualenv or create it first." >&2
  exit 1
fi

source .venv/bin/activate

usage() {
  cat <<'EOF' >&2
Usage: ./scripts/run-graphify-quality-pipeline.sh [options]

Options:
  --backend BACKEND      Graphify backend to use (default: auto-detected)
  --model MODEL          LLM model override
  --path PATH            Target path to build from (default: .)
  --token-budget N       Semantic extraction token budget (default: 4000)
  --max-workers N        Graphify workers (default: 1)
  --max-concurrency N    Graphify extraction concurrency (default: 1)
  --api-timeout S        Backend timeout in seconds (default: 600)
  --strict               Fail if the quality thresholds are not met
  --min-nodes N          Minimum node count threshold for strict mode (default: 20)
  --max-invalid-json N   Maximum invalid-JSON count before strict mode fails (default: 10)
  -h, --help             Show this help text
EOF
}

BACKEND="${GRAPHIFY_BACKEND:-}"
MODEL="${GRAPHIFY_MODEL:-}"
TARGET_PATH="${GRAPHIFY_TARGET_PATH:-.}"
TOKEN_BUDGET="${GRAPHIFY_TOKEN_BUDGET:-4000}"
MAX_WORKERS="${GRAPHIFY_MAX_WORKERS:-1}"
MAX_CONCURRENCY="${GRAPHIFY_MAX_CONCURRENCY:-1}"
API_TIMEOUT="${GRAPHIFY_API_TIMEOUT:-600}"
STRICT=false
MIN_NODES="${GRAPHIFY_MIN_NODES:-20}"
MAX_INVALID_JSON="${GRAPHIFY_MAX_INVALID_JSON:-10}"
PRINT_PLAN=false
# Bug 2 (2026-07-15): solo reenviamos --backend/--model a
# update-knowledge-graph-rag.sh cuando el USUARIO los dio explicitos por CLI
# -- no cuando vienen de GRAPHIFY_BACKEND/GRAPHIFY_MODEL (esos los lee
# tambien update-knowledge-graph-rag.sh por su cuenta, unica fuente de verdad
# para la autodeteccion de backend).
BACKEND_EXPLICIT=false
MODEL_EXPLICIT=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --backend)
      BACKEND="${2:-}"
      BACKEND_EXPLICIT=true
      shift 2
      ;;
    --model)
      MODEL="${2:-}"
      MODEL_EXPLICIT=true
      shift 2
      ;;
    --path)
      TARGET_PATH="${2:-.}"
      shift 2
      ;;
    --token-budget)
      TOKEN_BUDGET="${2:-$TOKEN_BUDGET}"
      shift 2
      ;;
    --max-workers)
      MAX_WORKERS="${2:-$MAX_WORKERS}"
      shift 2
      ;;
    --max-concurrency)
      MAX_CONCURRENCY="${2:-$MAX_CONCURRENCY}"
      shift 2
      ;;
    --api-timeout)
      API_TIMEOUT="${2:-$API_TIMEOUT}"
      shift 2
      ;;
    --strict)
      STRICT=true
      shift
      ;;
    --min-nodes)
      MIN_NODES="${2:-$MIN_NODES}"
      shift 2
      ;;
    --max-invalid-json)
      MAX_INVALID_JSON="${2:-$MAX_INVALID_JSON}"
      shift 2
      ;;
    --print-plan)
      PRINT_PLAN=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

# Bug 2 (2026-07-15): la cascada de autodeteccion propia de este script se
# ELIMINO -- duplicaba (y podia discrepar de) la de
# update-knowledge-graph-rag.sh, que es ahora la unica fuente de verdad para
# "que backend/modelo usar cuando no se dan explicitos". Este script solo
# resuelve el remapeo RESIDUAL: si el usuario fuerza --backend openai sin
# OPENAI_API_KEY pero con NVIDIA_API_KEY, redirige el endpoint Y fuerza el
# modelo lejos de cualquier nombre gpt-* (el bug original: el endpoint se
# redirigia a NVIDIA pero el modelo se quedaba en gpt-4o-mini si venia
# preseteado -> NVIDIA lo rechaza -> fallo perpetuo).
if [ "$BACKEND" = "openai" ] && [ -z "${OPENAI_API_KEY:-}" ] && [ -n "${NVIDIA_API_KEY:-}" ]; then
  export OPENAI_API_KEY="${NVIDIA_API_KEY}"
  export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://integrate.api.nvidia.com/v1}"
  case "${MODEL:-}" in
    ""|gpt-*)
      MODEL="${GRAPHIFY_OPENAI_MODEL:-meta/llama-3.3-70b-instruct}"
      ;;
  esac
fi

if [ "$PRINT_PLAN" = true ]; then
  printf 'backend=%s\n' "${BACKEND:-auto}"
  printf 'model=%s\n' "${MODEL:-auto}"
  printf 'endpoint=%s\n' "${OPENAI_BASE_URL:-default}"
  exit 0
fi

mkdir -p graphify-out graphify-out/logs
LOG_PATH="${GRAPHIFY_LOG_PATH:-graphify-out/logs/pipeline.log}"
QUALITY_REPORT_PATH="${GRAPHIFY_QUALITY_REPORT_PATH:-graphify-out/quality-report.json}"

export GRAPHIFY_MAX_OUTPUT_TOKENS="${GRAPHIFY_MAX_OUTPUT_TOKENS:-4096}"
export GRAPHIFY_LLM_TEMPERATURE="${GRAPHIFY_LLM_TEMPERATURE:-0}"
export GRAPHIFY_API_TIMEOUT="${GRAPHIFY_API_TIMEOUT:-$API_TIMEOUT}"

printf 'Running Graphify quality pipeline with backend=%s model=%s target=%s\n' "${BACKEND:-auto}" "${MODEL:-auto}" "$TARGET_PATH"

# Bug 6 (2026-07-15): el log ya no se trunca en cada run (>) -- se preserva
# el historial acumulado (>>) para que graphify_failure_guard.py pueda ver
# fallos repetidos entre corridas. La cabecera marca donde empieza CADA
# corrida (failure_guard solo escanea desde el ultimo marcador).
echo "--- run started $(date -u +%FT%TZ) backend=${BACKEND:-auto} model=${MODEL:-auto} ---" >> "$LOG_PATH"

RAG_ARGS=(
  --max-concurrency "$MAX_CONCURRENCY"
  --max-workers "$MAX_WORKERS"
  --token-budget "$TOKEN_BUDGET"
  --api-timeout "$API_TIMEOUT"
)
if [ "$BACKEND_EXPLICIT" = true ]; then
  RAG_ARGS+=(--backend "$BACKEND")
fi
if [ "$MODEL_EXPLICIT" = true ]; then
  RAG_ARGS+=(--model "$MODEL")
fi

./scripts/update-knowledge-graph-rag.sh "${RAG_ARGS[@]}" >> "$LOG_PATH" 2>&1

# Bug 4 (2026-07-15): guard de fallos repetidos -- cuenta "truncated at
# max_completion_tokens" / "LLM returned invalid JSON" por fichero en esta
# corrida y, al tercer fallo acumulado del mismo fichero, lo anade a
# .graphifyignore para que deje de intentarse.
python3 scripts/graphify_failure_guard.py "$LOG_PATH"

python3 - "$QUALITY_REPORT_PATH" "$LOG_PATH" "$TARGET_PATH" "${BACKEND:-auto}" "${MODEL:-auto}" <<'PY'
import json
import os
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
log_path = Path(sys.argv[2])
target_path = sys.argv[3]
backend = sys.argv[4]
model = sys.argv[5]

out_dir = Path('graphify-out')
graph_path = out_dir / 'graph.json'
manifest_path = out_dir / 'manifest.json'
cypher_path = out_dir / 'cypher.txt'
report_md_path = out_dir / 'GRAPH_REPORT.md'

nodes = []
edges = []
communities = []
if graph_path.exists():
    try:
        graph = json.loads(graph_path.read_text(encoding='utf-8'))
    except Exception:
        graph = {}
    if isinstance(graph, dict):
        nodes = graph.get('nodes') or []
        edges = graph.get('edges') or []
        communities = graph.get('communities') or []

if isinstance(nodes, list):
    node_count = len(nodes)
else:
    node_count = 0
if isinstance(edges, list):
    edge_count = len(edges)
else:
    edge_count = 0
if isinstance(communities, list):
    community_count = len(communities)
else:
    community_count = 0

log_text = log_path.read_text(encoding='utf-8', errors='replace') if log_path.exists() else ''
invalid_json_count = log_text.count('invalid JSON') + log_text.count('returned invalid JSON')
empty_hollow_count = log_text.count('hollow response')
failed_chunk_count = log_text.count('failed:')

metrics = {
    'target_path': target_path,
    'backend': backend,
    'model': model,
    'node_count': node_count,
    'edge_count': edge_count,
    'community_count': community_count,
    'cypher_file_exists': cypher_path.exists(),
    'graph_report_exists': report_md_path.exists(),
    'invalid_json_count': invalid_json_count,
    'hollow_response_count': empty_hollow_count,
    'failed_chunk_count': failed_chunk_count,
    'generated_at': int(Path('/proc/self').stat().st_mtime) if Path('/proc/self').exists() else 0,
}
report_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(json.dumps(metrics, indent=2, sort_keys=True))
PY

python3 - "$QUALITY_REPORT_PATH" "$MIN_NODES" "$MAX_INVALID_JSON" "$STRICT" <<'PY'
import json
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
min_nodes = int(sys.argv[2])
max_invalid_json = int(sys.argv[3])
strict = sys.argv[4].lower() == 'true'

metrics = json.loads(report_path.read_text(encoding='utf-8'))
if strict:
    if metrics.get('node_count', 0) < min_nodes:
        raise SystemExit(f"Quality gate failed: node_count={metrics.get('node_count')} < min_nodes={min_nodes}")
    if metrics.get('invalid_json_count', 0) > max_invalid_json:
        raise SystemExit(
            f"Quality gate failed: invalid_json_count={metrics.get('invalid_json_count')} > max_invalid_json={max_invalid_json}"
        )
print('Quality gate passed')
PY

printf '\nQuality report: %s\n' "$QUALITY_REPORT_PATH"
