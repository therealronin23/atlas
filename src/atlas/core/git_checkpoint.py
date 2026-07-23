"""
Atlas Core — Git Checkpoint Manager (absorbido de Cline, 2026-07-18).

Hueco real encontrado tras una comparación demasiado superficial en el
barrido de esta misma sesión: `TimeTravel`/`CheckpointStore` (ADR-021)
audita ESTADO DEL PIPELINE (etiquetas como "blocked_governance"), no
contenido de ficheros — no es lo mismo que "deshacer los cambios que hizo
el agente". Cline SÍ resuelve eso, con un mecanismo simple y real: cada
turno del agente se etiqueta con un commit o stash de git real, y restaurar
un checkpoint es `git reset --hard` + `git clean -fd` + aplicar ese ref
(absorbido fiel de `checkpoint-restore.ts`: mismos comandos, mismo orden).

Diferencia deliberada con Cline, más segura: Cline opera sobre el directorio
de trabajo REAL del usuario. Este módulo está pensado para operar SOLO
dentro de los git worktrees aislados que `ParallelCoder`/`ToolCoder` ya
crean por tarea (`git worktree add --detach`) — nunca en el repo principal.
El caller es responsable de pasar un `repo_path` que sea un worktree
efímero, no el checkout real; este módulo no lo fuerza estructuralmente
(no hay un ExternalFsBridge de rutas de worktree conocidas de antemano,
son directorios temporales dinámicos), pero SÍ rechaza explícitamente
operar sin que `repo_path` exista y sea un repo git real.

`restore()` es DESTRUCTIVO por diseño (como en Cline): borra todo lo no
checkpointeado. Se audita en Merkle con risk_level="critical".

2026-07-22 — wireado en el loop agéntico (`orchestrator.py` /
`orchestrator_parts/agentic_executor.py` + `gate_f_executor.py`): expuesto
como tool `git_checkpoint_restore`, clasificada `mutate` (ADR-032/033),
NUNCA auto-aprobada por la allowlist de ADR-033 pese a su riesgo `critical`
(exclusión explícita en `Orchestrator._is_agentic_auto_approved`, ver ADR).
El wiring agéntico añade la guarda estructural que este módulo, a propósito,
no fuerza por sí mismo (ver párrafo anterior): `is_ephemeral_worktree()` más
abajo, invocada por `GateFExecutor.run_git_checkpoint_restore` ANTES de
llamar a `restore()`, rechaza cualquier `repo_path` que no sea un worktree
efímero real (nunca el checkout git principal).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from atlas.logging.merkle_logger import MerkleLogger

CheckpointKind = Literal["commit", "stash"]


@dataclass(frozen=True)
class CheckpointEntry:
    ref: str
    run_count: int
    kind: CheckpointKind
    created_at: str


class GitCheckpointError(Exception):
    """El repo_path no es un repo git real, o el comando de git falló."""


def is_ephemeral_worktree(repo_path: Path) -> bool:
    """True si `repo_path` es un git worktree efímero (creado con
    `git worktree add`), nunca el checkout git principal.

    Invariante ESTRUCTURAL real, no una allowlist de rutas conocidas de
    antemano (los worktrees que crean `ParallelCoder`/`ToolCoder` son
    directorios temporales dinámicos, imposibles de enumerar de antemano):
    en un worktree, `.git` es un FICHERO de una línea
    (`gitdir: <repo>/.git/worktrees/<nombre>`); en el checkout principal,
    `.git` es un DIRECTORIO. Verificado en vivo con `git worktree add`
    real (no asumido de la documentación de git).

    Usado por el wiring agéntico de `restore()` (`GateFExecutor` en
    `orchestrator_parts/gate_f_executor.py`) para rechazar, ANTES de tocar
    el disco, cualquier intento de restaurar sobre el repo real."""
    return (repo_path / ".git").is_file()


class GitCheckpointManager:
    """Checkpoints reales por turno de agente, dentro de un worktree aislado.

    Uso esperado: llamar `checkpoint()` tras cada turno del agente en un
    worktree efímero; `restore()` solo si el operador pide deshacer turnos
    concretos ANTES de que `ParallelCoder`/`ToolCoder` sincronicen el
    resultado final al repo real (ver `_sync_sandbox_back` en tool_coder.py).
    """

    def __init__(self, merkle: MerkleLogger | None = None) -> None:
        self._merkle = merkle

    def _run_git(self, repo_path: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise GitCheckpointError(
                f"git {' '.join(args)} falló en {repo_path}: {result.stderr.strip()}"
            )
        return result.stdout.strip()

    def _verify_is_git_repo(self, repo_path: Path) -> None:
        if not repo_path.is_dir():
            raise GitCheckpointError(f"{repo_path} no existe")
        try:
            inside = self._run_git(repo_path, "rev-parse", "--is-inside-work-tree")
        except GitCheckpointError as exc:
            raise GitCheckpointError(f"{repo_path} no es un repo git: {exc}") from exc
        if inside != "true":
            raise GitCheckpointError(f"{repo_path} no es un repo git (rev-parse={inside!r})")

    def checkpoint(self, repo_path: Path, run_count: int) -> CheckpointEntry:
        """Captura el estado actual (tracked + untracked) como checkpoint.
        Usa stash por defecto (no ensucia el log de commits del worktree
        efímero) — fiel al mecanismo dual de Cline (kind='stash'). Si el
        working tree está limpio (nada que stashear — caso real encontrado
        al testear: primer checkpoint tras un `git init` recién hecho),
        cae a kind='commit' sobre el HEAD actual en vez de forzar un stash
        vacío (que git rechaza, "no local changes to save")."""
        self._verify_is_git_repo(repo_path)
        from datetime import datetime, timezone

        status = self._run_git(repo_path, "status", "--porcelain")
        if not status:
            ref = self._run_git(repo_path, "rev-parse", "HEAD")
            entry = CheckpointEntry(
                ref=ref, run_count=run_count, kind="commit",
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self._log("git_checkpoint.checkpoint", "ok", risk_level="safe",
                       payload={"repo_path": str(repo_path), "run_count": run_count,
                                "ref": ref, "kind": "commit", "clean_tree": True})
            return entry

        # --include-untracked: los ficheros NUEVOS del agente también entran
        # en el checkpoint, no solo los tracked modificados.
        self._run_git(repo_path, "stash", "push", "--include-untracked",
                       "-m", f"atlas-checkpoint-run-{run_count}")
        ref = self._run_git(repo_path, "rev-parse", "stash@{0}")
        # git stash push consume el working tree — lo restauramos de
        # inmediato (stash apply, no pop) para que el agente siga
        # trabajando sobre el mismo estado, con el checkpoint ya grabado.
        self._run_git(repo_path, "stash", "apply", "stash@{0}")
        entry = CheckpointEntry(
            ref=ref, run_count=run_count, kind="stash",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._log("git_checkpoint.checkpoint", "ok", risk_level="safe",
                   payload={"repo_path": str(repo_path), "run_count": run_count, "ref": ref})
        return entry

    def restore(self, repo_path: Path, checkpoint: CheckpointEntry) -> None:
        """DESTRUCTIVO — borra todo lo no checkpointeado en repo_path.
        Mismo orden de comandos que Cline (`applyCheckpointToWorktree`):
        verificar repo → verificar que el ref existe → reset --hard →
        clean -fd → aplicar el checkpoint (reset si es commit, stash apply
        si es stash)."""
        self._verify_is_git_repo(repo_path)
        try:
            self._run_git(repo_path, "cat-file", "-e", f"{checkpoint.ref}^{{commit}}")
        except GitCheckpointError as exc:
            self._log("git_checkpoint.restore", "failed", risk_level="critical",
                       payload={"repo_path": str(repo_path), "ref": checkpoint.ref, "error": str(exc)})
            raise

        self._run_git(repo_path, "reset", "--hard")
        self._run_git(repo_path, "clean", "-fd")
        if checkpoint.kind == "commit":
            self._run_git(repo_path, "reset", "--hard", checkpoint.ref)
        else:
            self._run_git(repo_path, "stash", "apply", checkpoint.ref)

        self._log(
            "git_checkpoint.restore", "ok", risk_level="critical",
            payload={"repo_path": str(repo_path), "ref": checkpoint.ref,
                     "run_count": checkpoint.run_count, "kind": checkpoint.kind},
        )

    def _log(
        self, action: str, result: str, *,
        risk_level: str = "safe", payload: dict[str, object] | None = None,
    ) -> None:
        if self._merkle is None:
            return
        self._merkle.log(
            action=action, agent="git_checkpoint.manager", result=result,
            risk_level=risk_level, payload=payload or {},
        )
