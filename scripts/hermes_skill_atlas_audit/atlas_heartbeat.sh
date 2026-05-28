#!/bin/bash
# atlas_heartbeat — daily liveness beacon from Hermes (VPS) into Atlas's Merkle
# ledger (ADR-029 reverse audit). Deploy to ~/.hermes/scripts/ and schedule via:
#
#   hermes cron create "0 9 * * *" --name atlas-heartbeat --no-agent \
#       --script atlas_heartbeat.sh
#
# With --no-agent the script IS the job; its stdout (the audit receipt) is
# delivered verbatim. If Atlas is unreachable the client exits non-zero and
# prints why — the heartbeat is best-effort and never blocks Hermes.
set -euo pipefail

export HERMES_API_KEY="$(grep -oP 'HERMES_API_KEY=\K.*' /root/.hermes/.env)"

exec python3 /root/.hermes/skills/atlas-audit/atlas_audit.py \
    --action cron.heartbeat \
    --result success \
    --risk safe \
    --payload "{\"host\":\"hermes-vps\",\"ts\":\"$(date -Iseconds)\"}"
