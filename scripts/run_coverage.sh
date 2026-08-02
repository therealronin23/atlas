#!/usr/bin/env bash
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export PYTHONPATH=src

.venv/bin/python -m coverage run -m pytest "$@"
.venv/bin/coverage report -m -i --include="src/*"
.venv/bin/coverage html -d htmlcov -i --include="src/*"
