"""Security contract for dotenv loading in autonomous operator scripts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
LOADER = REPO / "scripts" / "safe_dotenv.py"


def _run(env_file: Path, code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LOADER), str(env_file), "--", sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


def test_dotenv_is_parsed_as_literal_data_without_shell_expansion(tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist"
    env_file = tmp_path / ".env"
    literal = f"$(touch {marker})"
    env_file.write_text(f"SAFE_VALUE='{literal}'\nexport SECOND=value # comment\n", encoding="utf-8")
    env_file.chmod(0o600)

    result = _run(
        env_file,
        "import os; print(os.environ['SAFE_VALUE']); print(os.environ['SECOND'])",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [literal, "value"]
    assert not marker.exists()


def test_dotenv_rejects_permissive_permissions(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET=value\n", encoding="utf-8")
    env_file.chmod(0o644)

    result = _run(env_file, "print('must not run')")

    assert result.returncode != 0
    assert "permissions" in result.stderr.lower()
    assert "must not run" not in result.stdout


def test_dotenv_rejects_duplicate_keys_without_printing_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET=first-secret\nSECRET=second-secret\n", encoding="utf-8")
    env_file.chmod(0o600)

    result = _run(env_file, "print('must not run')")

    assert result.returncode != 0
    assert "duplicate" in result.stderr.lower()
    assert "first-secret" not in result.stderr
    assert "second-secret" not in result.stderr


def test_autonomous_scripts_never_source_dotenv_as_shell_code() -> None:
    names = (
        "run_24h_autonomous_audit.sh",
        "update-knowledge-graph.sh",
        "update-knowledge-graph-rag.sh",
        "run-graphify-quality-pipeline.sh",
        "graphify-monitor-and-switch.sh",
        "hermes_local.sh",
    )
    for name in names:
        raw = (REPO / "scripts" / name).read_text(encoding="utf-8")
        assert 'source ".env"' not in raw
        assert 'source "${ROOT_DIR}/.env"' not in raw
        assert "safe_dotenv.py" in raw
