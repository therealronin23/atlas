#!/usr/bin/env bash
# Provision the pinned Nous Research Hermes release as an unprivileged service.
#
# Usage (on the VPS, as root):
#   bash install_hermes_agent_vps.sh /path/to/bootstrap.json
#
# The bootstrap is a mode-0600 JSON file produced by
# deploy_hermes_vps_oneshot.sh. It is never sourced and is removed on exit.
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

readonly HERMES_VERSION="0.18.2"
readonly HERMES_TAG="v2026.7.7.2"
readonly HERMES_COMMIT="9de9c25f620ff7f1ce0fd5457d596052d5159596"
readonly HERMES_REPOSITORY="https://github.com/NousResearch/hermes-agent.git"
readonly UV_VERSION="0.11.21"
readonly UV_INSTALLER_URL="https://astral.sh/uv/${UV_VERSION}/install.sh"
readonly UV_INSTALLER_SHA256="053045e1e69ec77358fd44f2ef2cacb768a22d50f433e213624f0157ffbbc883"
readonly SERVICE_USER="hermes"
readonly SERVICE_GROUP="hermes"
readonly SERVICE_HOME="/var/lib/hermes"
readonly HERMES_HOME="${SERVICE_HOME}/.hermes"
readonly HERMES_WORKSPACE="${SERVICE_HOME}/workspace"
readonly RELEASE_PATH="/opt/hermes-agent"
readonly SERVICE_PATH="/etc/systemd/system/hermes-agent.service"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SKILL_SOURCE="${SCRIPT_DIR}/hermes_skill_atlas_twin"

BOOTSTRAP_JSON=""
RELEASE_STAGING=""
UV_INSTALLER_TMP=""

log() { printf '[hermes-install] %s\n' "$*"; }
die() { printf '[hermes-install] ERROR: %s\n' "$*" >&2; exit 1; }

cleanup() {
    if [[ -n "${UV_INSTALLER_TMP}" && -f "${UV_INSTALLER_TMP}" ]]; then
        rm -f -- "${UV_INSTALLER_TMP}"
    fi
    if [[ -n "${RELEASE_STAGING}" && -d "${RELEASE_STAGING}" ]]; then
        case "${RELEASE_STAGING}" in
            /opt/hermes-agent.new.*) rm -rf -- "${RELEASE_STAGING}" ;;
            *) log "Refusing to remove unexpected staging path" ;;
        esac
    fi
    if [[ -n "${BOOTSTRAP_JSON}" && -f "${BOOTSTRAP_JSON}" ]]; then
        rm -f -- "${BOOTSTRAP_JSON}"
    fi
}
trap cleanup EXIT

[[ ${EUID} -eq 0 ]] || die "run this provisioner as root"
[[ $# -eq 1 ]] || die "expected one mode-0600 bootstrap.json path"
[[ ! -L "$1" ]] || die "bootstrap.json must not be a symlink"
[[ -f "$1" ]] || die "bootstrap.json is not a regular file"
BOOTSTRAP_JSON="$(readlink -f -- "$1")"
[[ -x "$(command -v python3)" ]] || die "python3 is required before provisioning"
[[ -f "${SKILL_SOURCE}/SKILL.md" && -f "${SKILL_SOURCE}/atlas_twin.py" ]] \
    || die "repository-owned atlas-twin skill bundle is missing"
[[ ! -L "${SKILL_SOURCE}/SKILL.md" && ! -L "${SKILL_SOURCE}/atlas_twin.py" ]] \
    || die "skill bundle files must not be symlinks"

log "Validating bootstrap without evaluating shell code"
python3 - "${BOOTSTRAP_JSON}" <<'PY'
from __future__ import annotations

import ipaddress
import json
import os
import re
import stat
import sys
from pathlib import Path
from urllib.parse import urlsplit

path = Path(sys.argv[1])
mode = stat.S_IMODE(path.stat().st_mode)
if mode & 0o077:
    raise SystemExit("bootstrap.json must not be readable by group or others")
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid bootstrap.json: {exc}") from exc
if not isinstance(data, dict):
    raise SystemExit("bootstrap.json must contain a JSON object")

allowed = {
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS", "HERMES_API_KEY",
    "HERMES_MODEL_PROVIDER", "HERMES_MODEL", "ATLAS_DASHBOARD_URL",
    "GROQ_API_KEY", "OPENROUTER_API_KEY",
}
unknown = sorted(set(data) - allowed)
if unknown:
    raise SystemExit(f"unsupported bootstrap keys: {', '.join(unknown)}")
required = {
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS", "HERMES_API_KEY",
    "HERMES_MODEL_PROVIDER", "HERMES_MODEL", "ATLAS_DASHBOARD_URL",
}
missing = sorted(key for key in required if not data.get(key))
if missing:
    raise SystemExit(f"missing bootstrap keys: {', '.join(missing)}")
for key, value in data.items():
    if not isinstance(value, str) or "\x00" in value or "\n" in value or "\r" in value:
        raise SystemExit(f"{key} must be a single-line string")
if len(data["HERMES_API_KEY"].encode()) < 32:
    raise SystemExit("HERMES_API_KEY must contain at least 32 bytes")
if not re.fullmatch(r"[0-9]+(?:,[0-9]+)*", data["TELEGRAM_ALLOWED_USERS"]):
    raise SystemExit("TELEGRAM_ALLOWED_USERS must be comma-separated numeric user IDs")

provider = data["HERMES_MODEL_PROVIDER"]
provider_key = {
    "custom:groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}.get(provider)
if provider_key is None:
    raise SystemExit("HERMES_MODEL_PROVIDER must be custom:groq or openrouter")
if not data.get(provider_key):
    raise SystemExit(f"{provider} requires {provider_key}")
if not re.fullmatch(r"[A-Za-z0-9._:/+-]{1,200}", data["HERMES_MODEL"]):
    raise SystemExit("HERMES_MODEL contains unsupported characters")

parsed = urlsplit(data["ATLAS_DASHBOARD_URL"])
try:
    _ = parsed.port
except ValueError as exc:
    raise SystemExit("ATLAS_DASHBOARD_URL has an invalid port") from exc
if (
    parsed.scheme not in {"http", "https"}
    or parsed.hostname is None
    or parsed.username is not None
    or parsed.password is not None
    or parsed.path not in {"", "/"}
    or parsed.query
    or parsed.fragment
):
    raise SystemExit("ATLAS_DASHBOARD_URL must be a credential-free origin")
host = parsed.hostname.casefold().rstrip(".")
allowed_nets = tuple(
    ipaddress.ip_network(raw)
    for raw in (
        "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12",
        "192.168.0.0/16", "100.64.0.0/10", "::1/128", "fc00::/7",
    )
)
host_ok = host in {"localhost", "localhost.localdomain"} or host.endswith(".ts.net")
if not host_ok:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    host_ok = address is not None and any(address in network for network in allowed_nets)
if not host_ok:
    raise SystemExit("ATLAS_DASHBOARD_URL must use a private or Tailscale host")
PY

log "Installing minimal operating-system prerequisites"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl git python3 coreutils >/dev/null

install_uv() {
    local current=""
    if command -v uv >/dev/null 2>&1; then
        current="$(uv --version)"
    fi
    if [[ "${current}" == "uv ${UV_VERSION}" ]]; then
        return
    fi

    UV_INSTALLER_TMP="$(mktemp /tmp/uv-installer.XXXXXX)"
    curl --proto '=https' --tlsv1.2 -fsSL "${UV_INSTALLER_URL}" -o "${UV_INSTALLER_TMP}"
    local actual_sha
    actual_sha="$(sha256sum "${UV_INSTALLER_TMP}" | awk '{print $1}')"
    [[ "${actual_sha}" == "${UV_INSTALLER_SHA256}" ]] \
        || die "uv installer checksum mismatch"
    UV_UNMANAGED_INSTALL=/usr/local/bin UV_DISABLE_UPDATE=1 sh "${UV_INSTALLER_TMP}"
    rm -f -- "${UV_INSTALLER_TMP}"
    UV_INSTALLER_TMP=""
    [[ "$(/usr/local/bin/uv --version)" == "uv ${UV_VERSION}" ]] \
        || die "pinned uv installation did not produce the expected version"
}

log "Bootstrapping checksum-verified uv ${UV_VERSION}"
install_uv
readonly UV_BIN="$(command -v uv)"

if id "${SERVICE_USER}" >/dev/null 2>&1; then
    [[ "$(id -u "${SERVICE_USER}")" != "0" ]] || die "hermes account must not be root"
    usermod --home "${SERVICE_HOME}" --shell /usr/sbin/nologin "${SERVICE_USER}"
else
    useradd --system --user-group --home-dir "${SERVICE_HOME}" --create-home \
        --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

for path in "${SERVICE_HOME}" "${HERMES_HOME}" "${HERMES_WORKSPACE}" \
    "${HERMES_HOME}/skills" "${HERMES_HOME}/logs" "${HERMES_HOME}/memories"; do
    [[ ! -L "${path}" ]] || die "refusing symlinked Hermes state path: ${path}"
    install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0700 "${path}"
done

if systemctl is-active --quiet hermes-agent.service; then
    systemctl stop hermes-agent.service
fi
if [[ -S /run/user/0/bus ]] \
    && XDG_RUNTIME_DIR=/run/user/0 systemctl --user is-active --quiet hermes-gateway.service; then
    XDG_RUNTIME_DIR=/run/user/0 systemctl --user stop hermes-gateway.service
    XDG_RUNTIME_DIR=/run/user/0 systemctl --user disable hermes-gateway.service
fi

log "Fetching the pinned release tag and verifying its immutable commit"
RELEASE_STAGING="$(mktemp -d /opt/hermes-agent.new.XXXXXX)"
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null
git -C "${RELEASE_STAGING}" init -q
git -C "${RELEASE_STAGING}" -c core.hooksPath=/dev/null remote add origin "${HERMES_REPOSITORY}"
git -C "${RELEASE_STAGING}" -c core.hooksPath=/dev/null fetch -q --depth 1 \
    origin "refs/tags/${HERMES_TAG}"
git -C "${RELEASE_STAGING}" -c core.hooksPath=/dev/null checkout -q --detach FETCH_HEAD
[[ "$(git -C "${RELEASE_STAGING}" rev-parse HEAD)" == "${HERMES_COMMIT}" ]] \
    || die "Hermes tag does not resolve to the audited commit"
[[ -z "$(git -C "${RELEASE_STAGING}" status --porcelain --untracked-files=no)" ]] \
    || die "Hermes release checkout is unexpectedly dirty"

log "Resolving only the locked core and Telegram dependency graph"
UV_PROJECT_ENVIRONMENT="${RELEASE_STAGING}/.venv" \
    "${UV_BIN}" sync --locked --no-dev --extra messaging --python /usr/bin/python3 \
    --project "${RELEASE_STAGING}"
version_output="$("${RELEASE_STAGING}/.venv/bin/hermes" --version)"
[[ "${version_output}" == *"${HERMES_VERSION}"* ]] \
    || die "installed Hermes version is not ${HERMES_VERSION}"

log "Writing a schema-valid, least-privilege Hermes configuration"
"${RELEASE_STAGING}/.venv/bin/python" - "${BOOTSTRAP_JSON}" "${HERMES_HOME}" \
    "${HERMES_WORKSPACE}" <<'PY'
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import yaml

bootstrap_path, home_raw, workspace = sys.argv[1:]
home = Path(home_raw)
data = json.loads(Path(bootstrap_path).read_text(encoding="utf-8"))

custom_providers = []
if data.get("GROQ_API_KEY"):
    custom_providers.append({
        "name": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
    })

config = {
    "model": {
        "default": data["HERMES_MODEL"],
        "provider": data["HERMES_MODEL_PROVIDER"],
    },
    "custom_providers": custom_providers,
    "fallback_providers": [],
    "max_concurrent_sessions": 2,
    "max_live_sessions": 4,
    "agent": {
        "api_max_retries": 1,
        "gateway_timeout": 1800,
        "restart_drain_timeout": 0,
    },
    "terminal": {
        "backend": "local",
        "cwd": workspace,
        "timeout": 180,
    },
    "approvals": {
        "mode": "manual",
        "timeout": 60,
        "cron_mode": "deny",
    },
    "memory": {
        "memory_enabled": True,
        "user_profile_enabled": True,
        "write_approval": True,
    },
    "skills": {
        "external_dirs": [],
        "template_vars": True,
        "inline_shell": False,
        "guard_agent_created": True,
        "write_approval": True,
    },
}
if data["HERMES_MODEL_PROVIDER"] == "openrouter":
    config["provider_routing"] = {
        "sort": "throughput",
        "require_parameters": True,
        "data_collection": "deny",
    }

env_keys = (
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ALLOWED_USERS",
    "HERMES_API_KEY",
    "ATLAS_DASHBOARD_URL",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
)
env_lines = [
    f"{key}={json.dumps(data[key], ensure_ascii=False)}"
    for key in env_keys
    if data.get(key)
]

soul = """# Hermes — peer executor for Atlas Core

You are Hermes Agent running as an optional, untrusted peer of Atlas Core.
Atlas remains the authority for local capabilities, governance and the Merkle
audit ledger. Use the repository-owned `atlas-twin` skill for every Atlas
request; never construct HMAC signatures manually and never reveal secrets.

Do not claim that Atlas or any provider is reachable until a live probe proves
it in the current session. A refusal from Atlas is final and must not be routed
around. Destructive or high-sensitivity actions require human approval.
"""

def atomic_write(path: Path, payload: str, mode: int) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise

atomic_write(
    home / "config.yaml",
    yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
    0o600,
)
atomic_write(home / ".env", "\n".join(env_lines) + "\n", 0o600)
atomic_write(home / "SOUL.md", soul, 0o600)
PY

skill_target="${HERMES_HOME}/skills/atlas-twin"
[[ ! -L "${skill_target}" ]] || die "refusing symlinked atlas-twin skill directory"
if [[ -d "${skill_target}" ]]; then
    mv -- "${skill_target}" "${skill_target}.previous.$(date -u +%Y%m%dT%H%M%SZ)"
fi
install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0700 "${skill_target}"
install -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0600 \
    "${SKILL_SOURCE}/SKILL.md" "${skill_target}/SKILL.md"
install -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0700 \
    "${SKILL_SOURCE}/atlas_twin.py" "${skill_target}/atlas_twin.py"
chown -hR "${SERVICE_USER}:${SERVICE_GROUP}" "${SERVICE_HOME}"
chmod 0600 "${HERMES_HOME}/.env" "${HERMES_HOME}/config.yaml" "${HERMES_HOME}/SOUL.md"
# The service may create approved user skills, but the Atlas transport client
# itself is repository-owned and mounted read-only in the service namespace.
chown -hR root:"${SERVICE_GROUP}" "${skill_target}"
chmod 0750 "${skill_target}" "${skill_target}/atlas_twin.py"
chmod 0640 "${skill_target}/SKILL.md"

if [[ -e "${RELEASE_PATH}" || -L "${RELEASE_PATH}" ]]; then
    [[ ! -L "${RELEASE_PATH}" && -d "${RELEASE_PATH}" ]] \
        || die "existing release path is not a real directory"
    mv -- "${RELEASE_PATH}" "${RELEASE_PATH}.previous.$(date -u +%Y%m%dT%H%M%SZ)"
fi
mv -- "${RELEASE_STAGING}" "${RELEASE_PATH}"
RELEASE_STAGING=""
chown -hR root:root "${RELEASE_PATH}"
chmod -R go-w "${RELEASE_PATH}"

log "Installing the system service with a read-only host filesystem"
temporary_unit="$(mktemp /etc/systemd/system/.hermes-agent.service.XXXXXX)"
cat >"${temporary_unit}" <<'UNIT'
[Unit]
Description=Hermes Agent peer for Atlas Core
Documentation=https://github.com/NousResearch/hermes-agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=hermes
Group=hermes
WorkingDirectory=/var/lib/hermes/workspace
Environment=HOME=/var/lib/hermes
Environment=HERMES_HOME=/var/lib/hermes/.hermes
Environment=PYTHONDONTWRITEBYTECODE=1
EnvironmentFile=/var/lib/hermes/.hermes/.env
ExecStart=/opt/hermes-agent/.venv/bin/hermes gateway run
Restart=on-failure
RestartSec=10
TimeoutStopSec=30
KillMode=mixed
UMask=0077

NoNewPrivileges=true
CapabilityBoundingSet=
AmbientCapabilities=
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
ProtectClock=true
ProtectHostname=true
RestrictSUIDSGID=true
RestrictRealtime=true
RestrictNamespaces=true
LockPersonality=true
RemoveIPC=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadOnlyPaths=/opt/hermes-agent
ReadWritePaths=/var/lib/hermes
BindReadOnlyPaths=/var/lib/hermes/.hermes/skills/atlas-twin

[Install]
WantedBy=multi-user.target
UNIT
chmod 0644 "${temporary_unit}"
mv -- "${temporary_unit}" "${SERVICE_PATH}"
systemd-analyze verify "${SERVICE_PATH}"
systemctl daemon-reload

log "Validating configuration through the pinned Hermes CLI"
runuser -u "${SERVICE_USER}" -- env HOME="${SERVICE_HOME}" HERMES_HOME="${HERMES_HOME}" \
    "${RELEASE_PATH}/.venv/bin/hermes" config get model >/dev/null

systemctl enable hermes-agent.service
systemctl restart hermes-agent.service
ready=0
for _attempt in $(seq 1 30); do
    if systemctl is-active --quiet hermes-agent.service; then
        ready=1
        break
    fi
    sleep 1
done
if [[ ${ready} -ne 1 ]]; then
    journalctl -u hermes-agent.service --no-pager -n 50 >&2
    die "hermes-agent.service did not become active"
fi
sleep 3
if ! systemctl is-active --quiet hermes-agent.service; then
    journalctl -u hermes-agent.service --no-pager -n 50 >&2
    die "hermes-agent.service exited during the stability window"
fi

log "Hermes ${HERMES_VERSION} is active from audited commit ${HERMES_COMMIT}"
log "The Atlas twin skill is installed; provider and twin reachability remain unverified until live probes pass"
