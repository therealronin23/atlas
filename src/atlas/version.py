from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _read_version() -> str:
    try:
        return version("atlas-core")
    except PackageNotFoundError:
        # Bare source checkout before installation. Installed wheels/editables
        # always use distribution metadata and never depend on repository files.
        pyproject = _project_root() / "pyproject.toml"
        return str(
            tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
        )


__version__ = _read_version()
