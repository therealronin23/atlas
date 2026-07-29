"""Import-boundary regression coverage for Atlas Sentinel."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_sentinel_imports_directly_in_a_fresh_interpreter() -> None:
    """Security callers must not depend on importing ``atlas.mcp`` first."""
    repo_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from atlas.security.sentinel_gate import SentinelGate; print(SentinelGate.__name__)",
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "SentinelGate"
