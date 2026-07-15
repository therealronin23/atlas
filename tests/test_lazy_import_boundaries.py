"""Cheap commands must not import the heavyweight LiteLLM SDK."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "atlas.interfaces.cli",
        "atlas.core.inference_hub",
        "atlas.memory.embeddings",
    ],
)
def test_import_does_not_load_litellm(module: str) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = "src"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; import {module}; "
            "raise SystemExit(1 if 'litellm' in sys.modules else 0)",
        ],
        cwd=os.getcwd(),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
