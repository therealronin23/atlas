#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'EOF'
ERROR: graphify-monitor-and-switch.sh is retired.

It used workstation-wide process matching and implicit provider switching, so
it could terminate an unrelated Graphify job or spend against the wrong
provider. Run one deliberate, serialized build instead:

  ./scripts/run-graphify-quality-pipeline.sh \
    --backend <backend> --model <model> --max-retries 0 --strict

Inspect graphify-out/quality-report.json before choosing another provider.
EOF
exit 64
