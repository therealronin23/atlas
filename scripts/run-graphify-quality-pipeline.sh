#!/usr/bin/env bash
set -euo pipefail
umask 077

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

# OpenAI SDKs standardized on OPENAI_BASE_URL. Preserve compatibility with
# older local Graphify setups without letting a legacy value silently fall
# back to the public OpenAI endpoint.
if [ -z "${OPENAI_BASE_URL:-}" ] && [ -n "${OPENAI_API_BASE:-}" ]; then
  export OPENAI_BASE_URL="$OPENAI_API_BASE"
fi

usage() {
  cat <<'EOF' >&2
Usage: ./scripts/run-graphify-quality-pipeline.sh [options]

Options:
  --backend BACKEND      Graphify backend to use (default: auto-detected)
  --model MODEL          LLM model override
  --path PATH            Compatibility flag; only repository root `.` is supported
  --token-budget N       Semantic extraction token budget (default: 4000)
  --max-workers N        Graphify workers (default: 1)
  --max-concurrency N    Graphify extraction concurrency (default: 1)
  --api-timeout S        Backend timeout in seconds (default: 600)
  --max-retries N        SDK retries per LLM request (default: 1)
  --strict               Fail if the quality thresholds are not met
  --min-nodes N          Minimum node count threshold for strict mode (default: 20)
  --max-invalid-json N   Maximum invalid-JSON count before strict mode fails (default: 10)
  --max-failed-chunks N  Maximum failed semantic chunks in strict mode (default: 0)
  --max-hollow-responses N
                         Maximum hollow LLM responses in strict mode (default: 0)
  --max-partial-results N
                         Maximum truncated partial results in strict mode (default: 0)
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
MAX_RETRIES="${GRAPHIFY_MAX_RETRIES:-1}"
STRICT=false
MIN_NODES="${GRAPHIFY_MIN_NODES:-20}"
MAX_INVALID_JSON="${GRAPHIFY_MAX_INVALID_JSON:-10}"
MAX_FAILED_CHUNKS="${GRAPHIFY_MAX_FAILED_CHUNKS:-0}"
MAX_HOLLOW_RESPONSES="${GRAPHIFY_MAX_HOLLOW_RESPONSES:-0}"
MAX_PARTIAL_RESULTS="${GRAPHIFY_MAX_PARTIAL_RESULTS:-0}"
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
    --max-retries)
      MAX_RETRIES="${2:-$MAX_RETRIES}"
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
    --max-failed-chunks)
      MAX_FAILED_CHUNKS="${2:-$MAX_FAILED_CHUNKS}"
      shift 2
      ;;
    --max-hollow-responses)
      MAX_HOLLOW_RESPONSES="${2:-$MAX_HOLLOW_RESPONSES}"
      shift 2
      ;;
    --max-partial-results)
      MAX_PARTIAL_RESULTS="${2:-$MAX_PARTIAL_RESULTS}"
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

if [ "$TARGET_PATH" != "." ]; then
  echo "ERROR: the quality pipeline only supports --path .; non-root output is not wired to the canonical graphify-out artifacts." >&2
  exit 2
fi

for QUALITY_LIMIT in \
  "max-retries:$MAX_RETRIES" \
  "min-nodes:$MIN_NODES" \
  "max-invalid-json:$MAX_INVALID_JSON" \
  "max-failed-chunks:$MAX_FAILED_CHUNKS" \
  "max-hollow-responses:$MAX_HOLLOW_RESPONSES" \
  "max-partial-results:$MAX_PARTIAL_RESULTS"; do
  QUALITY_LIMIT_NAME="${QUALITY_LIMIT%%:*}"
  QUALITY_LIMIT_VALUE="${QUALITY_LIMIT#*:}"
  if [[ ! "$QUALITY_LIMIT_VALUE" =~ ^[0-9]+$ ]]; then
    echo "ERROR: --${QUALITY_LIMIT_NAME} must be a non-negative integer." >&2
    exit 2
  fi
done
for POSITIVE_CONTROL in \
  "token-budget:$TOKEN_BUDGET" \
  "max-workers:$MAX_WORKERS" \
  "max-concurrency:$MAX_CONCURRENCY" \
  "api-timeout:$API_TIMEOUT"; do
  POSITIVE_CONTROL_NAME="${POSITIVE_CONTROL%%:*}"
  POSITIVE_CONTROL_VALUE="${POSITIVE_CONTROL#*:}"
  if [[ ! "$POSITIVE_CONTROL_VALUE" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: --${POSITIVE_CONTROL_NAME} must be a positive integer." >&2
    exit 2
  fi
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
if [ "$BACKEND" = "openai" ] && [ -n "${NVIDIA_API_KEY:-}" ] && [ -z "${OPENAI_BASE_URL:-}" ]; then
  ROUTE_TO_NVIDIA=false
  if [ -z "${OPENAI_API_KEY:-}" ] || [ "${OPENAI_API_KEY:-}" = "${NVIDIA_API_KEY}" ]; then
    ROUTE_TO_NVIDIA=true
  fi
  case "${MODEL:-}" in
    meta/*|nvidia/*) ROUTE_TO_NVIDIA=true ;;
  esac
  if [ "$ROUTE_TO_NVIDIA" = true ]; then
    export OPENAI_API_KEY="${NVIDIA_API_KEY}"
    export OPENAI_BASE_URL="https://integrate.api.nvidia.com/v1"
    case "${MODEL:-}" in
      ""|gpt-*)
        MODEL="${GRAPHIFY_OPENAI_MODEL:-meta/llama-3.3-70b-instruct}"
        ;;
    esac
  fi
fi

if [ "$PRINT_PLAN" = true ]; then
  printf 'backend=%s\n' "${BACKEND:-auto}"
  printf 'model=%s\n' "${MODEL:-auto}"
  printf 'endpoint=%s\n' "${OPENAI_BASE_URL:-default}"
  printf 'max_retries=%s\n' "$MAX_RETRIES"
  printf 'max_failed_chunks=%s\n' "$MAX_FAILED_CHUNKS"
  printf 'max_hollow_responses=%s\n' "$MAX_HOLLOW_RESPONSES"
  printf 'max_partial_results=%s\n' "$MAX_PARTIAL_RESULTS"
  exit 0
fi

LOG_PATH="${GRAPHIFY_LOG_PATH:-graphify-out/logs/pipeline.log}"
QUALITY_REPORT_PATH="${GRAPHIFY_QUALITY_REPORT_PATH:-graphify-out/quality-report.json}"
mkdir -p graphify-out graphify-out/logs "$(dirname "$LOG_PATH")" "$(dirname "$QUALITY_REPORT_PATH")"
chmod 700 graphify-out/logs
for PRIVATE_ARTIFACT in "$LOG_PATH" "$QUALITY_REPORT_PATH"; do
  if [ -L "$PRIVATE_ARTIFACT" ] || { [ -e "$PRIVATE_ARTIFACT" ] && [ ! -f "$PRIVATE_ARTIFACT" ]; }; then
    echo "ERROR: refusing unsafe Graphify private artifact: $PRIVATE_ARTIFACT" >&2
    exit 73
  fi
  touch "$PRIVATE_ARTIFACT"
  chmod 600 "$PRIVATE_ARTIFACT"
done
python3 - "$QUALITY_REPORT_PATH" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY

export GRAPHIFY_MAX_OUTPUT_TOKENS="${GRAPHIFY_MAX_OUTPUT_TOKENS:-16384}"
export GRAPHIFY_LLM_TEMPERATURE="${GRAPHIFY_LLM_TEMPERATURE:-0}"
export GRAPHIFY_API_TIMEOUT="$API_TIMEOUT"

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
  --max-retries "$MAX_RETRIES"
)
if [ "$BACKEND_EXPLICIT" = true ]; then
  RAG_ARGS+=(--backend "$BACKEND")
fi
if [ "$MODEL_EXPLICIT" = true ]; then
  RAG_ARGS+=(--model "$MODEL")
fi

# Complete and validate content-addressed checkpoints before starting the
# publication transaction. The lower script owns backend auto-detection and
# routing, so resume cannot silently use a different provider. A failed resume
# exits before publication; already verified per-source checkpoints remain for
# the next invocation. The full run repeats this cheap cache check while
# holding the writer lock, closing source-drift races.
if [ "${GRAPHIFY_SKIP_SEMANTIC_RESUME:-0}" != "1" ]; then
  set +e
  python3 - "$LOG_PATH" \
    ./scripts/update-knowledge-graph-rag.sh --resume-only "${RAG_ARGS[@]}" <<'PY'
import os
import signal
import subprocess
import sys

log_path = sys.argv[1]
command = sys.argv[2:]
flags = os.O_WRONLY | os.O_APPEND | os.O_CLOEXEC
flags |= getattr(os, 'O_NOFOLLOW', 0)
try:
    log_fd = os.open(log_path, flags)
except OSError as exc:
    print(
        f"ERROR: could not open private Graphify log ({type(exc).__name__})",
        file=sys.stderr,
    )
    raise SystemExit(73) from None

with os.fdopen(log_fd, 'a', encoding='utf-8', errors='replace', buffering=1) as log:
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        log.write(
            f"[atlas resume] could not launch checkpoint phase: "
            f"{type(exc).__name__}\n"
        )
        raise SystemExit(69) from None
    try:
        raise SystemExit(process.wait())
    except KeyboardInterrupt:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        raise SystemExit(130) from None
PY
  RESUME_EXIT_CODE=$?
  set -e
  if [ "$RESUME_EXIT_CODE" -ne 0 ]; then
    python3 - "$QUALITY_REPORT_PATH" "$RESUME_EXIT_CODE" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "status": "semantic_resume_incomplete",
            "exit_code": int(sys.argv[2]),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "verified_checkpoints_preserved": True,
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY
    exit "$RESUME_EXIT_CODE"
  fi
fi

set +e
python3 - \
  "$LOG_PATH" \
  "$STRICT" \
  "$MAX_INVALID_JSON" \
  "$MAX_FAILED_CHUNKS" \
  "$MAX_HOLLOW_RESPONSES" \
  "$MAX_PARTIAL_RESULTS" \
  ./scripts/update-knowledge-graph-rag.sh "${RAG_ARGS[@]}" <<'PY'
import os
import signal
import subprocess
import sys
import threading

log_path = sys.argv[1]
strict = sys.argv[2].lower() == 'true'
limits = {
    'invalid_json_count': int(sys.argv[3]),
    'failed_chunk_count': int(sys.argv[4]),
    'hollow_response_count': int(sys.argv[5]),
    'partial_result_count': int(sys.argv[6]),
    'graph_validation_warning_count': 0,
}
command = sys.argv[7:]
counts = {name: 0 for name in limits}
terminated_for_quality = False
kill_timer: threading.Timer | None = None


def terminate_group(process: subprocess.Popen[str], sig: signal.Signals) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass


flags = os.O_WRONLY | os.O_APPEND | os.O_CLOEXEC
flags |= getattr(os, 'O_NOFOLLOW', 0)
try:
    log_fd = os.open(log_path, flags)
except OSError as exc:
    print(
        f"ERROR: could not open private Graphify log ({type(exc).__name__})",
        file=sys.stderr,
    )
    raise SystemExit(73) from None

with os.fdopen(log_fd, 'a', encoding='utf-8', errors='replace', buffering=1) as log:
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,
            start_new_session=True,
        )
    except OSError as exc:
        log.write(
            f"[atlas quality] could not launch GraphRAG: {type(exc).__name__}\n"
        )
        raise SystemExit(69) from None

    try:
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
            if 'invalid JSON' in line:
                counts['invalid_json_count'] += 1
            if 'failed:' in line:
                counts['failed_chunk_count'] += 1
            if (
                'hollow response' in line
                and 'adaptive retry can bisect' not in line
            ):
                counts['hollow_response_count'] += 1
            if 'partial result kept' in line:
                counts['partial_result_count'] += 1
            if '[graphify] Extraction warning' in line:
                counts['graph_validation_warning_count'] += 1
            exceeded = [
                name for name, count in counts.items() if count > limits[name]
            ]
            if strict and exceeded and not terminated_for_quality:
                terminated_for_quality = True
                summary = ', '.join(
                    f"{name}={counts[name]}>{limits[name]}" for name in exceeded
                )
                log.write(
                    f"[atlas quality] fail-fast: strict threshold impossible "
                    f"({summary})\n"
                )
                terminate_group(process, signal.SIGTERM)
                kill_timer = threading.Timer(
                    5.0, terminate_group, args=(process, signal.SIGKILL)
                )
                kill_timer.daemon = True
                kill_timer.start()
    except KeyboardInterrupt:
        terminate_group(process, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            terminate_group(process, signal.SIGKILL)
            process.wait()
        raise SystemExit(130) from None
    finally:
        if process.stdout is not None:
            process.stdout.close()

    return_code = process.wait()
    if kill_timer is not None:
        kill_timer.cancel()

if terminated_for_quality:
    raise SystemExit(78)
if return_code < 0:
    raise SystemExit(128 - return_code)
raise SystemExit(return_code)
PY
RAG_EXIT_CODE=$?
set -e

# Cache recovery has one transaction authority:
# update-knowledge-graph-rag.sh. This wrapper must never purge every new key --
# that was the restart-from-zero bug. It only removes entries proven unsafe by
# an explicit partial-source diagnostic or invalid confidence, and reports the
# lower layer's own rollback count.
SEMANTIC_CACHE_CLEANUP_COUNTS="$(python3 - "$LOG_PATH" <<'PY'
import json
import re
import sys
from pathlib import Path

root = Path.cwd().resolve()
text = Path(sys.argv[1]).read_text(encoding='utf-8', errors='replace')
marker = '--- run started '
start = text.rfind(marker)
current = text[start:] if start >= 0 else text
targets: set[Path] = set()
for raw in re.findall(
    r'\[graphify\] single-file chunk (.+?) truncated at [^\n]*partial result kept',
    current,
):
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if resolved.is_relative_to(root):
        targets.add(resolved)

cache_dir = root / 'graphify-out' / 'cache' / 'semantic'
if cache_dir.exists() and (cache_dir.is_symlink() or not cache_dir.is_dir()):
    raise SystemExit('unsafe semantic cache directory')
purged_partial = 0
purged_invalid = 0
allowed_confidence = {'AMBIGUOUS', 'EXTRACTED', 'INFERRED'}
if cache_dir.is_dir():
    for entry in cache_dir.glob('*.json'):
        if entry.is_symlink() or not entry.is_file():
            continue
        try:
            payload = json.loads(entry.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        invalid_confidence = any(
            isinstance(edge, dict)
            and edge.get('confidence', 'EXTRACTED') not in allowed_confidence
            for edge in (payload.get('edges') or [])
        )
        if invalid_confidence:
            entry.unlink()
            purged_invalid += 1
            continue
        sources: set[Path] = set()
        for key in ('nodes', 'edges', 'hyperedges'):
            values = payload.get(key) or []
            if not isinstance(values, list):
                continue
            for item in values:
                if not isinstance(item, dict):
                    continue
                raw_source = item.get('source_file')
                if not isinstance(raw_source, str) or not raw_source:
                    continue
                source = Path(raw_source)
                if not source.is_absolute():
                    source = root / source
                sources.add(source.resolve())
        if sources & targets:
            entry.unlink()
            purged_partial += 1

purged_inner = sum(
    int(value)
    for value in re.findall(
        r'\[atlas graphify\] purged (\d+) semantic cache entries created by failed run\.',
        current,
    )
)
print(purged_partial, purged_invalid, purged_inner)
PY
)" || {
  echo "ERROR: targeted semantic-cache cleanup failed." >&2
  RAG_EXIT_CODE=73
  SEMANTIC_CACHE_CLEANUP_COUNTS="0 0 0"
}
read -r PURGED_PARTIAL_CACHE_ENTRIES PURGED_INVALID_CACHE_ENTRIES \
  PURGED_FAILED_RUN_CACHE_ENTRIES <<< "$SEMANTIC_CACHE_CLEANUP_COUNTS"

if [ "$RAG_EXIT_CODE" -ne 0 ]; then
  python3 - \
    "$QUALITY_REPORT_PATH" \
    "$RAG_EXIT_CODE" \
    "$LOG_PATH" \
    "$PURGED_PARTIAL_CACHE_ENTRIES" \
    "$PURGED_INVALID_CACHE_ENTRIES" \
    "$PURGED_FAILED_RUN_CACHE_ENTRIES" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

log_text = Path(sys.argv[3]).read_text(encoding='utf-8', errors='replace')
run_start = log_text.rfind('--- run started ')
current_lines = (log_text[run_start:] if run_start >= 0 else log_text).splitlines()
counters = {
    'invalid_json_count': sum('invalid JSON' in line for line in current_lines),
    'failed_chunk_count': sum('failed:' in line for line in current_lines),
    'hollow_response_count': sum(
        'hollow response' in line and 'adaptive retry can bisect' not in line
        for line in current_lines
    ),
    'partial_result_count': sum(
        'partial result kept' in line for line in current_lines
    ),
    'graph_validation_warning_count': sum(
        '[graphify] Extraction warning' in line for line in current_lines
    ),
}
Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "status": (
                "quality_threshold_aborted"
                if int(sys.argv[2]) == 78
                else "pipeline_failed"
            ),
            "exit_code": int(sys.argv[2]),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "quality_counters": counters,
            "purged_partial_cache_entries": int(sys.argv[4]),
            "purged_invalid_cache_entries": int(sys.argv[5]),
            "purged_failed_run_cache_entries": int(sys.argv[6]),
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY
  exit "$RAG_EXIT_CODE"
fi

# The repeated-failure guard keeps current-run counters and emits review
# candidates. It never changes semantic coverage unless an operator invokes it
# separately with --apply-ignore.
python3 scripts/graphify_failure_guard.py "$LOG_PATH"

python3 - \
  "$QUALITY_REPORT_PATH" \
  "$LOG_PATH" \
  "$TARGET_PATH" \
  "${BACKEND:-auto}" \
  "${MODEL:-auto}" \
  "$PURGED_PARTIAL_CACHE_ENTRIES" \
  "$PURGED_INVALID_CACHE_ENTRIES" \
  "$PURGED_FAILED_RUN_CACHE_ENTRIES" <<'PY'
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

report_path = Path(sys.argv[1])
log_path = Path(sys.argv[2])
target_path = sys.argv[3]
backend = sys.argv[4]
model = sys.argv[5]
purged_partial_cache_entries = int(sys.argv[6])
purged_invalid_cache_entries = int(sys.argv[7])
purged_failed_run_cache_entries = int(sys.argv[8])

out_dir = Path('graphify-out')
graph_path = out_dir / 'graph.json'
manifest_path = out_dir / 'manifest.json'
cypher_path = out_dir / 'cypher.txt'
report_md_path = out_dir / 'GRAPH_REPORT.md'

nodes = []
edges = []
communities = []
legacy_file_ids = []
if graph_path.exists():
    try:
        graph = json.loads(graph_path.read_text(encoding='utf-8'))
    except Exception:
        graph = {}
    if isinstance(graph, dict):
        nodes = graph.get('nodes') or []
        edges = graph.get('edges') or graph.get('links') or []
        communities = graph.get('communities') or []

if isinstance(nodes, list):
    node_count = len(nodes)
else:
    node_count = 0
if isinstance(edges, list):
    edge_count = len(edges)
else:
    edge_count = 0
if isinstance(communities, (list, dict)) and communities:
    community_count = len(communities)
else:
    community_count = len(
        {
            node.get('community')
            for node in nodes
            if isinstance(node, dict) and node.get('community') is not None
        }
    )

# Graphify 0.9.11's read-only legacy-ID heuristic treats every AST node on L1
# as a file node. MCP config command/env nodes also live on L1, so that heuristic
# can emit a false pre-#1504 warning. Check only actual AST file anchors here:
# their label is the source filename (or their extractor metadata says file).
def normalize_graph_id(value):
    value = unicodedata.normalize('NFKC', value)
    value = re.sub(r'[^\w]+', '_', value, flags=re.UNICODE)
    value = re.sub(r'_+', '_', value)
    return value.strip('_').casefold()


graph_id_validation_status = 'checked'
root = Path.cwd().resolve()
file_anchors = []
for node in nodes:
    if not isinstance(node, dict) or node.get('_origin') != 'ast':
        continue
    if str(node.get('source_location') or '') != 'L1':
        continue
    source_file = node.get('source_file')
    node_id = node.get('id')
    if not isinstance(source_file, str) or not isinstance(node_id, str):
        continue
    source_path = Path(source_file)
    metadata = node.get('metadata')
    metadata = metadata if isinstance(metadata, dict) else {}
    is_file_anchor = (
        node.get('label') == source_path.name
        or metadata.get('kind') == 'file'
        or metadata.get('mcp_kind') == 'mcp_config_file'
    )
    if not is_file_anchor:
        continue
    if source_path.is_absolute():
        try:
            source_path = source_path.resolve().relative_to(root)
        except (OSError, ValueError):
            continue
    if not source_path.name:
        continue
    expected = normalize_graph_id(source_path.with_suffix('').as_posix())
    if expected:
        file_anchors.append((node_id, source_path.as_posix(), expected))

sources_by_expected = {}
for _, source_key, expected in file_anchors:
    sources_by_expected.setdefault(expected, set()).add(source_key)
naive_counts = {}
for expected, source_keys in sources_by_expected.items():
    for source_key in source_keys:
        naive = normalize_graph_id(f'{source_key}_{expected}')
        naive_counts[(expected, naive)] = naive_counts.get((expected, naive), 0) + 1
for node_id, source_key, expected in file_anchors:
    allowed = {expected}
    if len(sources_by_expected[expected]) > 1:
        naive = normalize_graph_id(f'{source_key}_{expected}')
        allowed.add(naive)
        if naive_counts[(expected, naive)] > 1:
            salt = hashlib.sha1(source_key.encode('utf-8')).hexdigest()[:6]
            allowed.add(normalize_graph_id(f'{source_key}_{expected}_{salt}'))
    if normalize_graph_id(node_id) not in allowed:
        legacy_file_ids.append(node_id)

log_text = log_path.read_text(encoding='utf-8', errors='replace') if log_path.exists() else ''
run_marker = '--- run started '
run_start = log_text.rfind(run_marker)
current_run_text = log_text[run_start:] if run_start >= 0 else log_text
current_run_lines = current_run_text.splitlines()
# Count affected log lines, not overlapping substrings. In particular,
# "returned invalid JSON" also contains "invalid JSON" and used to be counted
# twice. Historical runs remain available to the failure guard but cannot
# poison the quality verdict of this run.
invalid_json_count = sum('invalid JSON' in line for line in current_run_lines)
empty_hollow_count = sum(
    'hollow response' in line and 'adaptive retry can bisect' not in line
    for line in current_run_lines
)
failed_chunk_count = sum('failed:' in line for line in current_run_lines)
partial_result_count = sum(
    'partial result kept' in line for line in current_run_lines
)
graph_validation_warning_count = sum(
    '[graphify] Extraction warning' in line for line in current_run_lines
)
cluster_publish_verified = any(
    '[atlas graphify] validated clustered candidate published:' in line
    for line in current_run_lines
)
token_pattern = re.compile(
    r'\[graphify extract\] tokens:\s*([\d,]+)\s+in\s*/\s*([\d,]+)\s+out'
)
cache_pattern = re.compile(
    r'\[graphify extract\] semantic cache:\s*(\d+)\s+'
    r'(?:hit|cached)\s*/\s*(\d+)\s+(?:miss|re-extracted)'
)
input_tokens = 0
output_tokens = 0
semantic_cache_hits = 0
semantic_cache_misses = 0
semantic_cache_reported = False
for line in current_run_lines:
    token_match = token_pattern.search(line)
    if token_match:
        input_tokens = int(token_match.group(1).replace(',', ''))
        output_tokens = int(token_match.group(2).replace(',', ''))
    cache_match = cache_pattern.search(line)
    if cache_match:
        semantic_cache_hits = int(cache_match.group(1))
        semantic_cache_misses = int(cache_match.group(2))
        semantic_cache_reported = True

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
    'partial_result_count': partial_result_count,
    'purged_partial_cache_entries': purged_partial_cache_entries,
    'purged_failed_run_cache_entries': purged_failed_run_cache_entries,
    'graph_validation_warning_count': graph_validation_warning_count,
    'cluster_publish_verified': cluster_publish_verified,
    'legacy_file_id_count': len(legacy_file_ids),
    'graph_id_validation_status': graph_id_validation_status,
    'purged_invalid_cache_entries': purged_invalid_cache_entries,
    'input_tokens': input_tokens,
    'output_tokens': output_tokens,
    'total_tokens': input_tokens + output_tokens,
    'semantic_cache_hits': semantic_cache_hits,
    'semantic_cache_misses': semantic_cache_misses,
    'semantic_cache_provenance': (
        'mixed_or_unverified'
        if semantic_cache_hits
        else ('current_run_only' if semantic_cache_reported else 'not_reported')
    ),
    'generated_at': datetime.now(timezone.utc).isoformat(),
}
report_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(json.dumps(metrics, indent=2, sort_keys=True))
PY

TOKEN_TOTAL=$(python3 - "$QUALITY_REPORT_PATH" <<'PY'
import json
import sys
from pathlib import Path

metrics = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
print(int(metrics.get('total_tokens', 0)))
PY
)
TOKEN_LEDGER_PROVIDER=""
TOKEN_LEDGER_STATUS="no_usage_reported"
if [ "$TOKEN_TOTAL" -gt 0 ]; then
  case "$BACKEND" in
    claude) TOKEN_LEDGER_PROVIDER="anthropic" ;;
    gemini|ollama) TOKEN_LEDGER_PROVIDER="$BACKEND" ;;
    openai)
      case "${OPENAI_BASE_URL:-}" in
        https://integrate.api.nvidia.com/v1*) TOKEN_LEDGER_PROVIDER="nvidia" ;;
        https://api.groq.com/openai/v1*) TOKEN_LEDGER_PROVIDER="groq" ;;
        https://openrouter.ai/*) TOKEN_LEDGER_PROVIDER="openrouter" ;;
        ""|https://api.openai.com/*) TOKEN_LEDGER_PROVIDER="openai" ;;
      esac
      ;;
  esac
  if [ -z "$TOKEN_LEDGER_PROVIDER" ]; then
    TOKEN_LEDGER_STATUS="unresolved_provider"
    echo "WARNING: Graphify reported token usage but the billing provider could not be resolved; usage was not attributed." >&2
  elif [ ! -x scripts/token-tracker.sh ]; then
    TOKEN_LEDGER_STATUS="tracker_unavailable"
    echo "WARNING: Graphify reported token usage but token-tracker.sh is unavailable." >&2
  elif scripts/token-tracker.sh log "$TOKEN_LEDGER_PROVIDER" "$TOKEN_TOTAL" "${MODEL:-unknown}"; then
    TOKEN_LEDGER_STATUS="recorded"
  else
    TOKEN_LEDGER_STATUS="record_failed"
    echo "WARNING: Graphify token usage could not be appended to the local ledger." >&2
  fi
fi
python3 - \
  "$QUALITY_REPORT_PATH" \
  "$TOKEN_LEDGER_PROVIDER" \
  "$TOKEN_LEDGER_STATUS" \
  "$TOKEN_TOTAL" <<'PY'
import json
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
metrics = json.loads(report_path.read_text(encoding='utf-8'))
metrics['token_ledger'] = {
    'provider': sys.argv[2] or None,
    'status': sys.argv[3],
    'total_tokens': int(sys.argv[4]),
}
report_path.write_text(
    json.dumps(metrics, indent=2, sort_keys=True) + '\n', encoding='utf-8'
)
PY

python3 - \
  "$QUALITY_REPORT_PATH" \
  "$MIN_NODES" \
  "$MAX_INVALID_JSON" \
  "$MAX_FAILED_CHUNKS" \
  "$MAX_HOLLOW_RESPONSES" \
  "$MAX_PARTIAL_RESULTS" \
  "$STRICT" <<'PY'
import json
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
min_nodes = int(sys.argv[2])
max_invalid_json = int(sys.argv[3])
max_failed_chunks = int(sys.argv[4])
max_hollow_responses = int(sys.argv[5])
max_partial_results = int(sys.argv[6])
strict = sys.argv[7].lower() == 'true'

metrics = json.loads(report_path.read_text(encoding='utf-8'))
violations = []
if strict:
    if metrics.get('node_count', 0) < min_nodes:
        violations.append(
            f"node_count={metrics.get('node_count')} < min_nodes={min_nodes}"
        )
    if (
        metrics.get('node_count', 0) > 1
        and metrics.get('edge_count', 0) > 0
        and metrics.get('community_count', 0) < 1
    ):
        violations.append('community_count=0 for a non-empty connected graph')
    if metrics.get('invalid_json_count', 0) > max_invalid_json:
        violations.append(
            f"invalid_json_count={metrics.get('invalid_json_count')} > max_invalid_json={max_invalid_json}"
        )
    if metrics.get('failed_chunk_count', 0) > max_failed_chunks:
        violations.append(
            f"failed_chunk_count={metrics.get('failed_chunk_count')} > max_failed_chunks={max_failed_chunks}"
        )
    if metrics.get('hollow_response_count', 0) > max_hollow_responses:
        violations.append(
            f"hollow_response_count={metrics.get('hollow_response_count')} "
            f"> max_hollow_responses={max_hollow_responses}"
        )
    if metrics.get('partial_result_count', 0) > max_partial_results:
        violations.append(
            f"partial_result_count={metrics.get('partial_result_count')} "
            f"> max_partial_results={max_partial_results}"
        )
    if metrics.get('graph_validation_warning_count', 0) > 0:
        violations.append(
            "graph_validation_warning_count="
            f"{metrics.get('graph_validation_warning_count')} > 0"
        )
    if metrics.get('graph_id_validation_status') != 'checked':
        violations.append('graph_id_validation_status is not checked')
    if metrics.get('legacy_file_id_count', 0) > 0:
        violations.append(
            f"legacy_file_id_count={metrics.get('legacy_file_id_count')} > 0"
        )
metrics['strict'] = strict
metrics['quality_gate'] = (
    'failed' if violations else ('passed' if strict else 'not_requested')
)
metrics['status'] = (
    'quality_gate_failed'
    if violations
    else ('passed' if strict else 'completed')
)
metrics['quality_gate_violations'] = violations
report_path.write_text(
    json.dumps(metrics, indent=2, sort_keys=True) + '\n', encoding='utf-8'
)
if violations:
    raise SystemExit('Quality gate failed: ' + '; '.join(violations))
print('Quality gate passed')
PY

printf '\nQuality report: %s\n' "$QUALITY_REPORT_PATH"
