#!/usr/bin/env bash
# Read-only, evidence-producing Atlas <-> Hermes pairing verification.
set -uo pipefail
IFS=$'\n\t'

readonly REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"
readonly TWIN_CLIENT="${REPO_ROOT}/scripts/hermes_skill_atlas_twin/atlas_twin.py"
readonly VPS_USER="${VPS_USER:-root}"
: "${VPS_HOST:?Set VPS_HOST to the verified Tailscale IP or MagicDNS name}"
readonly VPS_HOST
readonly REMOTE="${VPS_USER}@${VPS_HOST}"
readonly REMOTE_CLIENT="/var/lib/hermes/.hermes/skills/atlas-twin/atlas_twin.py"
readonly SSH_OPTIONS=(
    -o BatchMode=yes
    -o ConnectTimeout=8
    -o StrictHostKeyChecking=yes
    -o LogLevel=ERROR
)

failures=0
pass() { printf '  PASS  %s\n' "$*"; }
fail() { printf '  FAIL  %s\n' "$*" >&2; failures=$((failures + 1)); }
note() { printf '  NOTE  %s\n' "$*"; }

if [[ ! "${VPS_USER}" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; then
    fail "VPS_USER is invalid"
fi
if [[ ! "${VPS_HOST}" =~ ^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$ ]]; then
    fail "VPS_HOST is invalid"
fi
if ! python3 - "${VPS_HOST}" <<'PY'
import ipaddress
import sys

host = sys.argv[1].casefold().rstrip(".")
if host.endswith(".ts.net"):
    raise SystemExit(0)
try:
    address = ipaddress.ip_address(host)
except ValueError:
    raise SystemExit(1)
raise SystemExit(0 if address in ipaddress.ip_network("100.64.0.0/10") else 1)
PY
then
    fail "VPS_HOST is not a Tailscale address"
fi

printf '%s\n' 'Atlas signed readiness'
if [[ ! -f "${ENV_FILE}" || -L "${ENV_FILE}" ]]; then
    fail "local .env is missing or symlinked"
elif local_health="$(python3 "${TWIN_CLIENT}" --env-file "${ENV_FILE}" health 2>&1)"; then
    if python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"] and d["merkle_chain_ok"]' \
        <<<"${local_health}"; then
        pass "Atlas accepted a fresh signed nonce and its Merkle chain is integral"
    else
        fail "Atlas health response did not prove readiness"
    fi
else
    fail "Atlas signed health failed: ${local_health}"
fi

printf '%s\n' 'Hermes pinned service'
if service_state="$(ssh "${SSH_OPTIONS[@]}" "${REMOTE}" \
    'systemctl is-active hermes-agent.service' 2>&1)" \
    && [[ "${service_state}" == "active" ]]; then
    pass "hermes-agent.service is active"
else
    fail "hermes-agent.service is not active: ${service_state:-unreachable}"
fi

expected_commit="9de9c25f620ff7f1ce0fd5457d596052d5159596"
if actual_commit="$(ssh "${SSH_OPTIONS[@]}" "${REMOTE}" \
    'git -C /opt/hermes-agent rev-parse HEAD' 2>&1)" \
    && [[ "${actual_commit}" == "${expected_commit}" ]]; then
    pass "Hermes code matches the audited immutable commit"
else
    fail "Hermes release commit mismatch or unreadable"
fi

if service_identity="$(ssh "${SSH_OPTIONS[@]}" "${REMOTE}" \
    "systemctl show hermes-agent.service -p User -p NoNewPrivileges --value" 2>&1)" \
    && [[ "${service_identity}" == *"hermes"* && "${service_identity}" == *"yes"* ]]; then
    pass "Hermes runs as the dedicated user with no-new-privileges"
else
    fail "Hermes service identity/hardening check failed"
fi

printf '%s\n' 'Hermes to Atlas signed channel'
skill_trusted=0
local_skill_sha="$(sha256sum "${TWIN_CLIENT}" | awk '{print $1}')"
if remote_skill_evidence="$(ssh "${SSH_OPTIONS[@]}" "${REMOTE}" \
    "sha256sum '${REMOTE_CLIENT}'; stat -c '%U:%G %a' '${REMOTE_CLIENT}'" 2>&1)"; then
    remote_skill_sha="$(awk 'NR == 1 {print $1}' <<<"${remote_skill_evidence}")"
    remote_skill_mode="$(awk 'NR == 2 {print $0}' <<<"${remote_skill_evidence}")"
    if [[ "${remote_skill_sha}" == "${local_skill_sha}" \
        && "${remote_skill_mode}" == "root:hermes 750" ]]; then
        pass "remote atlas-twin client matches the local audited artifact and is root-owned"
        skill_trusted=1
    else
        fail "remote atlas-twin client hash or ownership differs from the audited artifact"
    fi
else
    fail "remote atlas-twin client cannot be verified"
fi

remote_probe="runuser -u hermes -- env HOME=/var/lib/hermes HERMES_HOME=/var/lib/hermes/.hermes python3 '${REMOTE_CLIENT}' health"
if [[ ${skill_trusted} -ne 1 ]]; then
    fail "signed remote probe skipped because its client artifact is untrusted"
elif remote_health="$(ssh "${SSH_OPTIONS[@]}" "${REMOTE}" "${remote_probe}" 2>&1)"; then
    if python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"] and d["governance_ok"]' \
        <<<"${remote_health}"; then
        pass "Hermes reached Atlas through the real signed skill"
    else
        fail "remote twin response did not prove Atlas governance readiness"
    fi
else
    fail "Hermes could not complete the signed twin probe: ${remote_health}"
fi

note "This verifier does not spend provider tokens or send a Telegram message."
note "Provider inference and Telegram delivery remain unverified until their explicit live smokes pass."

if [[ ${failures} -ne 0 ]]; then
    printf 'Twin verification failed: %d check(s).\n' "${failures}" >&2
    exit 1
fi
printf '%s\n' 'Twin verification passed for the signed transport and service boundary.'
