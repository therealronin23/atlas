"""Operability contracts for the 24-hour audit runner and CI workflow.

The runner tests execute against an isolated synthetic repository with fake
``atlas`` and ``python`` executables.  They never start the live self-audit,
touch the real Atlas workspace, or run the project test suite.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
RUNNER = REPO_ROOT / "scripts" / "run_24h_autonomous_audit.sh"
AUDIT_COMPLETE = REPO_ROOT / "scripts" / "audit_complete.py"
AUDIT_UNIT = REPO_ROOT / "scripts" / "atlas-audit-24h.service"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _load_audit_complete() -> ModuleType:
    spec = importlib.util.spec_from_file_location("audit_complete_under_test", AUDIT_COMPLETE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_runner_environment(tmp_path: Path, *, fail_on: str = "") -> dict[str, str]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    atlas = fake_bin / "atlas"
    atlas.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" >> \"$ATLAS_CALLS\"\n"
        "if [[ -n \"${ATLAS_FAIL_ON:-}\" && \"$*\" == *\"$ATLAS_FAIL_ON\"* ]]; then\n"
        "  exit 23\n"
        "fi\n"
        "if [[ \"${1:-}\" == reality ]]; then printf '{}\\n'; fi\n",
        encoding="utf-8",
    )
    atlas.chmod(0o755)
    python = fake_bin / "python"
    python.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" >> \"$PYTHON_CALLS\"\n",
        encoding="utf-8",
    )
    python.chmod(0o755)

    root = tmp_path / "repo"
    root.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    return {
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        "HOME": str(home),
        "ATLAS_CORE_ROOT": str(root),
        "ATLAS_AUDIT_HOME": str(root / ".atlas-audit-home"),
        "ATLAS_CALLS": str(tmp_path / "atlas-calls.txt"),
        "PYTHON_CALLS": str(tmp_path / "python-calls.txt"),
        "ATLAS_FAIL_ON": fail_on,
    }


def _run_isolated_runner(
    tmp_path: Path, *, fail_on: str = ""
) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    env = _fake_runner_environment(tmp_path, fail_on=fail_on)
    result = subprocess.run(
        ["bash", "-c", 'umask 000; exec bash "$1"', "audit-runner-test", str(RUNNER)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return result, env


def test_runner_uses_cheap_reality_checks_and_one_complete_audit(tmp_path: Path) -> None:
    result, env = _run_isolated_runner(tmp_path)

    assert result.returncode == 0, result.stderr
    atlas_calls = Path(env["ATLAS_CALLS"]).read_text(encoding="utf-8").splitlines()
    reality_calls = [call for call in atlas_calls if call.startswith("reality ")]
    assert reality_calls == ["reality --strict --json", "reality --strict --json"]
    assert not any("--run-checks" in call for call in reality_calls)
    python_calls = Path(env["PYTHON_CALLS"]).read_text(encoding="utf-8").splitlines()
    assert python_calls.count("scripts/audit_complete.py") == 1


def test_autonomous_audit_never_auto_enables_live_external_smokes() -> None:
    raw = RUNNER.read_text(encoding="utf-8")

    assert 'export ATLAS_AUDIT_LIVE="${ATLAS_AUDIT_LIVE:-1}"' not in raw
    audit_raw = AUDIT_COMPLETE.read_text(encoding="utf-8")
    assert "twin_e2e_smoke.py" in audit_raw
    assert "verify_twin_pairing.sh" in audit_raw
    assert "operational_smoke.py" not in audit_raw


def test_runner_removes_pid_file_after_failure(tmp_path: Path) -> None:
    result, env = _run_isolated_runner(tmp_path, fail_on="security-audit")

    assert result.returncode == 23
    pid_file = Path(env["ATLAS_CORE_ROOT"]) / "logs" / "autonomous_audit_24h.pid"
    assert not pid_file.exists()


def test_runner_artifacts_are_private_even_with_permissive_caller_umask(
    tmp_path: Path,
) -> None:
    result, env = _run_isolated_runner(tmp_path)

    assert result.returncode == 0, result.stderr
    root = Path(env["ATLAS_CORE_ROOT"])
    log = next((root / "logs").glob("autonomous_audit_24h_*.log"))
    assert log.stat().st_mode & 0o777 == 0o600
    assert (root / ".atlas-audit-home").stat().st_mode & 0o777 == 0o700


def test_complete_audit_partitions_pytest_into_bounded_processes(tmp_path: Path) -> None:
    module = _load_audit_complete()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    files = []
    for index in range(5):
        path = tests_dir / f"test_{index}.py"
        path.write_text("def test_ok(): assert True\n", encoding="utf-8")
        files.append(path)

    commands: list[list[str]] = []

    def fake_run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> dict[str, Any]:
        commands.append(cmd)
        return {"cmd": " ".join(cmd), "exit": 0, "stdout_tail": "", "stderr_tail": ""}

    module.run = fake_run
    checks = module.run_pytest_batches(
        tmp_path,
        {},
        files,
        marker="not computer_use",
        batch_size=2,
    )

    assert len(checks) == 3
    assert len(commands) == 3
    for command in commands:
        test_paths = [arg for arg in command if arg.endswith(".py")]
        assert 1 <= len(test_paths) <= 2
        assert "tests/" not in command


def test_complete_audit_browser_candidates_are_an_honest_superset(tmp_path: Path) -> None:
    module = _load_audit_complete()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    browser = tests_dir / "test_browser.py"
    browser.write_text("pytestmark = pytest.mark.computer_use\n", encoding="utf-8")
    mixed = tests_dir / "test_mixed.py"
    mixed.write_text("@pytest.mark.computer_use\ndef test_browser(): pass\n", encoding="utf-8")
    core = tests_dir / "test_core.py"
    core.write_text("def test_core(): pass\n", encoding="utf-8")

    assert module.discover_computer_use_test_files(tmp_path) == [browser, mixed]


def test_complete_audit_bounds_each_subprocess(tmp_path: Path) -> None:
    module = _load_audit_complete()
    started = time.monotonic()

    check = module.run(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        tmp_path,
        {"ATLAS_AUDIT_CHECK_TIMEOUT_SECONDS": "1"},
    )

    assert check["exit"] == 124
    assert "timed out" in check["stderr_tail"]
    assert time.monotonic() - started < 1.8


def test_audit_unit_keeps_resource_cap_but_hardens_process_lifecycle() -> None:
    unit = AUDIT_UNIT.read_text(encoding="utf-8")

    assert "MemoryMax=4G" in unit
    assert "KillMode=control-group" in unit
    assert "UMask=0077" in unit
    assert "NoNewPrivileges=true" in unit
    assert "TimeoutStartSec=27h" in unit


def test_ci_uses_locked_matrix_browser_marker_and_isolated_wheel_smoke() -> None:
    raw = CI_WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(raw)
    jobs = workflow["jobs"]

    matrix = jobs["test-and-types"]["strategy"]["matrix"]["python-version"]
    assert matrix == ["3.11", "3.12"]
    assert "uv lock --check" in raw
    assert "uv sync --frozen --extra dev" in raw
    assert "apt-get install -y --no-install-recommends apparmor bubblewrap" in raw
    assert "profile atlas-ci-bwrap /usr/bin/bwrap flags=(default_allow)" in raw
    assert "apparmor_restrict_unprivileged_userns)\" = \"1\"" in raw
    assert "uv export --frozen --extra dev --no-emit-project" in raw
    assert "pip-audit --strict" in raw
    assert "atlas-audit-requirements.txt" in raw
    assert "--extra computer-use" in raw
    assert re.search(r"pytest\s+tests(?:/|\s).*?-m\s+[\"']?computer_use", raw, re.DOTALL)
    assert "uv build --wheel" in raw
    assert "uv export --frozen --no-dev --no-emit-project" in raw
    assert "--no-hashes" not in raw
    assert "--no-deps \"$wheel\"" in raw
    assert "atlas_data_root" in raw
    assert ".venv-wheel-smoke/bin/atlas\" --help" in raw

    uses = re.findall(r"^\s*- uses:\s*([^\s]+)", raw, re.MULTILINE)
    assert uses
    assert all(re.search(r"@[0-9a-f]{40}$", action) for action in uses)
