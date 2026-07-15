"""Tests para scripts/daemon_idle_guard.sh (plan F4.4, toasty-hatching-pillow.md).

Guarda barata cableada en el hook SessionStart (mismo mecanismo que
capability_route_hook.sh en .claude/settings.json): si atlas-core.service
lleva > 24h inactivo, imprime UNA línea de aviso a stdout; si está activo o
inactivo desde hace menos de 24h, permanece en silencio.

Aislamiento: `systemctl` se mockea creando un ejecutable falso en
tmp_path/bin y anteponiéndolo al PATH — el script real, el daemon real y
`.env` real nunca se tocan. Nunca se invoca start/stop/restart, ni real ni
mockeado (la guarda solo hace is-active / show, de solo lectura).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "daemon_idle_guard.sh"
SERVICE_PATH = REPO_ROOT / "scripts" / "atlas-core.service"
INSTALLER_PATH = REPO_ROOT / "scripts" / "install_atlas_systemd.sh"

UNIT = "atlas-core.service"

_MOCK_SYSTEMCTL_TEMPLATE = """\
#!/usr/bin/env bash
# Mock de systemctl para tests de daemon_idle_guard.sh — solo entiende
# `is-active` y `show -p InactiveEnterTimestamp --value`, ambos read-only.
set -euo pipefail
if [ "$1" = "--user" ] && [ "$2" = "is-active" ]; then
  echo "{state}"
  exit 0
fi
if [ "$1" = "--user" ] && [ "$2" = "is-enabled" ]; then
  echo "enabled"
  exit 0
fi
if [ "$1" = "--user" ] && [ "$2" = "show" ]; then
  echo "{inactive_ts}"
  exit 0
fi
echo "unexpected mock systemctl invocation: $*" >&2
exit 1
"""

_MOCK_JOURNALCTL_TEMPLATE = """\
#!/usr/bin/env bash
set -euo pipefail
if [ -n "{journal_epoch}" ]; then
  echo "{journal_epoch}.000000 atlas test"
fi
"""


def _install_mock_systemctl(
    tmp_path: Path,
    *,
    state: str,
    inactive_ts: str,
    journal_epoch: str = "",
) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    mock = bin_dir / "systemctl"
    mock.write_text(
        _MOCK_SYSTEMCTL_TEMPLATE.format(state=state, inactive_ts=inactive_ts),
        encoding="utf-8",
    )
    mock.chmod(0o755)
    journalctl = bin_dir / "journalctl"
    journalctl.write_text(
        _MOCK_JOURNALCTL_TEMPLATE.format(journal_epoch=journal_epoch),
        encoding="utf-8",
    )
    journalctl.chmod(0o755)
    return bin_dir


def _run(bin_dir: Path, **extra_env: str) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
    }
    env.update(extra_env)
    return subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _timestamp_hours_ago(hours: float) -> str:
    """Formato que systemd usa en InactiveEnterTimestamp, parseable por `date -d`."""
    epoch = subprocess.run(
        ["date", "-d", f"-{hours} hours", "+%Y-%m-%d %H:%M:%S"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return epoch


class TestActiveIsSilent:
    def test_active_service_prints_nothing(self, tmp_path: Path) -> None:
        bin_dir = _install_mock_systemctl(
            tmp_path, state="active", inactive_ts="n/a"
        )
        result = _run(bin_dir)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""


class TestSystemdHardening:
    def test_service_uses_private_umask_and_no_new_privileges(self) -> None:
        unit = SERVICE_PATH.read_text(encoding="utf-8")
        assert "UMask=0077" in unit
        assert "NoNewPrivileges=true" in unit

    def test_installer_has_bounded_readiness_gate(self) -> None:
        installer = INSTALLER_PATH.read_text(encoding="utf-8")
        assert "sleep 8" not in installer
        assert "systemctl --user is-active --quiet" in installer
        assert "exit 1" in installer


class TestInactiveUnder24hIsSilent:
    def test_inactive_since_one_hour_ago_prints_nothing(self, tmp_path: Path) -> None:
        inactive_ts = _timestamp_hours_ago(1)
        bin_dir = _install_mock_systemctl(
            tmp_path, state="inactive", inactive_ts=inactive_ts
        )
        result = _run(bin_dir)
        assert result.returncode == 0, result.stderr
        assert result.stdout == "", (
            f"esperaba silencio con <24h inactivo, obtuvo: {result.stdout!r}"
        )


class TestInactiveOver24hWarns:
    def test_inactive_since_25_hours_ago_prints_one_warning_line(
        self, tmp_path: Path
    ) -> None:
        inactive_ts = _timestamp_hours_ago(25)
        bin_dir = _install_mock_systemctl(
            tmp_path, state="inactive", inactive_ts=inactive_ts
        )
        result = _run(bin_dir)
        assert result.returncode == 0, result.stderr
        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        assert len(lines) == 1, (
            f"esperaba EXACTAMENTE una linea de aviso, obtuvo {len(lines)}: {lines}"
        )
        assert UNIT in lines[0]
        assert "inactivo" in lines[0]

    def test_threshold_is_configurable_via_env(self, tmp_path: Path) -> None:
        """Umbral parametrizable (para no depender de esperar 24h reales en CI)."""
        inactive_ts = _timestamp_hours_ago(2)
        bin_dir = _install_mock_systemctl(
            tmp_path, state="inactive", inactive_ts=inactive_ts
        )
        result = _run(bin_dir, DAEMON_IDLE_GUARD_THRESHOLD_SECONDS="3600")
        assert result.returncode == 0, result.stderr
        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        assert len(lines) == 1, (
            f"con umbral de 1h y 2h inactivo, esperaba aviso; obtuvo: {result.stdout!r}"
        )


class TestNeverActiveIsSilent:
    def test_no_inactive_timestamp_prints_nothing(self, tmp_path: Path) -> None:
        """Unit nunca arrancado (systemd no reporta InactiveEnterTimestamp): silencio,
        no un falso aviso."""
        bin_dir = _install_mock_systemctl(tmp_path, state="inactive", inactive_ts="n/a")
        result = _run(bin_dir)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""

    def test_empty_systemd_timestamp_uses_last_journal_activity(
        self, tmp_path: Path
    ) -> None:
        journal_epoch = subprocess.run(
            ["date", "-d", "-25 hours", "+%s"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        bin_dir = _install_mock_systemctl(
            tmp_path,
            state="inactive",
            inactive_ts="",
            journal_epoch=journal_epoch,
        )
        result = _run(bin_dir)
        assert result.returncode == 0, result.stderr
        assert UNIT in result.stdout
        assert "journal" in result.stdout
