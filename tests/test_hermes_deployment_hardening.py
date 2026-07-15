"""Static regression tests for the Hermes VPS deployment trust boundary."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"


def _read(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8")


def test_installer_is_pinned_locked_and_never_runs_mutable_installers() -> None:
    raw = _read("install_hermes_agent_vps.sh")
    assert "9de9c25f620ff7f1ce0fd5457d596052d5159596" in raw
    assert "v2026.7.7.2" in raw
    assert 'UV_VERSION="0.11.21"' in raw
    assert "053045e1e69ec77358fd44f2ef2cacb768a22d50f433e213624f0157ffbbc883" in raw
    assert re.search(r'\$\{UV_BIN\}"\s+sync\s+--locked', raw)
    assert "--extra messaging" in raw
    assert "pip install" not in raw
    assert not re.search(r"curl\b[^\n]*\|\s*(?:ba)?sh", raw)
    assert "ollama.com/install.sh" not in raw


def test_installer_uses_a_dedicated_hardened_service_user() -> None:
    raw = _read("install_hermes_agent_vps.sh")
    required = [
        "User=hermes",
        "Group=hermes",
        "NoNewPrivileges=true",
        "ProtectSystem=strict",
        "ProtectHome=true",
        "PrivateTmp=true",
        "PrivateDevices=true",
        "CapabilityBoundingSet=",
        "RestrictSUIDSGID=true",
        "UMask=0077",
        "ReadWritePaths=/var/lib/hermes",
        "BindReadOnlyPaths=/var/lib/hermes/.hermes/skills/atlas-twin",
    ]
    for directive in required:
        assert directive in raw
    assert "--accept-hooks" not in raw
    assert "User=root" not in raw
    assert "/root/.hermes" not in raw
    assert "HERMES_API_KEY=${" not in raw
    assert "echo \"HERMES_API_KEY=" not in raw
    assert "|| true" not in raw


def test_remote_wrapper_never_sources_or_places_secrets_in_ssh_argv() -> None:
    raw = _read("deploy_hermes_vps_oneshot.sh")
    assert 'source "$ENV_FILE"' not in raw
    assert "bootstrap.json" in raw
    assert "StrictHostKeyChecking=yes" in raw
    assert "StrictHostKeyChecking=accept-new" not in raw
    for secret in (
        "TELEGRAM_BOT_TOKEN",
        "OPENROUTER_API_KEY",
        "GROQ_API_KEY",
        "HERMES_API_KEY",
    ):
        assert f"${{{secret}}}" not in raw
    assert "scp" in raw
    assert "HERMES_API_KEY" in raw  # generated/stored locally, never printed
    assert "imprime el HERMES_API_KEY" not in raw
    assert "100.64.0.0/10" in raw
    assert '.endswith(".ts.net")' in raw


def test_legacy_reconfiguration_and_unlock_paths_fail_closed() -> None:
    stub_installer = _read("install_hermes_vps.sh")
    reconfigure = _read("reconfigure_hermes_vps.sh")
    unlock = _read("hermes_unlock_skills.sh")
    assert "SUPERSEDED" in stub_installer
    assert "curl" not in stub_installer
    assert "docker" not in stub_installer.lower()
    assert "SUPERSEDED" in reconfigure
    assert "SUPERSEDED" in unlock
    assert "skills install" not in unlock
    assert "--force" not in unlock
    assert "/root/.hermes" not in unlock


def test_legacy_audit_skill_delegates_to_the_hardened_single_client() -> None:
    client = (SCRIPTS / "hermes_skill_atlas_audit" / "atlas_audit.py").read_text(
        encoding="utf-8"
    )
    heartbeat = (SCRIPTS / "hermes_skill_atlas_audit" / "atlas_heartbeat.sh").read_text(
        encoding="utf-8"
    )
    assert "skills/atlas-twin" in client.replace('" / "', "/") or "atlas-twin" in client
    assert "urlopen" not in client
    assert "/root/.hermes" not in client
    assert "source " not in heartbeat
    assert "grep" not in heartbeat
    assert "/root/.hermes" not in heartbeat


def test_pairing_verifier_checks_the_real_signed_skill_over_tailnet() -> None:
    raw = _read("verify_twin_pairing.sh")
    assert "VPS_HOST_PUB" not in raw
    assert "178.105.216.187" not in raw
    assert "hermes-agent.service" in raw
    assert "/var/lib/hermes/.hermes/skills/atlas-twin/atlas_twin.py" in raw
    assert " health" in raw
    assert "atlas_twin" not in raw.lower() or "tool atlas_twin" not in raw.lower()
    assert "HERMES_API_KEY=" not in raw


def test_all_hermes_operational_shell_scripts_parse() -> None:
    for name in (
        "install_hermes_agent_vps.sh",
        "install_hermes_vps.sh",
        "deploy_hermes_vps_oneshot.sh",
        "reconfigure_hermes_vps.sh",
        "hermes_unlock_skills.sh",
        "verify_twin_pairing.sh",
    ):
        result = subprocess.run(
            ["bash", "-n", str(SCRIPTS / name)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"{name}: {result.stderr}"
