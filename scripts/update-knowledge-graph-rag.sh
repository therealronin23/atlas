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

# Normalize the legacy OpenAI-compatible endpoint variable before backend
# routing. Otherwise a provider key can be sent to the SDK's default endpoint.
if [ -z "${OPENAI_BASE_URL:-}" ] && [ -n "${OPENAI_API_BASE:-}" ]; then
  export OPENAI_BASE_URL="$OPENAI_API_BASE"
fi

export PYTHONHASHSEED=0

VAULT_DIR="graphify-vault"
BACKEND="${GRAPHIFY_BACKEND:-}"
MODEL="${GRAPHIFY_MODEL:-}"
IMPORT_NEO4J=false
FORCE=false
CODE_ONLY=false
NO_CLUSTER=false
MAX_CONCURRENCY=1
TOKEN_BUDGET=4000
API_TIMEOUT="${GRAPHIFY_API_TIMEOUT:-600}"
MAX_WORKERS=1
MAX_RETRIES="${GRAPHIFY_MAX_RETRIES:-1}"

usage() {
  cat <<'EOF' >&2
Usage: ./scripts/update-knowledge-graph-rag.sh [options]

Options:
  --backend BACKEND         Graphify LLM backend (openai|ollama|claude|gemini|deepseek|kimi|claude-cli)
  --model MODEL             Override the backend model name
  --vault-dir DIR           Obsidian export directory (default: graphify-vault)
  --import-neo4j            After export, import graphify-out/cypher.txt into Neo4j
  --force                   Force Graphify to rewrite the graph even if the rebuild shrinks
  --code-only               Build only the code graph (no semantic extraction)
  --no-cluster              Skip community clustering/labeling
  --max-concurrency N       LLM concurrency for semantic extraction (default: 1)
  --max-workers N           Worker threads for Graphify extraction (default: 1)
  --token-budget N          Token budget for Graphify semantic extraction (default: 4000)
  --api-timeout S           HTTP timeout in seconds for the LLM backend (default: 600)
  --max-retries N           SDK retries per LLM request (default: 1; upstream default is 6)
  -h, --help                Show this help text

Environment:
  GRAPHIFY_BACKEND          fallback backend if --backend is not provided
  GRAPHIFY_MODEL            fallback model if --model is not provided
  OPENAI_BASE_URL           local OpenAI-compatible server URL for openai backend
  OLLAMA_BASE_URL           local Ollama URL for ollama backend
  ANTHROPIC_BASE_URL        local Anthropic-compatible server URL for claude backend
  GRAPHIFY_API_TIMEOUT      explicit Graphify LLM HTTP timeout (seconds)
  GRAPHIFY_MAX_RETRIES      fallback SDK retry count (default: 1)
  NEO4J_URI                bolt URI for Neo4j import (default: bolt://localhost:7687)
  NEO4J_USER               Neo4j username (default: neo4j)
  NEO4J_PASSWORD           Neo4j password (required for import)
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --backend)
      shift
      BACKEND="${1:-}"
      ;;
    --model)
      shift
      MODEL="${1:-}"
      ;;
    --vault-dir)
      shift
      VAULT_DIR="${1:-$VAULT_DIR}"
      ;;
    --import-neo4j)
      IMPORT_NEO4J=true
      ;;
    --force)
      FORCE=true
      ;;
    --code-only)
      CODE_ONLY=true
      ;;
    --no-cluster)
      NO_CLUSTER=true
      ;;
    --max-concurrency)
      shift
      MAX_CONCURRENCY="${1:-$MAX_CONCURRENCY}"
      ;;
    --max-workers)
      shift
      MAX_WORKERS="${1:-$MAX_WORKERS}"
      ;;
    --token-budget)
      shift
      TOKEN_BUDGET="${1:-$TOKEN_BUDGET}"
      ;;
    --api-timeout)
      shift
      API_TIMEOUT="${1:-$API_TIMEOUT}"
      ;;
    --max-retries)
      shift
      MAX_RETRIES="${1:-$MAX_RETRIES}"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
  shift
done

if ! command -v graphify >/dev/null 2>&1; then
  echo "ERROR: graphify is not installed in the active virtualenv." >&2
  exit 1
fi

GRAPHIFY_VERSION="$(graphify --version 2>&1 | awk 'NR == 1 {print $2}')"
if [ "$GRAPHIFY_VERSION" != "0.9.11" ]; then
  echo "ERROR: Graphify version mismatch (expected 0.9.11, got ${GRAPHIFY_VERSION:-unknown})." >&2
  exit 1
fi

if [ -z "$BACKEND" ] && [ "$CODE_ONLY" = false ]; then
  if [ -n "${NVIDIA_API_KEY:-}" ]; then
    BACKEND=openai
    export OPENAI_API_KEY="${OPENAI_API_KEY:-${NVIDIA_API_KEY}}"
    export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://integrate.api.nvidia.com/v1}"
    export GRAPHIFY_OPENAI_MODEL="${GRAPHIFY_OPENAI_MODEL:-${MODEL:-meta/llama-3.3-70b-instruct}}"
    MODEL="${GRAPHIFY_OPENAI_MODEL:-meta/llama-3.3-70b-instruct}"
  elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    BACKEND=claude
  elif [ -n "${OPENAI_API_KEY:-}" ]; then
    BACKEND=openai
  elif [ -n "${OLLAMA_BASE_URL:-}" ]; then
    BACKEND=ollama
  elif [ -n "${GEMINI_API_KEY:-}" ]; then
    BACKEND=gemini
  elif [ -n "${DEEPSEEK_API_KEY:-}" ]; then
    BACKEND=deepseek
  fi
fi

if [ "$BACKEND" = "openai" ] && [ -n "${NVIDIA_API_KEY:-}" ] && [ -z "${OPENAI_BASE_URL:-}" ] && [ "$CODE_ONLY" = false ]; then
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
    export GRAPHIFY_OPENAI_MODEL="${GRAPHIFY_OPENAI_MODEL:-${MODEL:-meta/llama-3.3-70b-instruct}}"
    MODEL="${GRAPHIFY_OPENAI_MODEL:-meta/llama-3.3-70b-instruct}"
  fi
fi

# Auto-detect a local Ollama service if one is running and no backend is configured.
if [ -z "$BACKEND" ] && [ "$CODE_ONLY" = false ]; then
  if command -v curl >/dev/null 2>&1 && curl -sSf --max-time 2 http://127.0.0.1:11434/v1/models >/dev/null 2>&1; then
    BACKEND=ollama
    export OLLAMA_BASE_URL="http://127.0.0.1:11434/v1"
  fi
fi

if [ "$CODE_ONLY" = false ] && [ -z "$BACKEND" ]; then
  echo "ERROR: No Graphify LLM backend configured." >&2
  echo "Set --backend or GRAPHIFY_BACKEND, or provide a supported env key such as OPENAI_API_KEY, OLLAMA_BASE_URL, ANTHROPIC_API_KEY, or GEMINI_API_KEY." >&2
  exit 1
fi

for POSITIVE_CONTROL in \
  "max-concurrency:$MAX_CONCURRENCY" \
  "max-workers:$MAX_WORKERS" \
  "token-budget:$TOKEN_BUDGET" \
  "api-timeout:$API_TIMEOUT"; do
  POSITIVE_CONTROL_NAME="${POSITIVE_CONTROL%%:*}"
  POSITIVE_CONTROL_VALUE="${POSITIVE_CONTROL#*:}"
  if [[ ! "$POSITIVE_CONTROL_VALUE" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: --${POSITIVE_CONTROL_NAME} must be a positive integer." >&2
    exit 2
  fi
done

if [ "$CODE_ONLY" = false ]; then
  if [[ ! "$MAX_RETRIES" =~ ^[0-9]+$ ]]; then
    echo "ERROR: --max-retries must be a non-negative integer." >&2
    exit 2
  fi
  echo "Building semantic Graphify graph with backend=$BACKEND ${MODEL:+model=$MODEL}."
  export GRAPHIFY_MAX_OUTPUT_TOKENS="${GRAPHIFY_MAX_OUTPUT_TOKENS:-4096}"
  export GRAPHIFY_LLM_TEMPERATURE="${GRAPHIFY_LLM_TEMPERATURE:-0}"
  export GRAPHIFY_API_TIMEOUT="$API_TIMEOUT"
  # Graphify's OpenAI-compatible default is six retries. Combined with a
  # 900-second request timeout that permits a single chunk to block for about
  # 105 minutes. One retry keeps transient recovery without turning the
  # operator timeout into an unbounded-looking job; callers can still opt in.
  export GRAPHIFY_MAX_RETRIES="$MAX_RETRIES"
fi

echo "Writing Obsidian export to: $(pwd)/$VAULT_DIR"
mkdir -p "$VAULT_DIR"

if [ "$FORCE" = true ]; then
  export GRAPHIFY_FORCE=1
fi

SEMANTIC_LOCK_HELD=false
SEMANTIC_PUBLISH_PREPARED=false
GRAPHIFY_REBUILD_LOCK="graphify-out/.rebuild.lock"
GRAPHIFY_MANIFEST="graphify-out/manifest.json"
# Compatibility recovery for runs interrupted before the transactional
# publication directory was introduced.
GRAPHIFY_MANIFEST_BACKUP="graphify-out/.semantic-manifest.backup"
SEMANTIC_PUBLISH_BACKUP="graphify-out/.semantic-publish.backup"
SEMANTIC_PUBLISH_PREPARING="graphify-out/.semantic-publish.preparing"
SEMANTIC_CACHE_DIR="graphify-out/cache/semantic"
SEMANTIC_CACHE_BASELINE_NAME="semantic-cache-baseline.json"
SEMANTIC_PUBLISH_ARTIFACTS=(
  "graphify-out/manifest.json"
  "graphify-out/graph.json"
  "graphify-out/.graphify_analysis.json"
  "graphify-out/.graphify_labels.json"
  "graphify-out/.graphify_labels.json.sig"
  "graphify-out/.graphify_semantic_marker"
  "graphify-out/GRAPH_REPORT.md"
  "graphify-out/cypher.txt"
  "graphify-out/graph.graphml"
)

snapshot_semantic_cache() {
  python3 - "$1" "$SEMANTIC_CACHE_DIR" <<'PY'
import json
import re
import sys
from pathlib import Path

destination = Path(sys.argv[1])
cache_dir = Path(sys.argv[2])
if cache_dir.exists() and (cache_dir.is_symlink() or not cache_dir.is_dir()):
    raise SystemExit('ERROR: unsafe semantic cache directory.')
names = []
if cache_dir.is_dir():
    names = sorted(
        entry.name
        for entry in cache_dir.glob('*.json')
        if entry.is_file()
        and not entry.is_symlink()
        and re.fullmatch(r'[0-9a-f]{64}\.json', entry.name)
    )
destination.write_text(json.dumps(names) + '\n', encoding='utf-8')
PY
}

restore_semantic_cache() {
  python3 - \
    "$SEMANTIC_PUBLISH_BACKUP/$SEMANTIC_CACHE_BASELINE_NAME" \
    "$SEMANTIC_CACHE_DIR" <<'PY'
import json
import re
import sys
from pathlib import Path

baseline_path = Path(sys.argv[1])
cache_dir = Path(sys.argv[2])
if baseline_path.exists() and (
    baseline_path.is_symlink() or not baseline_path.is_file()
):
    raise SystemExit('ERROR: unsafe semantic cache baseline.')
if baseline_path.is_file():
    raw = json.loads(baseline_path.read_text(encoding='utf-8'))
    if not isinstance(raw, list) or not all(
        isinstance(name, str) and re.fullmatch(r'[0-9a-f]{64}\.json', name)
        for name in raw
    ):
        raise SystemExit('ERROR: invalid semantic cache baseline.')
    baseline = set(raw)
else:
    # Compatibility with a transaction left by the older implementation:
    # without a baseline, preserving a potentially partial checkpoint would
    # be a false hit. Re-extraction is expensive but safe.
    baseline = set()
if cache_dir.exists() and (cache_dir.is_symlink() or not cache_dir.is_dir()):
    raise SystemExit('ERROR: unsafe semantic cache directory.')
purged = 0
if cache_dir.is_dir():
    for entry in cache_dir.glob('*.json'):
        if entry.is_symlink() or not entry.is_file():
            continue
        if not re.fullmatch(r'[0-9a-f]{64}\.json', entry.name):
            continue
        if entry.name not in baseline:
            entry.unlink()
            purged += 1
print(purged)
PY
}

restore_semantic_publish() {
  if [ "$SEMANTIC_PUBLISH_PREPARED" = true ]; then
    local artifact backup_path purged_cache
    for artifact in "${SEMANTIC_PUBLISH_ARTIFACTS[@]}"; do
      rm -f -- "$artifact"
      backup_path="$SEMANTIC_PUBLISH_BACKUP/${artifact##*/}"
      if [ -f "$backup_path" ] && [ ! -L "$backup_path" ]; then
        cp -p -- "$backup_path" "$artifact"
      fi
    done
    if ! purged_cache="$(restore_semantic_cache)"; then
      echo "ERROR: semantic cache rollback failed; publication backup retained." >&2
      return 73
    fi
    if [ "$purged_cache" -gt 0 ]; then
      echo "[atlas graphify] purged $purged_cache semantic cache entries created by failed run."
    fi
    rm -rf -- "$SEMANTIC_PUBLISH_BACKUP"
    SEMANTIC_PUBLISH_PREPARED=false
  fi
}

prepare_semantic_publish() {
  local artifact
  if [ -e "$SEMANTIC_PUBLISH_BACKUP" ] || [ -L "$SEMANTIC_PUBLISH_BACKUP" ]; then
    if [ ! -d "$SEMANTIC_PUBLISH_BACKUP" ] || [ -L "$SEMANTIC_PUBLISH_BACKUP" ]; then
      echo "ERROR: unsafe stale semantic publication backup." >&2
      exit 73
    fi
    # We hold the writer lock, so an existing directory is an interrupted run.
    # Restore its last known-good artifacts before taking a new snapshot.
    SEMANTIC_PUBLISH_PREPARED=true
    restore_semantic_publish
  fi
  if [ -e "$SEMANTIC_PUBLISH_PREPARING" ] || [ -L "$SEMANTIC_PUBLISH_PREPARING" ]; then
    if [ ! -d "$SEMANTIC_PUBLISH_PREPARING" ] || [ -L "$SEMANTIC_PUBLISH_PREPARING" ]; then
      echo "ERROR: unsafe stale semantic publication staging directory." >&2
      exit 73
    fi
    rm -rf -- "$SEMANTIC_PUBLISH_PREPARING"
  fi
  for artifact in "${SEMANTIC_PUBLISH_ARTIFACTS[@]}"; do
    if [ -e "$artifact" ] || [ -L "$artifact" ]; then
      if [ ! -f "$artifact" ] || [ -L "$artifact" ]; then
        echo "ERROR: refusing unsafe Graphify publication artifact: $artifact" >&2
        exit 73
      fi
    fi
  done
  mkdir -m 700 "$SEMANTIC_PUBLISH_PREPARING"
  for artifact in "${SEMANTIC_PUBLISH_ARTIFACTS[@]}"; do
    if [ -f "$artifact" ]; then
      cp -p -- "$artifact" "$SEMANTIC_PUBLISH_PREPARING/${artifact##*/}"
    fi
  done
  snapshot_semantic_cache \
    "$SEMANTIC_PUBLISH_PREPARING/$SEMANTIC_CACHE_BASELINE_NAME"
  mv "$SEMANTIC_PUBLISH_PREPARING" "$SEMANTIC_PUBLISH_BACKUP"
  SEMANTIC_PUBLISH_PREPARED=true
}

commit_semantic_publish() {
  SEMANTIC_PUBLISH_PREPARED=false
  rm -rf -- "$SEMANTIC_PUBLISH_BACKUP"
}

release_semantic_lock() {
  if [ "$SEMANTIC_LOCK_HELD" = true ]; then
    # Keep the advisory lock pathname stable. Unlinking it before or after
    # unlocking is racy: a waiter can still reference the old inode while a
    # third process creates and locks a new inode at the same path. The file is
    # harmless when unlocked; ownership is determined by flock, not existence.
    flock -u 9 || true
    exec 9>&-
    SEMANTIC_LOCK_HELD=false
  fi
}

cleanup_semantic_run() {
  local status=$?
  trap - EXIT
  set +e
  rm -rf -- "$SEMANTIC_PUBLISH_PREPARING"
  restore_semantic_publish
  release_semantic_lock
  exit "$status"
}

acquire_semantic_lock() {
  if ! command -v flock >/dev/null 2>&1; then
    echo "ERROR: flock is required to serialize semantic Graphify rebuilds." >&2
    exit 69
  fi
  local timeout="${GRAPHIFY_LOCK_TIMEOUT:-900}"
  if [[ ! "$timeout" =~ ^[0-9]+$ ]]; then
    echo "ERROR: GRAPHIFY_LOCK_TIMEOUT must be a non-negative integer." >&2
    exit 2
  fi
  exec 9>>"$GRAPHIFY_REBUILD_LOCK"
  if ! flock -w "$timeout" 9; then
    exec 9>&-
    echo "ERROR: timed out waiting for the Graphify rebuild lock." >&2
    exit 75
  fi
  SEMANTIC_LOCK_HELD=true
  trap cleanup_semantic_run EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
}

semantic_source_snapshot() {
  python3 - "$SEMANTIC_PUBLISH_BACKUP/source-snapshot.json" "$1" <<'PY'
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from graphify.detect import detect

snapshot_path = Path(sys.argv[1])
mode = sys.argv[2]
root = Path('.').resolve()
detection = detect(root)
raw_paths = [
    value
    for values in (detection.get('files') or {}).values()
    for value in values
]
for control in (root / '.graphifyignore', root / '.gitignore'):
    if control.is_file() and not control.is_symlink():
        raw_paths.append(str(control))


def digest_path(raw: str) -> tuple[str, str]:
    path = Path(raw).resolve()
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        raise RuntimeError('detected semantic source escaped repository root') from None
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f'unsafe semantic source: {relative}')
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return relative, digest.hexdigest()


try:
    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 1)) as pool:
        current = dict(pool.map(digest_path, sorted(set(raw_paths))))
except (OSError, RuntimeError) as exc:
    print(f'ERROR: could not fingerprint semantic sources ({exc}).', file=sys.stderr)
    raise SystemExit(74) from None

if mode == 'write':
    temporary = snapshot_path.with_suffix('.tmp')
    temporary.write_text(
        json.dumps({'files': current}, sort_keys=True) + '\n', encoding='utf-8'
    )
    temporary.replace(snapshot_path)
    print(f'Semantic source snapshot: {len(current)} files.')
elif mode == 'verify':
    try:
        baseline_raw = json.loads(snapshot_path.read_text(encoding='utf-8'))
        baseline = baseline_raw['files']
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        print('ERROR: semantic source snapshot is missing or invalid.', file=sys.stderr)
        raise SystemExit(74) from None
    changed = sorted(
        path
        for path in set(baseline) | set(current)
        if baseline.get(path) != current.get(path)
    )
    if changed:
        print(
            f"ERROR: source tree drifted during semantic extraction "
            f"({len(changed)} path(s)); refusing publication. "
            f"Paths: {', '.join(changed[:8])}",
            file=sys.stderr,
        )
        raise SystemExit(75)
    print(f'Semantic source snapshot verified: {len(current)} files unchanged.')
else:
    print('ERROR: invalid semantic source snapshot mode.', file=sys.stderr)
    raise SystemExit(2)
PY
}

verify_semantic_candidate() {
  semantic_source_snapshot verify
  python3 - <<'PY'
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

root = Path('.').resolve()
graph_path = root / 'graphify-out' / 'graph.json'
try:
    graph = json.loads(graph_path.read_text(encoding='utf-8'))
except (OSError, json.JSONDecodeError):
    print('ERROR: semantic candidate graph is missing or invalid.', file=sys.stderr)
    raise SystemExit(74) from None
nodes = graph.get('nodes') if isinstance(graph, dict) else None
if not isinstance(nodes, list):
    print('ERROR: semantic candidate graph has no node list.', file=sys.stderr)
    raise SystemExit(74)


def normalize_id(value: str) -> str:
    value = unicodedata.normalize('NFKC', value)
    value = re.sub(r'[^\w]+', '_', value, flags=re.UNICODE)
    value = re.sub(r'_+', '_', value)
    return value.strip('_').casefold()


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
    if source_path.name:
        expected = normalize_id(source_path.with_suffix('').as_posix())
        if expected:
            file_anchors.append((node_id, source_path.as_posix(), expected))

sources_by_expected = {}
for _, source_key, expected in file_anchors:
    sources_by_expected.setdefault(expected, set()).add(source_key)
naive_counts = {}
for expected, source_keys in sources_by_expected.items():
    for source_key in source_keys:
        naive = normalize_id(f'{source_key}_{expected}')
        naive_counts[(expected, naive)] = naive_counts.get((expected, naive), 0) + 1

legacy_file_ids = []
for node_id, source_key, expected in file_anchors:
    allowed = {expected}
    if len(sources_by_expected[expected]) > 1:
        naive = normalize_id(f'{source_key}_{expected}')
        allowed.add(naive)
        if naive_counts[(expected, naive)] > 1:
            salt = hashlib.sha1(source_key.encode('utf-8')).hexdigest()[:6]
            allowed.add(normalize_id(f'{source_key}_{expected}_{salt}'))
    if normalize_id(node_id) not in allowed:
        legacy_file_ids.append(f'{source_key}: {node_id} -> {expected}')
if legacy_file_ids:
    print(
        f"ERROR: semantic candidate contains {len(legacy_file_ids)} real legacy "
        f"file ID(s): {'; '.join(legacy_file_ids[:8])}",
        file=sys.stderr,
    )
    raise SystemExit(74)
print('Semantic candidate source snapshot and file IDs verified.')
PY
}

publish_validated_cluster_candidate() {
  python3 - <<'PY'
import json
import sys
from pathlib import Path

from graphify.build import build_from_json
from graphify.export import to_json

out = Path('graphify-out')
graph_path = out / 'graph.json'
analysis_path = out / '.graphify_analysis.json'
labels_path = out / '.graphify_labels.json'
try:
    raw = json.loads(graph_path.read_text(encoding='utf-8'))
    analysis = json.loads(analysis_path.read_text(encoding='utf-8'))
except (OSError, json.JSONDecodeError):
    print('ERROR: clustered semantic candidate artifacts are invalid.', file=sys.stderr)
    raise SystemExit(74) from None
if not isinstance(raw, dict) or not isinstance(analysis, dict):
    print('ERROR: clustered semantic candidate artifacts are not objects.', file=sys.stderr)
    raise SystemExit(74)
communities_raw = analysis.get('communities')
if not isinstance(communities_raw, dict):
    print('ERROR: clustered semantic candidate has no communities.', file=sys.stderr)
    raise SystemExit(74)
try:
    communities = {
        int(key): [str(node_id) for node_id in value]
        for key, value in communities_raw.items()
        if isinstance(value, list)
    }
except (TypeError, ValueError):
    print('ERROR: clustered semantic communities are malformed.', file=sys.stderr)
    raise SystemExit(74) from None
graph = build_from_json(raw, directed=bool(raw.get('directed', False)))
members = {node_id for values in communities.values() for node_id in values}
if members != {str(node_id) for node_id in graph.nodes}:
    print('ERROR: clustered semantic communities do not cover the candidate graph.', file=sys.stderr)
    raise SystemExit(74)
labels = {}
if labels_path.is_file() and not labels_path.is_symlink():
    try:
        labels_raw = json.loads(labels_path.read_text(encoding='utf-8'))
        labels = {int(key): str(value) for key, value in labels_raw.items()}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        print('ERROR: clustered semantic labels are invalid.', file=sys.stderr)
        raise SystemExit(74) from None
if not to_json(
    graph,
    communities,
    str(graph_path),
    force=True,
    community_labels=labels or None,
):
    print('ERROR: validated clustered semantic graph was not published.', file=sys.stderr)
    raise SystemExit(74)
published = json.loads(graph_path.read_text(encoding='utf-8'))
published_nodes = published.get('nodes') if isinstance(published, dict) else None
if not isinstance(published_nodes, list) or (
    graph.number_of_nodes() and not all('community' in node for node in published_nodes)
):
    print('ERROR: published semantic graph lost community assignments.', file=sys.stderr)
    raise SystemExit(74)
print(
    f'[atlas graphify] validated clustered candidate published: '
    f'{graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges, '
    f'{len(communities)} communities.'
)
PY
}

if [ "$CODE_ONLY" = true ]; then
  if [ -f graphify-out/graph.json ]; then
    UPDATE_ARGS=()
    if [ "$FORCE" = true ]; then
      UPDATE_ARGS+=("--force")
    fi
    graphify update . "${UPDATE_ARGS[@]}"
  else
    graphify extract . --code-only --no-cluster
  fi
  if [ "$NO_CLUSTER" = false ]; then
    graphify cluster-only . --no-label --no-viz
  fi
else
  # `graphify extract` does not take the lock used by Graphify's post-commit
  # hook. Without this guard, a multi-hour semantic run can overwrite a newer
  # AST rebuild when it publishes last. Use the upstream lock pathname so the
  # hook queues its change set instead of racing us.
  acquire_semantic_lock
  # Graphify 0.9.11's incremental `extract` builds only the changed subset and
  # then publishes that subset as graph.json. A semantic refresh must instead
  # scan every live file while still reusing the content-addressed semantic
  # cache. Temporarily withdrawing the manifest selects the full-scan branch;
  # the old manifest is restored on any failed/interrupted extraction.
  if [ -e "$GRAPHIFY_MANIFEST_BACKUP" ] || [ -L "$GRAPHIFY_MANIFEST_BACKUP" ]; then
    if [ ! -e "$GRAPHIFY_MANIFEST" ] \
      && [ -f "$GRAPHIFY_MANIFEST_BACKUP" ] \
      && [ ! -L "$GRAPHIFY_MANIFEST_BACKUP" ]; then
      mv "$GRAPHIFY_MANIFEST_BACKUP" "$GRAPHIFY_MANIFEST"
    else
      echo "ERROR: ambiguous stale semantic manifest backup; refusing to rebuild." >&2
      exit 73
    fi
  fi
  prepare_semantic_publish
  rm -f "$GRAPHIFY_MANIFEST"
  semantic_source_snapshot write
  MODEL_ARGS=()
  if [ -n "$MODEL" ]; then
    MODEL_ARGS=("--model" "$MODEL")
  fi
  graphify extract . --backend "$BACKEND" "${MODEL_ARGS[@]}" --max-concurrency "$MAX_CONCURRENCY" --max-workers "$MAX_WORKERS" --token-budget "$TOKEN_BUDGET" --api-timeout "$API_TIMEOUT" --no-cluster
  if [ ! -f "$GRAPHIFY_MANIFEST" ] || [ -L "$GRAPHIFY_MANIFEST" ]; then
    echo "ERROR: full semantic extraction did not publish a safe manifest." >&2
    exit 74
  fi
  if [ "$NO_CLUSTER" = false ]; then
    # Graphify 0.9.11 does not expose token usage from community-name LLM
    # calls. Deterministic hub labels preserve topology and queryability while
    # keeping every paid semantic call measurable in the extraction stage.
    graphify cluster-only . --no-label --no-viz
  fi
  verify_semantic_candidate
  if [ "$NO_CLUSTER" = false ]; then
    # cluster-only ignores to_json(False) when its generic shrink guard rejects
    # legitimate dedup/isolated-node reduction, then prints a false success. A
    # full source snapshot and exact community coverage make this force-write
    # narrower and verifiable than disabling the guard globally.
    publish_validated_cluster_candidate
  fi
fi

graphify export neo4j
python3 scripts/graphify_obsidian_export.py \
  --graph graphify-out/graph.json \
  --output "$VAULT_DIR" \
  --replace-generated
if [ "$SEMANTIC_LOCK_HELD" = true ]; then
  commit_semantic_publish
  release_semantic_lock
  trap - EXIT INT TERM
fi

printf '\nDone.\n- Graph report: %s/GRAPH_REPORT.md\n- Obsidian vault: %s\n- Neo4j import: %s/cypher.txt\n' "$(pwd)/graphify-out" "$(pwd)/$VAULT_DIR" "$(pwd)/graphify-out"

if [ "$IMPORT_NEO4J" = true ]; then
  ./scripts/neo4j-import.sh
fi

if [ "$CODE_ONLY" = false ]; then
  printf '\nNOTE: Semantic extraction may use your LLM backend for docs and community labels.\nUse this only when you want a richer, GraphRAG-ready graph and have an available model.\nFor low-token maintenance, continue using ./scripts/update-knowledge-graph.sh.\n'
fi
