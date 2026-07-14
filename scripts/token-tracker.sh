#!/bin/bash
# Token tracking and budget alerting system for Atlas Core
# Logs API calls and alerts when approaching budget limits

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs/token-tracking"
BUDGET_FILE="${PROJECT_ROOT}/.token-budget"

# Create logging directory
mkdir -p "$LOG_DIR"

# Token budgets (monthly, in tokens)
declare -A BUDGETS=(
    ["groq"]=1000000         # Groq free tier
    ["openrouter"]=500000    # OpenRouter standard
    ["anthropic"]=200000     # Claude API (conservative)
    ["ollama"]=0             # Local - unlimited
    ["gemini"]=1000000       # Gemini monthly
)

# Alert thresholds (when to warn, in percent of budget)
ALERT_THRESHOLD=80
CRITICAL_THRESHOLD=95

# Function: Log token usage
log_usage() {
    local provider=$1
    local tokens=$2
    local model=$3
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    local log_file="${LOG_DIR}/${provider}-$(date +%Y%m).log"
    echo "${timestamp} | ${model} | ${tokens} tokens" >> "$log_file"
}

# Function: Get current month usage
get_monthly_usage() {
    local provider=$1
    local log_file="${LOG_DIR}/${provider}-$(date +%Y%m).log"
    
    if [[ ! -f "$log_file" ]]; then
        echo 0
        return
    fi
    
    awk '{sum += $NF} END {print sum}' "$log_file" 2>/dev/null || echo 0
}

# Function: Check budget and alert
check_budget() {
    local provider=$1
    local budget=${BUDGETS[$provider]:-0}
    
    if [[ $budget -eq 0 ]]; then
        return  # Unlimited (local)
    fi
    
    local usage=$(get_monthly_usage "$provider")
    local percent=$((usage * 100 / budget))
    
    if [[ $percent -ge $CRITICAL_THRESHOLD ]]; then
        echo "🚨 CRITICAL: ${provider} at ${percent}% budget (${usage}/${budget} tokens)"
        return 2
    elif [[ $percent -ge $ALERT_THRESHOLD ]]; then
        echo "⚠️  WARNING: ${provider} at ${percent}% budget (${usage}/${budget} tokens)"
        return 1
    else
        echo "✅ ${provider}: ${percent}% budget (${usage}/${budget} tokens)"
        return 0
    fi
}

# Function: Report all providers
report_all() {
    echo "📊 TOKEN BUDGET REPORT ($(date '+%Y-%m-%d %H:%M:%S'))"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    local max_status=0
    for provider in "${!BUDGETS[@]}"; do
        if ! check_budget "$provider"; then
            max_status=$?
        fi
    done
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    return $max_status
}

# Main
case "${1:-report}" in
    report)
        report_all
        ;;
    log)
        shift
        log_usage "$@"
        ;;
    check)
        check_budget "${2:-anthropic}"
        ;;
    *)
        echo "Usage: $0 {report|log provider tokens model|check provider}"
        exit 1
        ;;
esac
