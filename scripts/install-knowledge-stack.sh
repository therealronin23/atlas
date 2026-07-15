#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

INSTALL_DEPS=false
INSTALL_UNDERSTAND_ANYTHING=false
INSTALL_NEO4J_IMAGE=false
START_NEO4J=false
NEO4J_CONTAINER_NAME="atlas-neo4j"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-}"
NEO4J_IMAGE="${NEO4J_IMAGE:-neo4j:2026.06.0}"
UNDERSTAND_ANYTHING_DIR="tools/understand-anything"

usage() {
  cat <<'EOF' >&2
Usage: ./scripts/install-knowledge-stack.sh [options]

Options:
  --deps                    Install GraphRAG dependencies in .venv
  --understand-anything     Clone Understand-Anything for local reference/use
  --neo4j-image             Pull the pinned Neo4j Docker image
  --start-neo4j             Start a loopback-only local Neo4j container
  --all                     Run all install tasks
  -h, --help                Show this help text

Environment:
  NEO4J_PASSWORD            Required for --start-neo4j (minimum 16 characters)
  NEO4J_IMAGE               Pinned image override (default: neo4j:2026.06.0)
EOF
}

if [ "$#" -eq 0 ]; then
  usage
  exit 2
fi

while [ "$#" -gt 0 ]; do
  case "$1" in
    --deps)
      INSTALL_DEPS=true
      ;;
    --understand-anything)
      INSTALL_UNDERSTAND_ANYTHING=true
      ;;
    --neo4j-image)
      INSTALL_NEO4J_IMAGE=true
      ;;
    --start-neo4j)
      START_NEO4J=true
      ;;
    --all)
      INSTALL_DEPS=true
      INSTALL_UNDERSTAND_ANYTHING=true
      INSTALL_NEO4J_IMAGE=true
      START_NEO4J=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
  shift
done

if [ "$INSTALL_DEPS" = true ]; then
  if [ ! -x .venv/bin/python ]; then
    echo "ERROR: .venv/bin/python is unavailable." >&2
    exit 1
  fi
  echo "Installing pinned GraphRAG dependencies into .venv..."
  .venv/bin/python -m pip install graphiti==0.1.13 neo4j==6.2.0
  echo "Dependencies installed: graphiti, neo4j."
fi

if [ "$INSTALL_UNDERSTAND_ANYTHING" = true ]; then
  if [ -d "$UNDERSTAND_ANYTHING_DIR" ]; then
    echo "Understand-Anything already exists at $UNDERSTAND_ANYTHING_DIR."
  else
    echo "Cloning Understand-Anything into $UNDERSTAND_ANYTHING_DIR..."
    mkdir -p "$(dirname "$UNDERSTAND_ANYTHING_DIR")"
    git clone https://github.com/Egonex-AI/Understand-Anything.git "$UNDERSTAND_ANYTHING_DIR"
  fi
fi

if [ "$INSTALL_NEO4J_IMAGE" = true ] || [ "$START_NEO4J" = true ]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: Docker is required for Neo4j setup." >&2
    exit 1
  fi
fi

if [ "$INSTALL_NEO4J_IMAGE" = true ]; then
  echo "Pulling pinned Neo4j image $NEO4J_IMAGE..."
  docker pull "$NEO4J_IMAGE"
fi

if [ "$START_NEO4J" = true ]; then
  if [ -z "$NEO4J_PASSWORD" ]; then
    echo "ERROR: NEO4J_PASSWORD is required for --start-neo4j." >&2
    exit 1
  fi
  if [ "${#NEO4J_PASSWORD}" -lt 16 ]; then
    echo "ERROR: NEO4J_PASSWORD must contain at least 16 characters." >&2
    exit 1
  fi

  if docker ps -a --format '{{.Names}}' | grep -qx "$NEO4J_CONTAINER_NAME"; then
    PORT_BINDINGS="$(docker inspect --format '{{json .HostConfig.PortBindings}}' "$NEO4J_CONTAINER_NAME")"
    if [[ "$PORT_BINDINGS" != *'127.0.0.1'* ]]; then
      echo "ERROR: existing Neo4j container is not loopback-only; recreate it securely." >&2
      exit 1
    fi
    if ! docker ps --format '{{.Names}}' | grep -qx "$NEO4J_CONTAINER_NAME"; then
      docker start "$NEO4J_CONTAINER_NAME" >/dev/null
    fi
    echo "Neo4j container is running on loopback only."
  else
    echo "Starting loopback-only Neo4j container..."
    export NEO4J_AUTH="neo4j/$NEO4J_PASSWORD"
    docker run -d --name "$NEO4J_CONTAINER_NAME" \
      --restart unless-stopped \
      -p 127.0.0.1:7474:7474 \
      -p 127.0.0.1:7687:7687 \
      -e NEO4J_AUTH \
      -v atlas-neo4j-data:/data \
      -v atlas-neo4j-logs:/logs \
      "$NEO4J_IMAGE" >/dev/null
    unset NEO4J_AUTH
    echo "Neo4j is available at bolt://127.0.0.1:7687 with user 'neo4j'."
  fi
fi
