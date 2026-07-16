#!/usr/bin/env bash
# Local token-use ledger and budget alerting for Atlas Core.
# It never claims to be the provider's billing authority.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs/token-tracking"
mkdir -p "$LOG_DIR"
chmod 700 "$LOG_DIR"

# Positive values are local monthly budgets, zero means local/unlimited and
# -1 means the provider has no trustworthy token budget configured here.
declare -A BUDGETS=(
    ["groq"]=1000000
    ["openrouter"]=500000
    ["anthropic"]=200000
    ["gemini"]=1000000
    ["nvidia"]=-1
    ["openai"]=-1
    ["ollama"]=0
)
PROVIDERS=(groq openrouter anthropic gemini nvidia openai ollama)

ALERT_THRESHOLD=80
CRITICAL_THRESHOLD=95

usage() {
    echo "Usage: $0 {report|log provider tokens model|check provider}" >&2
}

require_provider() {
    local provider=$1
    if [[ -z "${BUDGETS[$provider]+configured}" ]]; then
        echo "ERROR: unknown provider: $provider" >&2
        return 64
    fi
}

log_usage() {
    local provider=$1
    local tokens=$2
    local model=$3
    require_provider "$provider" || return $?
    if [[ ! "$tokens" =~ ^[0-9]+$ ]]; then
        echo "ERROR: tokens must be a non-negative integer." >&2
        return 2
    fi
    if [[ -z "$model" || "$model" == *$'\n'* || "$model" == *$'\r'* ]]; then
        echo "ERROR: model must be a non-empty single-line value." >&2
        return 2
    fi

    local timestamp log_file
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    log_file="${LOG_DIR}/${provider}-$(date +%Y%m).log"
    if [[ -L "$log_file" ]] || { [[ -e "$log_file" ]] && [[ ! -f "$log_file" ]]; }; then
        echo "ERROR: refusing unsafe token ledger: $log_file" >&2
        return 73
    fi
    touch "$log_file"
    chmod 600 "$log_file"
    printf '%s | %s | %s\n' "$timestamp" "$model" "$tokens" >> "$log_file"
}

get_monthly_usage() {
    local provider=$1
    local log_file="${LOG_DIR}/${provider}-$(date +%Y%m).log"
    if [[ ! -f "$log_file" || -L "$log_file" ]]; then
        echo 0
        return
    fi
    # New records end in the numeric count. Read the penultimate column too so
    # historical "123 tokens" records are recovered instead of summed as zero.
    awk '
        {
            value = $NF
            if (value == "tokens" && NF > 1) value = $(NF - 1)
            if (value ~ /^[0-9]+$/) sum += value
        }
        END { printf "%.0f\n", sum + 0 }
    ' "$log_file"
}

check_budget() {
    local provider=$1
    require_provider "$provider" || return $?
    local budget=${BUDGETS[$provider]}
    local usage
    usage=$(get_monthly_usage "$provider")

    if [[ $budget -lt 0 ]]; then
        echo "ℹ️  ${provider}: budget unknown (${usage} locally recorded tokens)"
        return 0
    fi
    if [[ $budget -eq 0 ]]; then
        echo "ℹ️  ${provider}: local/unlimited (${usage} locally recorded tokens)"
        return 0
    fi

    local percent=$((usage * 100 / budget))
    if [[ $percent -ge $CRITICAL_THRESHOLD ]]; then
        echo "🚨 CRITICAL: ${provider} at ${percent}% budget (${usage}/${budget} locally recorded tokens)"
        return 2
    fi
    if [[ $percent -ge $ALERT_THRESHOLD ]]; then
        echo "⚠️  WARNING: ${provider} at ${percent}% budget (${usage}/${budget} locally recorded tokens)"
        return 1
    fi
    echo "✅ ${provider}: ${percent}% budget (${usage}/${budget} locally recorded tokens)"
}

report_all() {
    echo "📊 LOCAL TOKEN LEDGER ($(date '+%Y-%m-%d %H:%M:%S'))"
    echo "Local records only; not provider billing or a live quota query."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    local max_status=0 provider status
    for provider in "${PROVIDERS[@]}"; do
        status=0
        if check_budget "$provider"; then
            status=0
        else
            status=$?
        fi
        if [[ $status -gt $max_status ]]; then
            max_status=$status
        fi
    done

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    return "$max_status"
}

case "${1:-report}" in
    report)
        [[ $# -le 1 ]] || { usage; exit 2; }
        report_all
        ;;
    log)
        [[ $# -eq 4 ]] || { usage; exit 2; }
        log_usage "$2" "$3" "$4"
        ;;
    check)
        [[ $# -eq 2 ]] || { usage; exit 2; }
        check_budget "$2"
        ;;
    *)
        usage
        exit 2
        ;;
esac
