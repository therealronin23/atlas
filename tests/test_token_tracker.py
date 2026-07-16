"""Operational regressions for the local provider token ledger."""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path


SOURCE = Path(__file__).resolve().parent.parent / "scripts" / "token-tracker.sh"


def _script(tmp_path: Path) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    target = scripts / SOURCE.name
    target.write_text(SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    target.chmod(0o755)
    return target


def _run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), *args],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )


def test_logged_tokens_are_numeric_and_reported_from_private_ledger(
    tmp_path: Path,
) -> None:
    script = _script(tmp_path)

    logged = _run(script, "log", "openrouter", "123", "synthetic-model")
    report = _run(script, "report")

    assert logged.returncode == 0, logged.stderr
    assert report.returncode == 0, report.stderr
    assert "123/500000 locally recorded tokens" in report.stdout
    assert "not provider billing" in report.stdout
    log_dir = tmp_path / "logs" / "token-tracking"
    log_file = next(log_dir.glob("openrouter-*.log"))
    assert stat.S_IMODE(log_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(log_file.stat().st_mode) == 0o600


def test_critical_budget_propagates_nonzero_exit_status(tmp_path: Path) -> None:
    script = _script(tmp_path)
    assert _run(script, "log", "anthropic", "195000", "synthetic").returncode == 0

    result = _run(script, "report")

    assert result.returncode == 2
    assert "CRITICAL" in result.stdout


def test_unknown_or_path_like_provider_is_rejected(tmp_path: Path) -> None:
    script = _script(tmp_path)

    result = _run(script, "log", "../../escape", "10", "model")

    assert result.returncode == 64
    assert "unknown provider" in result.stderr.lower()
    assert not (tmp_path / "escape").exists()


def test_nvidia_is_reported_as_unbudgeted_not_zero_percent(tmp_path: Path) -> None:
    script = _script(tmp_path)

    result = _run(script, "report")

    assert result.returncode == 0
    assert "nvidia: budget unknown" in result.stdout
    assert "nvidia: 0%" not in result.stdout
    assert "openai: budget unknown" in result.stdout
