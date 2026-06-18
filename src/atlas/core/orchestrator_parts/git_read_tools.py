"""Tools de lectura git + listing de workspace.

Extraído de ``Orchestrator`` (refactor god-object slice 2, 2026-05-30).
Sin cambios de comportamiento; las firmas que ven los callers (loop agéntico
y CLI) se preservan vía thin delegates en ``Orchestrator``.

Las tres tools git (``status``/``log``/``diff``) corren contra el repo de
código (`ATLAS_REPO_ROOT` o derivado) — no contra el workspace de runtime —
para que el modelo aterrice respuestas sobre commits reales y no confabule.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from atlas.core.contracts import Task
from atlas.logging.merkle_logger import MerkleLogger


class GitReadTools:
    """`git status/log/diff` + listing del workspace, auditados en Merkle."""

    def __init__(
        self,
        workspace: Path,
        merkle: MerkleLogger,
        repo_root: Callable[[], Path | None],
        run_via_executor: Callable[..., dict[str, Any]],
    ) -> None:
        self._workspace = workspace
        self._merkle = merkle
        self._repo_root = repo_root
        self._run_via_executor = run_via_executor

    def _git_args(self, sub: str, *extra: str) -> tuple[str, ...]:
        """Prefija ``-C <repo_root>`` cuando hay repo de código (grounding real).

        Sin repo (None) cae al comportamiento previo: git corre en el cwd del
        sandbox (workspace/tmp).
        """
        root = self._repo_root()
        if root is not None:
            return ("-C", str(root), sub, *extra)
        return (sub, *extra)

    def _with_repo_root(self, result: dict[str, Any]) -> dict[str, Any]:
        """Inyecta el repo_root real en el resultado git.

        Grounding de procedencia: el modelo gemelo (Hermes) NO debe inventar la
        ruta del repo. Sin este campo, al pedir "dónde está el repo" confabula
        un path inexistente. Con él, tiene la verdad en el output de la tool.
        """
        root = self._repo_root()
        if root is not None and "error" not in result:
            result["repo_root"] = str(root)
        return result

    def status(self, task: Task | None = None) -> dict[str, Any]:
        return self._with_repo_root(
            self._run_via_executor("git", self._git_args("status", "--short"), task=task)
        )

    def log(self, task: Task | None = None) -> dict[str, Any]:
        return self._with_repo_root(
            self._run_via_executor("git", self._git_args("log", "--oneline", "-10"), task=task)
        )

    def diff(self, task: Task | None = None) -> dict[str, Any]:
        return self._with_repo_root(
            self._run_via_executor("git", self._git_args("diff", "--stat"), task=task)
        )

    def list_workspace(self) -> dict[str, Any]:
        """Lista el workspace via ``iterdir()`` + log explícito en Merkle.

        No usa sandbox porque ``iterdir()`` es Python puro (no IO de proceso).
        Mantiene el contrato de auditoría registrando la operación como la
        registraría ``AtlasExecutor``.
        """
        try:
            entries = [p.name for p in self._workspace.iterdir()]
            self._merkle.log(
                action="fs.list_dir",
                agent="atlas.executor",
                result="ok",
                risk_level="safe",
                payload={"path": str(self._workspace), "entries": len(entries)},
            )
            return {"entries": sorted(entries), "path": str(self._workspace)}
        except Exception as e:  # noqa: BLE001
            self._merkle.log(
                action="fs.list_dir",
                agent="atlas.executor",
                result="failed",
                risk_level="safe",
                payload={"path": str(self._workspace), "error": str(e)},
            )
            return {"error": str(e)}
