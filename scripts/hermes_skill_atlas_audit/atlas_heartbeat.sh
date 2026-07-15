#!/usr/bin/env bash
# Compatibility heartbeat. The atlas-twin client parses the protected Hermes
# EnvironmentFile as data; this script never sources or prints it.
set -euo pipefail

readonly HERMES_HOME="${HERMES_HOME:-/var/lib/hermes/.hermes}"
readonly CLIENT="${HERMES_HOME}/skills/atlas-twin/atlas_twin.py"
[[ -f "${CLIENT}" && ! -L "${CLIENT}" ]] || {
    printf 'atlas-twin skill is not installed\n' >&2
    exit 2
}

payload="$(printf '{\"host\":\"hermes-vps\",\"ts\":\"%s\"}' "$(date -Iseconds)")"
exec python3 "${CLIENT}" audit cron.heartbeat \
    --result success \
    --risk safe \
    --payload "${payload}"
