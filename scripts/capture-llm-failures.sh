#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'EOF'
ERROR: capture-llm-failures.sh is retired.

The historical helper spawned an unbounded tail/awk pipeline and copied broad
context around provider errors into a second file. Use the private, current-run
metrics in graphify-out/quality-report.json and the bounded canonical pipeline
log instead. Generate them with one deliberate
run-graphify-quality-pipeline.sh --strict execution.
EOF
exit 64
