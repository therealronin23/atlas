"""Regression tests for retired Graphify auto-switching helpers.

The historical monitor killed every matching process on the workstation and
selected external providers implicitly. The strict, single-writer pipeline is
the only supported semantic build entrypoint now.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    "name",
    [
        "graphify-monitor-and-switch.sh",
        "graphify-autoremediation.sh",
        "capture-llm-failures.sh",
    ],
)
def test_unsafe_graphify_automation_is_retired_fail_closed(
    name: str, tmp_path: Path
) -> None:
    source = REPO_ROOT / "scripts" / name
    result = subprocess.run(
        ["bash", str(source)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 64
    assert "retired" in result.stderr.lower()
    assert "--strict" in result.stderr
    assert not (tmp_path / "graphify-out").exists()


def test_retired_monitor_contains_no_global_process_kill() -> None:
    text = (REPO_ROOT / "scripts" / "graphify-monitor-and-switch.sh").read_text(
        encoding="utf-8"
    )

    assert "pgrep" not in text
    assert "kill " not in text
    assert "while true" not in text


def test_retired_failure_capture_contains_no_unbounded_tail() -> None:
    text = (REPO_ROOT / "scripts" / "capture-llm-failures.sh").read_text(
        encoding="utf-8"
    )

    assert "exit 64" in text
    assert "tail -n 0 -F" not in text
