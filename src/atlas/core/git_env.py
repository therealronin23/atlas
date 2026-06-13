"""
Saneo del entorno git heredado.

Cuando un proceso corre dentro de un hook git (pre-commit, post-commit, etc.),
git EXPORTA `GIT_DIR`, `GIT_INDEX_FILE`, `GIT_WORK_TREE`, etc. al entorno.
Cualquier `git` hijo que no limpie esas variables se redirige al repo del hook
en vez del repo/worktree objetivo — bug de secuestro que generó worktrees
huérfanos y flakiness del pre-commit (2026-06-13). Todo subproceso git que
opere sobre un repo determinado por `cwd` debe pasar este entorno saneado.
"""

from __future__ import annotations

import os

_GIT_HOOK_ENV_VARS = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_PREFIX",
    "GIT_COMMON_DIR",
)


def clean_git_env() -> dict[str, str]:
    """Copia de ``os.environ`` sin las variables que git inyecta en hooks."""
    env = os.environ.copy()
    for var in _GIT_HOOK_ENV_VARS:
        env.pop(var, None)
    return env
