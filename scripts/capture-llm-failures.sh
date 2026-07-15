#!/usr/bin/env bash
set -euo pipefail
# Tail Graphify logs and capture raw LLM failure snippets to a consolidated file.
cd "$(dirname "$0")/.."
OUT=graphify-out/llm-raw-responses.log
mkdir -p graphify-out/logs
# Files to watch (existing ones plus any temp wrapper logs)
WATCH_FILES=(graphify-out/logs/pipeline.log /tmp/graphify_retry_nvidia.log /tmp/graphify_gemini_run.log /tmp/graphify_run_async.log /tmp/graphify_nvidia_repo.log /tmp/graphify_switched_run.log)
# Ensure OUT exists
touch "$OUT"
# AWK-based streaming monitor: keep a rolling buffer of previous lines and on match dump buffer + next N lines
BUFFER=80
AFTER=80
PATTERN="invalid JSON|returned invalid JSON|hollow response|LLM returned invalid JSON|single-file chunk .* truncated"
# Build list of files that exist
EXIST_FILES=()
for f in "${WATCH_FILES[@]}"; do
  if [ -f "$f" ]; then
    EXIST_FILES+=("$f")
  fi
done
# If none exist yet, fall back to pipeline.log (will be created later)
if [ ${#EXIST_FILES[@]} -eq 0 ]; then
  EXIST_FILES=(graphify-out/logs/pipeline.log)
fi
# Use tail -F to follow all files
# Pipe into awk which implements the buffer+capture behavior
# Using awk for portability; rely on gawk for strftime if available, else use date
TAIL_CMD=(tail -n 0 -F)
TAIL_CMD+=("${EXIST_FILES[@]}")
# Start tail and process
"${TAIL_CMD[@]}" | awk -v outfile="$OUT" -v bufsize="$BUFFER" -v afterlimit="$AFTER" -v pat="$PATTERN" '
  function now(){
    cmd = "date -u +%Y-%m-%dT%H:%M:%SZ"
    cmd | getline t; close(cmd)
    return t
  }
  BEGIN{
    capture=0; after=0; idx=0; for(i=0;i<bufsize;i++) buf[i]="";
  }
  {
    line=$0; buf[idx%bufsize]=line; idx++;
    if (tolower(line) ~ tolower(pat)) {
      ts = now();
      print "----" ts "----" >> outfile;
      # dump buffer
      start = idx - bufsize; if (start < 0) start = 0;
      for (i=start; i<idx; i++) {
        l = buf[i%bufsize]; print l >> outfile;
      }
      # mark to capture following lines
      after = afterlimit;
      fflush(outfile);
    } else if (after>0) {
      print line >> outfile; fflush(outfile); after--; if (after==0) print "----end----" >> outfile;
    }
  }
'
