"""
Capa 3 — Backend de ejecución de workers (ADR-046).

Substrato GENERAL de ejecución: un `WorktreeWorker` corre en un git worktree
desechable (aislamiento de código), produce un diff, lo valida EN su worktree y
emite un `Artifact(PATCH)`. No es un sistema de mantenimiento: el worker de
mantenimiento es solo la primera instancia concreta. El mismo backend sirve a
workers de seguridad, research, codegen de feature, etc. — cada dominio es un
`produce_diff` + un verificador distintos.

Invariante de seguridad (ver ADR-045/046): el worker **no escribe Merkle ni
toca el `ATLAS_HOME` vivo**. Es un productor puro; el coordinador (único
escritor, capa 3) es quien registra. El worktree es detached sobre un commit
base: no interfiere con la rama viva ni con la cadena Merkle.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from atlas.core.verify import Artifact, ArtifactKind, CostTier, Evidence

# Variables que git EXPORTA cuando corre dentro de un hook (pre-commit, etc.).
# Si no se limpian, secuestran cualquier `git` hijo hacia el repo del hook en
# vez del worktree objetivo — el bug que generó los worktrees huérfanos y la
# flakiness del pre-commit (2026-06-13). El backend corre precisamente bajo
# hooks, así que esto NO es defensivo de más.
_GIT_HOOK_ENV_VARS = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_PREFIX",
    "GIT_COMMON_DIR",
)


def _clean_git_env() -> dict[str, str]:
    env = os.environ.copy()
    for var in _GIT_HOOK_ENV_VARS:
        env.pop(var, None)
    return env


class WorktreeManager:
    """Ciclo de vida de worktrees git desechables. Reusa el patrón de
    ColdUpdate (`git worktree add --detach`). Aislamiento de código, no de
    Merkle: los worktrees comparten el object store pero están en detached HEAD
    sobre el commit base, así que no tocan la rama viva."""

    def __init__(self, root: Path, *, worktrees_dir: Path | None = None) -> None:
        self._root = root.resolve()
        self._dir = (worktrees_dir or (self._root / ".atlas-worktrees")).resolve()

    def create(self, name: str, *, base_ref: str = "HEAD") -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / name
        result = subprocess.run(
            ["git", "worktree", "add", "--detach", str(path), base_ref],
            cwd=self._root,
            env=_clean_git_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git worktree add falló: {result.stderr.strip()[:300]}")
        return path

    def teardown(self, path: Path) -> None:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(path)],
            cwd=self._root,
            env=_clean_git_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        # Defensa: si git no lo quitó (p.ej. metadata divergente), borra el dir
        # y poda. Nunca toca el root.
        if path.exists() and path.resolve() != self._root and self._dir in path.resolve().parents:
            shutil.rmtree(path, ignore_errors=True)
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=self._root,
            env=_clean_git_env(),
            capture_output=True,
            text=True,
            check=False,
        )

    @contextmanager
    def session(self, name: str, *, base_ref: str = "HEAD") -> Iterator[Path]:
        path = self.create(name, base_ref=base_ref)
        try:
            yield path
        finally:
            self.teardown(path)


class WorktreeWorker:
    """Worker que produce y valida en un worktree aislado. Conforma el Protocol
    `Worker` de la capa 3. Las funciones de cambio y validación se inyectan: el
    de mantenimiento usará un transform determinista o la cascada; en tests, un
    fake — sin git ni suite reales en la lógica del worker."""

    def __init__(
        self,
        worker_id: str,
        domain: str,
        *,
        manager: WorktreeManager,
        produce_diff: Callable[[Any, Path], str],
        validate: Callable[[Path, str], Evidence],
        allowed_paths: tuple[str, ...] = (),
        base_ref: str = "HEAD",
        cost: CostTier = CostTier.SUITE,
    ) -> None:
        self._worker_id = worker_id
        self._domain = domain
        self._manager = manager
        self._produce_diff = produce_diff
        self._validate = validate
        self._allowed_paths = allowed_paths
        self._base_ref = base_ref
        self._cost = cost

    @property
    def worker_id(self) -> str:
        return self._worker_id

    @property
    def domain(self) -> str:
        return self._domain

    def produce(self, task: Any) -> Artifact:
        """Crea worktree → produce diff → valida en el worktree → teardown.
        El resultado de la validación cara viaja en metadata; el coordinador
        re-verifica barato (UnifiedDiffVerifier) y muestrea (audit_sample)."""
        with self._manager.session(self._worker_id, base_ref=self._base_ref) as path:
            diff = self._produce_diff(task, path)
            validation = self._validate(path, diff)
        return Artifact(
            kind=ArtifactKind.PATCH,
            payload={"diff": diff},
            producer_cost=self._cost,
            metadata={
                "worker_id": self._worker_id,
                "domain": self._domain,
                "allowed_paths": list(self._allowed_paths),
                "worktree_validation": validation.to_dict(),
            },
        )
