"""
Wiring de las 4 técnicas restantes en AtlasCoder — todo opt-in, aditivo.
#5 (token_budget): recorta institutional_section+avoid_section+repo_map por
    presupuesto si excede, priorizando avoid_section (lecciones) > repo_map.
#16 (git_autocommit): commitea automáticamente tras éxito si auto_commit=True.
#11/#21: verificados directamente en sus propios módulos (conditional_rules,
    history_compactor) — no requieren wiring adicional en AtlasCoder, son
    utilidades standalone que el llamador usa según su caso (documentado).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

from atlas.core.atlas_coder import AtlasCoder


def _git_repo(tmp_path: Path) -> Path:
    repo = tmp_path
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "foo.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    return repo


def _sr(search: str, replace: str) -> str:
    return f"<<<<<<< SEARCH\n{search}\n=======\n{replace}\n>>>>>>> REPLACE"


def _make_hub(response_text: str):
    hub = MagicMock()
    resp = MagicMock()
    resp.success = True
    resp.text = response_text
    resp.error = None
    hub.infer.return_value = resp
    hub.infer_for_role.return_value = resp
    return hub


def test_auto_commit_creates_commit_on_success(tmp_path):
    repo = _git_repo(tmp_path)
    hub = _make_hub(_sr("x = 1", "x = 2"))

    coder = AtlasCoder(hub, repo_root=repo)
    result = coder.code(
        task="cambia x", context_files=["foo.py"], test_cmd=["true"],
        auto_commit=True,
    )

    assert result.success is True
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=repo, capture_output=True, text=True,
    ).stdout
    assert "[atlas-coder]" in log
    assert "cambia x" in log


def test_auto_commit_disabled_by_default(tmp_path):
    """Sin auto_commit=True (default False), no se commitea nada."""
    repo = _git_repo(tmp_path)
    hub = _make_hub(_sr("x = 1", "x = 2"))

    coder = AtlasCoder(hub, repo_root=repo)
    result = coder.code(task="cambia x", context_files=["foo.py"], test_cmd=["true"])

    assert result.success is True
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=repo, capture_output=True, text=True,
    ).stdout
    assert "[atlas-coder]" not in log
    assert log.strip() == "init"


def test_auto_commit_no_commit_on_failure(tmp_path):
    repo = _git_repo(tmp_path)
    hub = _make_hub(_sr("no_existe_nunca", "x"))

    coder = AtlasCoder(hub, repo_root=repo)
    coder.code(
        task="tarea que falla", context_files=["foo.py"], test_cmd=["false"],
        auto_commit=True, max_iterations=1,
    )

    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=repo, capture_output=True, text=True,
    ).stdout
    assert log.strip() == "init"  # sin commit nuevo
