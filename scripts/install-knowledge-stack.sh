#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

INSTALL_DEPS=false
INSTALL_UNDERSTAND_ANYTHING=false
INSTALL_NEO4J_IMAGE=false
START_NEO4J=false
NEO4J_CONTAINER_NAME="atlas-neo4j"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-atlasneo4j}"
UNDERSTAND_ANYTHING_DIR="tools/understand-anything"

usage() {
  cat <<'EOF' >&2
Usage: ./scripts/install-knowledge-stack.sh [options]

Options:
  --deps                    Install GraphRAG dependencies in .venv (graphiti, neo4j Python driver)
  --understand-anything     Clone the Understand-Anything repo for local reference/use
  --neo4j-image             Pull the Neo4j Docker image for GraphRAG/Graphify import
  --start-neo4j             Start a local Neo4j container using Docker
  --all                     Run all install tasks
  -h, --help                Show this help text

Environment:
  NEO4J_PASSWORD            Neo4j password for local container (default: atlasneo4j)
EOF
  exit 1
}

if [ "$#" -eq 0 ]; then
  usage
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
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      ;;
  esac
  shift
done

if [ ! -f ".venv/bin/activate" ]; then
  echo "ERROR: .venv not found. Create the project virtualenv first." >&2
  exit 1
fi

source .venv/bin/activate

if [ "$INSTALL_DEPS" = true ]; then
  echo "Installing GraphRAG dependencies into .venv..."
  python -m pip install --upgrade pip setuptools wheel
  python -m pip install graphiti==0.1.13 neo4j==6.2.0
  echo "Dependencies installed: graphiti, neo4j."
fi

if [ "$INSTALL_UNDERSTAND_ANYTHING" = true ]; then
  if [ -d "$UNDERSTAND_ANYTHING_DIR" ]; then
    echo "Understand-Anything repository already exists at $UNDERSTAND_ANYTHING_DIR."
  else
    echo "Cloning Understand-Anything into $UNDERSTAND_ANYTHING_DIR..."
    mkdir -p "$(dirname "$UNDERSTAND_ANYTHING_DIR")"
    git clone https://github.com/Egonex-AI/Understand-Anything.git "$UNDERSTAND_ANYTHING_DIR"
  fi
  echo "Understand-Anything is available at $UNDERSTAND_ANYTHING_DIR. Use Claude Code plugin install commands in the repo if desired."
fi

if [ "$INSTALL_NEO4J_IMAGE" = true ] || [ "$START_NEO4J" = true ]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: Docker is required to pull or start Neo4j." >&2
    exit 1
  fi
fi

if [ "$INSTALL_NEO4J_IMAGE" = true ]; then
  echo "Pulling Neo4j Docker image..."
  docker pull neo4j:latest
  echo "Neo4j Docker image is ready."
fi

if [ "$START_NEO4J" = true ]; then
  if docker ps --format '{{.Names}}' | grep -qx "$NEO4J_CONTAINER_NAME"; then
    echo "Neo4j container '$NEO4J_CONTAINER_NAME' is already running."
  else
    if docker ps -a --format '{{.Names}}' | grep -qx "$NEO4J_CONTAINER_NAME"; then
      echo "Starting existing Neo4j container '$NEO4J_CONTAINER_NAME'..."
      docker start "$NEO4J_CONTAINER_NAME"
    else
      echo "Starting new Neo4j container '$NEO4J_CONTAINER_NAME'..."
      docker run -d --name "$NEO4J_CONTAINER_NAME" -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH="neo4j/$NEO4J_PASSWORD" neo4j:latest
    fi
  fi
  echo "Neo4j is available at bolt://localhost:7687 with user 'neo4j'. Set NEO4J_PASSWORD to $NEO4J_PASSWORD or export a custom password before running this script."
fi

if [ "$INSTALL_DEPS" = false ] && [ "$INSTALL_UNDERSTAND_ANYTHING" = false ] && [ "$INSTALL_NEO4J_IMAGE" = false ] && [ "$START_NEO4J" = false ]; then
  usage
fi
