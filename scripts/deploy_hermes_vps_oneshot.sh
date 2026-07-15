#!/usr/bin/env bash
# Safely stage and invoke the pinned Hermes provisioner over an existing SSH
# trust relationship. Secrets travel only in a mode-0600 JSON file; they never
# appear in process arguments, terminal output, or the remote command string.
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

readonly REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"
readonly INSTALLER="${REPO_ROOT}/scripts/install_hermes_agent_vps.sh"
readonly SKILL_DIR="${REPO_ROOT}/scripts/hermes_skill_atlas_twin"
readonly VPS_USER="${VPS_USER:-root}"
: "${VPS_HOST:?Set VPS_HOST to the verified Tailscale IP or MagicDNS name}"
readonly VPS_HOST
readonly REMOTE="${VPS_USER}@${VPS_HOST}"
readonly REMOTE_STAGE="/tmp/atlas-hermes-deploy-$(date -u +%Y%m%dT%H%M%SZ)-$$"
readonly PYTHON_BIN="${PYTHON_BIN:-python3}"
readonly SSH_OPTIONS=(
    -o BatchMode=yes
    -o ConnectTimeout=10
    -o StrictHostKeyChecking=yes
    -o LogLevel=ERROR
)

LOCAL_STAGE=""
REMOTE_CREATED=0

die() { printf '[hermes-deploy] ERROR: %s\n' "$*" >&2; exit 1; }
log() { printf '[hermes-deploy] %s\n' "$*"; }

cleanup() {
    if [[ -n "${LOCAL_STAGE}" && -d "${LOCAL_STAGE}" ]]; then
        case "${LOCAL_STAGE}" in
            /tmp/atlas-hermes-local.*) rm -rf -- "${LOCAL_STAGE}" ;;
            *) log "Refusing to remove unexpected local staging path" ;;
        esac
    fi
    if [[ ${REMOTE_CREATED} -eq 1 ]]; then
        if ! ssh "${SSH_OPTIONS[@]}" "${REMOTE}" "rm -rf -- '${REMOTE_STAGE}'"; then
            printf '[hermes-deploy] WARNING: remote staging cleanup failed: %s\n' \
                "${REMOTE_STAGE}" >&2
        fi
    fi
}
trap cleanup EXIT

[[ "${VPS_USER}" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || die "invalid VPS_USER"
[[ "${VPS_HOST}" =~ ^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$ ]] || die "invalid VPS_HOST"
[[ -f "${ENV_FILE}" && ! -L "${ENV_FILE}" ]] || die "missing or symlinked ENV_FILE"
[[ -f "${INSTALLER}" && -f "${SKILL_DIR}/SKILL.md" \
    && -f "${SKILL_DIR}/atlas_twin.py" ]] || die "Hermes deployment bundle is incomplete"
command -v "${PYTHON_BIN}" >/dev/null 2>&1 || die "python3 is required locally"
command -v ssh >/dev/null 2>&1 || die "ssh is required locally"
command -v scp >/dev/null 2>&1 || die "scp is required locally"
if ! "${PYTHON_BIN}" - "${VPS_HOST}" <<'PY'
import ipaddress
import sys

host = sys.argv[1].casefold().rstrip(".")
if host.endswith(".ts.net"):
    raise SystemExit(0)
try:
    address = ipaddress.ip_address(host)
except ValueError:
    raise SystemExit(1)
allowed = tuple(
    ipaddress.ip_network(value)
    for value in (
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
        "100.64.0.0/10", "fc00::/7",
    )
)
raise SystemExit(0 if any(address in network for network in allowed) else 1)
PY
then
    die "VPS_HOST must be a private IP, Tailscale IP, or full .ts.net name"
fi

LOCAL_STAGE="$(mktemp -d /tmp/atlas-hermes-local.XXXXXX)"
readonly BOOTSTRAP_JSON="${LOCAL_STAGE}/bootstrap.json"

log "Building a minimal bootstrap from literal .env values"
"${PYTHON_BIN}" - "${ENV_FILE}" "${BOOTSTRAP_JSON}" <<'PY'
from __future__ import annotations

import ast
import json
import os
import re
import secrets
import stat
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
raw = env_path.read_text(encoding="utf-8")
os.chmod(env_path, 0o600)

def parse_value(value: str, line_number: int) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    if stripped[0] in {"'", '"'}:
        try:
            decoded = ast.literal_eval(stripped)
        except (SyntaxError, ValueError) as exc:
            raise SystemExit(f"invalid quoted value at .env line {line_number}") from exc
        if not isinstance(decoded, str):
            raise SystemExit(f"non-string value at .env line {line_number}")
        return decoded
    return re.split(r"\s+#", stripped, maxsplit=1)[0].rstrip()

values: dict[str, str] = {}
for line_number, line in enumerate(raw.splitlines(), 1):
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    if stripped.startswith("export "):
        stripped = stripped[7:].lstrip()
    key, separator, value = stripped.partition("=")
    if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key.strip()):
        raise SystemExit(f"unsupported .env syntax at line {line_number}")
    key = key.strip()
    if key in values:
        raise SystemExit(f"duplicate .env key: {key}")
    values[key] = parse_value(value, line_number)

secret = values.get("HERMES_API_KEY", "")
if not secret:
    secret = secrets.token_hex(32)
    replacement = f"HERMES_API_KEY={secret}"
    pattern = re.compile(r"(?m)^(?:export\s+)?HERMES_API_KEY\s*=.*$")
    if pattern.search(raw):
        raw = pattern.sub(replacement, raw, count=1)
    else:
        raw = raw.rstrip("\n") + "\n" + replacement + "\n"
    temporary = env_path.with_name(f".{env_path.name}.hermes-{os.getpid()}")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, env_path)
        os.chmod(env_path, 0o600)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    values["HERMES_API_KEY"] = secret
elif len(secret.encode()) < 32:
    raise SystemExit("HERMES_API_KEY must contain at least 32 bytes")

selected_keys = (
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ALLOWED_USERS",
    "HERMES_API_KEY",
    "HERMES_MODEL_PROVIDER",
    "HERMES_MODEL",
    "ATLAS_DASHBOARD_URL",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
)
selected = {key: values[key] for key in selected_keys if values.get(key)}
required = selected_keys[:6]
missing = [key for key in required if not selected.get(key)]
if missing:
    raise SystemExit(f"missing required .env keys: {', '.join(missing)}")
provider_key = {
    "custom:groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}.get(selected["HERMES_MODEL_PROVIDER"])
if provider_key is None:
    raise SystemExit("HERMES_MODEL_PROVIDER must be custom:groq or openrouter")
if not selected.get(provider_key):
    raise SystemExit(f"selected provider requires {provider_key}")

fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as handle:
    json.dump(selected, handle, ensure_ascii=False, sort_keys=True)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
if stat.S_IMODE(output_path.stat().st_mode) != 0o600:
    raise SystemExit("could not secure bootstrap.json")
PY

log "Using the pre-enrolled SSH host key for ${REMOTE}"
ssh "${SSH_OPTIONS[@]}" "${REMOTE}" "umask 077; mkdir -- '${REMOTE_STAGE}'"
REMOTE_CREATED=1

log "Staging the provisioner, local skill and sealed bootstrap"
scp "${SSH_OPTIONS[@]}" -- "${INSTALLER}" "${BOOTSTRAP_JSON}" \
    "${REMOTE}:${REMOTE_STAGE}/"
scp "${SSH_OPTIONS[@]}" -r -- "${SKILL_DIR}" "${REMOTE}:${REMOTE_STAGE}/"

if [[ "${VPS_USER}" == "root" ]]; then
    remote_command="bash '${REMOTE_STAGE}/install_hermes_agent_vps.sh' '${REMOTE_STAGE}/bootstrap.json'"
else
    remote_command="sudo -n bash '${REMOTE_STAGE}/install_hermes_agent_vps.sh' '${REMOTE_STAGE}/bootstrap.json'"
fi
log "Provisioning the audited release; provider calls are not part of this step"
ssh "${SSH_OPTIONS[@]}" "${REMOTE}" "${remote_command}"

log "Provisioning completed and the shared key is stored only in ${ENV_FILE} and the VPS secret file"
log "Restart Atlas with the updated environment, then run scripts/verify_twin_pairing.sh"
