#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Watch for graphify extraction to finish, then validate and remediate if needed.
INVALID_JSON_THRESHOLD=10
MIN_NODES=20
RETRY_TOKEN_BUDGET=2000
RETRY_CONCURRENCY=1
RETRY_WORKERS=1
LOG=/tmp/graphify_autorem.log
echo "[autorem] starting watch" > "$LOG"
# wait for any graphify extract to finish
while pgrep -f "graphify extract" >/dev/null 2>&1; do
  echo "[autorem] graphify extract still running..." >> "$LOG"
  sleep 10
done
# wait a bit for wrapper to finish writing reports
sleep 5
# generate or read quality report
QR=graphify-out/quality-report.json
if [ ! -f "$QR" ]; then
  echo "[autorem] quality report not found, generating from logs" >> "$LOG"
  python3 - "$QR" graphify-out/logs/pipeline.log . openai meta/llama-3.3-70b-instruct <<'PY'
import json,sys
from pathlib import Path
report_path=Path(sys.argv[1])
log_path=Path(sys.argv[2])
# reproduce minimal metrics
out_dir=Path('graphify-out')
graph_path=out_dir/'graph.json'
nodes=[]
if graph_path.exists():
    try:
        g=json.loads(graph_path.read_text(encoding='utf-8'))
        nodes=g.get('nodes') or []
    except Exception:
        nodes=[]
log_text=log_path.read_text(encoding='utf-8',errors='replace') if log_path.exists() else ''
metrics={'node_count': len(nodes), 'invalid_json_count': log_text.count('invalid JSON')+log_text.count('returned invalid JSON'), 'hollow_response_count': log_text.count('hollow response')}
report_path.write_text(json.dumps(metrics,indent=2))
print(json.dumps(metrics,indent=2))
PY
fi
# read metrics
metrics_file="$QR"
if [ ! -f "$metrics_file" ]; then
  echo "[autorem] no metrics file, aborting" >> "$LOG"
  exit 0
fi
metrics=$(cat "$metrics_file")
invalid_json=$(echo "$metrics" | python3 -c "import sys, json; print(json.load(sys.stdin).get('invalid_json_count',0))")
node_count=$(echo "$metrics" | python3 -c "import sys, json; print(json.load(sys.stdin).get('node_count',0))")
echo "[autorem] node_count=$node_count invalid_json=$invalid_json" >> "$LOG"
remedied=false
if [ "$invalid_json" -gt "$INVALID_JSON_THRESHOLD" ]; then
  echo "[autorem] invalid_json ($invalid_json) > threshold ($INVALID_JSON_THRESHOLD) -> rerunning pipeline with conservative settings" >> "$LOG"
  ./scripts/run-graphify-quality-pipeline.sh --backend openai --model meta/llama-3.3-70b-instruct --path . --token-budget $RETRY_TOKEN_BUDGET --max-workers $RETRY_WORKERS --max-concurrency $RETRY_CONCURRENCY --api-timeout 900 > /tmp/graphify_retry_conservative.log 2>&1
  remedied=true
fi
if [ "$node_count" -lt "$MIN_NODES" ]; then
  echo "[autorem] node_count ($node_count) < MIN_NODES ($MIN_NODES) -> rerun full pipeline (conservative)" >> "$LOG"
  ./scripts/run-graphify-quality-pipeline.sh --backend openai --model meta/llama-3.3-70b-instruct --path . --token-budget $RETRY_TOKEN_BUDGET --max-workers $RETRY_WORKERS --max-concurrency $RETRY_CONCURRENCY --api-timeout 900 > /tmp/graphify_retry_nodes.log 2>&1
  remedied=true
fi
# Generate audit artifact
python3 - <<'PY'
import json,sys
from pathlib import Path
out=Path('graphify-out')
qr=out/'quality-report.json'
report={'summary':'Auto remediation run','remedied':False}
if qr.exists():
    report.update(json.loads(qr.read_text()))
report['remedied']=False
if Path('/tmp/graphify_retry_conservative.log').exists() or Path('/tmp/graphify_retry_nodes.log').exists():
    report['remedied']=True
Path('graphify-out/audit-report.json').write_text(json.dumps(report,indent=2))
print('audit report written')
PY
# Create premortem
cat > graphify-out/premortem.md <<'MD'
# Premortem: Graphify Semantic Build

Likely failure modes observed:
- LLM returned invalid JSON due to token truncation -> mitigate by lowering token budget and reducing concurrency
- Hollow/empty responses due to model instability or quota limits -> mitigate by switching provider or model and retrying chunks
- Partial exports due to wrapper crash -> mitigate by ensuring wrapper writes artifacts atomically and backing up graph.json

Mitigations applied automatically:
- If invalid JSON > threshold (10), rerun with token_budget=2000 and concurrency=1 once
- If node_count below threshold, rerun conservative full pipeline

Further actions:
- If failures persist, run targeted chunk re-extraction and inspect model responses
- Consider switching model (e.g., smaller but more stable or alternative provider)
- Add JSON schema validation + retries per chunk in Graphify extraction step
MD

if [ "$remedied" = true ]; then
  echo "[autorem] remediation runs finished; audit artifacts at graphify-out/" >> "$LOG"
else
  echo "[autorem] no remediation necessary; audit artifacts at graphify-out/" >> "$LOG"
fi
echo "[autorem] done" >> "$LOG"
