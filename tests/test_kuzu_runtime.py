"""Regression coverage for Atlas's bounded embedded-Kuzu profile."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest


def test_kuzu_database_construction_is_centralized() -> None:
    """No Atlas source or test may silently request Kuzu's 8-TiB default."""
    root = Path(__file__).resolve().parents[1]
    allowed = root / "src" / "atlas" / "memory" / "kuzu_runtime.py"
    constructor = "kuzu" + ".Database("
    violations = [
        path.relative_to(root).as_posix()
        for tree in (root / "src" / "atlas", root / "tests")
        for path in sorted(tree.rglob("*.py"))
        if path != allowed and path != Path(__file__).resolve()
        and constructor in path.read_text(encoding="utf-8")
    ]

    assert violations == []


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="RLIMIT_AS regression is Linux-specific")
def test_bounded_kuzu_opener_runs_below_two_gib_of_address_space(tmp_path: Path) -> None:
    """The shared opener avoids Kuzu's unsafe 8-TiB virtual mmap default."""
    pytest.importorskip("kuzu")
    root = Path(__file__).resolve().parents[1]
    child_env = dict(os.environ)
    inherited_pythonpath = child_env.get("PYTHONPATH", "")
    child_env["PYTHONPATH"] = os.pathsep.join(
        item for item in (str(root / "src"), inherited_pythonpath) if item
    )
    script = """
import resource
import sys

import kuzu
from atlas.memory.kuzu_runtime import open_kuzu_database

limit = 2 * 1024 * 1024 * 1024
resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
database = open_kuzu_database(sys.argv[1])
connection = kuzu.Connection(database)
try:
    assert connection.execute('RETURN 1').get_next()[0] == 1
finally:
    connection.close()
    database.close()
"""

    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "bounded.kuzu")],
        check=False,
        capture_output=True,
        text=True,
        env=child_env,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
