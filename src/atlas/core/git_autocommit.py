"""Atlas Core — Git Autocommit (técnica #16, patrón Aider).

Commitea automáticamente los cambios de AtlasCoder tras un éxito, con un
marcador de autoría en el mensaje (para /undo seguro: solo revertir
commits que Atlas hizo).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__ = ["commit_changes", "is_atlas_commit"]

_MARKER = "[atlas-coder]"


def commit_changes(repo_root: Path, *, files_changed: list[str], task: str) -> str | None:
    """Añade y commitea files_changed con mensaje '[atlas-coder] task'.
    Sin archivos, no commitea (devuelve None). Devuelve el SHA del commit."""
    if not files_changed:
        return None
    subprocess.run(["git", "add", *files_changed], cwd=repo_root, check=True, capture_output=True)
    message = f"{_MARKER} {task[:72]}"
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo_root, check=True, capture_output=True)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def is_atlas_commit(repo_root: Path, sha: str) -> bool:
    """True si el commit sha tiene el marcador de autoría de Atlas."""
    result = subprocess.run(
        ["git", "log", "-1", "--pretty=%s", sha], cwd=repo_root, capture_output=True, text=True,
    )
    return result.stdout.startswith(_MARKER)
