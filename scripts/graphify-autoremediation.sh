#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'EOF'
ERROR: graphify-autoremediation.sh is retired.

It derived decisions from stale, accumulated logs and could launch external LLM
work implicitly. The supported replacement is the current-run quality gate:

  ./scripts/run-graphify-quality-pipeline.sh \
    --backend <backend> --model <model> --max-retries 0 --strict

Any provider change is a separate, deliberate operation after inspecting
graphify-out/quality-report.json.
EOF
exit 64
