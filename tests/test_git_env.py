"""Contrato de clean_git_env(): saneo del env git de hooks (2026-06-13).

Es el fix compartido por WorktreeManager (capa 3) y ColdUpdateManager: bajo un
hook git, GIT_DIR/GIT_INDEX_FILE secuestraban los `git` hijos hacia el repo del
hook. Ambos consumidores dependen de este contrato.
"""

from __future__ import annotations

from atlas.core.git_env import clean_git_env


def test_strips_all_hook_vars(monkeypatch) -> None:
    for var in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_PREFIX", "GIT_COMMON_DIR"):
        monkeypatch.setenv(var, "/algo/secuestrado")
    env = clean_git_env()
    for var in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_PREFIX", "GIT_COMMON_DIR"):
        assert var not in env


def test_preserves_other_env(monkeypatch) -> None:
    monkeypatch.setenv("GIT_DIR", "/x")
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("ATLAS_HOME", "/home/atlas")
    env = clean_git_env()
    assert env["PATH"] == "/usr/bin"
    assert env["ATLAS_HOME"] == "/home/atlas"
    assert "GIT_DIR" not in env


def test_noop_when_no_git_vars(monkeypatch) -> None:
    monkeypatch.delenv("GIT_DIR", raising=False)
    # No lanza ni inventa claves; es una copia saneada.
    assert "GIT_DIR" not in clean_git_env()
