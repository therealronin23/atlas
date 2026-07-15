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
API_TIMEOUT=600
MAX_WORKERS=1

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
  -h, --help                Show this help text

Environment:
  GRAPHIFY_BACKEND          fallback backend if --backend is not provided
  GRAPHIFY_MODEL            fallback model if --model is not provided
  OPENAI_BASE_URL           local OpenAI-compatible server URL for openai backend
  OLLAMA_BASE_URL           local Ollama URL for ollama backend
  ANTHROPIC_BASE_URL        local Anthropic-compatible server URL for claude backend
  GRAPHIFY_API_TIMEOUT      explicit Graphify LLM HTTP timeout (seconds)
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

if [ "$BACKEND" = "openai" ] && [ -z "${OPENAI_API_KEY:-}" ] && [ -n "${NVIDIA_API_KEY:-}" ] && [ "$CODE_ONLY" = false ]; then
  export OPENAI_API_KEY="${NVIDIA_API_KEY}"
  export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://integrate.api.nvidia.com/v1}"
  export GRAPHIFY_OPENAI_MODEL="${GRAPHIFY_OPENAI_MODEL:-${MODEL:-meta/llama-3.3-70b-instruct}}"
  MODEL="${GRAPHIFY_OPENAI_MODEL:-meta/llama-3.3-70b-instruct}"
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

if [ "$CODE_ONLY" = false ]; then
  echo "Building semantic Graphify graph with backend=$BACKEND ${MODEL:+model=$MODEL}."
  export GRAPHIFY_MAX_OUTPUT_TOKENS="${GRAPHIFY_MAX_OUTPUT_TOKENS:-4096}"
  export GRAPHIFY_LLM_TEMPERATURE="${GRAPHIFY_LLM_TEMPERATURE:-0}"
  export GRAPHIFY_API_TIMEOUT="${GRAPHIFY_API_TIMEOUT:-$API_TIMEOUT}"
fi

echo "Writing Obsidian export to: $(pwd)/$VAULT_DIR"
mkdir -p "$VAULT_DIR"

if [ "$FORCE" = true ]; then
  export GRAPHIFY_FORCE=1
fi

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
  MODEL_ARGS=()
  if [ -n "$MODEL" ]; then
    MODEL_ARGS=("--model" "$MODEL")
  fi
  graphify extract . --backend "$BACKEND" "${MODEL_ARGS[@]}" --max-concurrency "$MAX_CONCURRENCY" --max-workers "$MAX_WORKERS" --token-budget "$TOKEN_BUDGET" --api-timeout "$API_TIMEOUT" --no-cluster
  if [ "$NO_CLUSTER" = false ]; then
    graphify cluster-only . --backend "$BACKEND" "${MODEL_ARGS[@]}" --no-viz
  fi
fi

graphify export obsidian --dir "$VAULT_DIR"
graphify export neo4j

printf '\nDone.\n- Graph report: %s/GRAPH_REPORT.md\n- Obsidian vault: %s\n- Neo4j import: %s/cypher.txt\n' "$(pwd)/graphify-out" "$(pwd)/$VAULT_DIR" "$(pwd)/graphify-out"

if [ "$IMPORT_NEO4J" = true ]; then
  ./scripts/neo4j-import.sh
fi

if [ "$CODE_ONLY" = false ]; then
  printf '\nNOTE: Semantic extraction may use your LLM backend for docs and community labels.\nUse this only when you want a richer, GraphRAG-ready graph and have an available model.\nFor low-token maintenance, continue using ./scripts/update-knowledge-graph.sh.\n'
fi
