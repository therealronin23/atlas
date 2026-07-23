"""
t1-git-checkpoint-agentic-wiring — restore() expuesto en el loop agéntico.

git_checkpoint.py (absorción de Cline, 2026-07-18) está probado en aislado
(tests/test_git_checkpoint.py) pero su método DESTRUCTIVO `restore()` nunca
tuvo caller dentro del loop agéntico (ADR-031). Este archivo prueba el
wiring completo, con un git worktree REAL (no mocks): igual que
test_orchestrator_mutating_loop.py para editor_write, pero con las dos
garantías extra que pide este ticket:

  1. `git_checkpoint_restore` SIEMPRE suspende (ADR-032) y SIEMPRE exige
     HITL — nunca se auto-aprueba, ni siquiera si el operador la mete en la
     allowlist de ADR-033 (a diferencia de cualquier otro mutante).
  2. La ejecución real solo ocurre dentro de un worktree efímero (`git
     worktree add`); sobre el checkout git principal, la tool se rechaza
     estructuralmente y no toca el disco.
  3. Denegar deja el worktree intacto; aprobar ejecuta restore() real y
     queda auditado en Merkle con risk_level="critical".
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from atlas.core.contracts import RoutingLevel, TaskStatus
from atlas.core.git_checkpoint import GitCheckpointManager
from atlas.core.orchestrator import Orchestrator


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


class _ScriptedHub:
    """Idéntico al de test_orchestrator_mutating_loop.py — hub de inferencia
    falso con un guion de respuestas fijas."""

    def __init__(self, script: list) -> None:  # noqa: ANN001
        self._script = list(script)
        self.calls: list = []

    def infer(self, request):  # noqa: ANN001, ANN201
        self.calls.append(request)
        if len(self._script) > 1:
            return self._script.pop(0)
        return self._script[0]


def _resp(text: str = "", tool_calls: list | None = None):  # noqa: ANN001, ANN201
    from atlas.core.inference_hub import InferenceLevel, InferenceResponse

    return InferenceResponse(
        text=text, provider="mock", model="m", level=InferenceLevel.L1,
        latency_ms=1, success=True, tokens_used=1, mode="live",
        tool_calls=tool_calls or [],
    )


def _restore_call(repo_path: Path, ref: str, run_count: int, kind: str) -> dict:
    return {
        "id": "m1",
        "name": "git_checkpoint_restore",
        "arguments": json.dumps({
            "repo_path": str(repo_path), "ref": ref,
            "run_count": run_count, "kind": kind,
        }),
    }


@pytest.fixture
def main_repo(tmp_path: Path) -> Path:
    """El checkout git 'real' — NUNCA debe aceptar restore() vía el loop."""
    repo = tmp_path / "main_repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@atlas.local")
    _git(repo, "config", "user.name", "atlas-test")
    (repo / "file.txt").write_text("v1\n")
    _git(repo, "add", "file.txt")
    _git(repo, "commit", "-q", "-m", "initial")
    return repo


@pytest.fixture
def worktree(main_repo: Path, tmp_path: Path) -> Path:
    """Worktree efímero real (`git worktree add --detach`) — el ÚNICO lugar
    donde restore() debe poder operar, igual que ParallelCoder/ToolCoder."""
    wt = tmp_path / "wt-ephemeral"
    _git(main_repo, "worktree", "add", "-q", "--detach", str(wt), "HEAD")
    return wt


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_MEMORY_VECTOR", "0")
    monkeypatch.delenv("ATLAS_PIPELINE_GATE_D", raising=False)
    return Orchestrator(workspace=tmp_path / "atlas")


# ===========================================================================
# Suspensión → aprobación → restore ejecutado → auditado en Merkle (critical)
# ===========================================================================


def test_restore_suspends_then_approval_executes_and_audits_critical(
    orch: Orchestrator, worktree: Path,
) -> None:
    # Checkpoint real de referencia, tomado ANTES del turno "destructivo" del
    # agente (mismo GitCheckpointManager que usaría ToolCoder/ParallelCoder).
    manager = GitCheckpointManager()
    cp = manager.checkpoint(worktree, run_count=1)

    (worktree / "file.txt").write_text("v2 -- turno del agente a deshacer\n")
    (worktree / "nuevo_del_agente.py").write_text("archivo nuevo del turno\n")

    hub = _ScriptedHub([
        _resp(tool_calls=[_restore_call(worktree, cp.ref, cp.run_count, cp.kind)]),
        _resp(text="Restaurado al checkpoint anterior."),
    ])
    orch.enable_gate_d_pipeline(inference_hub=hub)
    task = orch.handle_intent("deshaz el ultimo turno del agente")

    # 1. Suspensión: la mutación NUNCA se auto-aprueba, ni corre sin HITL.
    assert task.status == TaskStatus.AWAITING_APPROVAL
    assert task.route == RoutingLevel.REQUIRES_APPROVAL
    assert task.metadata["agentic_state"]["pending_mutations"][0]["name"] == (
        "git_checkpoint_restore"
    )
    # El disco no se tocó todavía.
    assert (worktree / "file.txt").read_text() == "v2 -- turno del agente a deshacer\n"
    assert (worktree / "nuevo_del_agente.py").exists()

    # 2. Aprobación humana → reanuda y ejecuta restore() real.
    res = orch.approve_pending(task.id, True)
    assert res["status"] == "done"
    assert task.status == TaskStatus.DONE

    # 3. restore() real corrió: reset --hard + clean -fd sobre el worktree.
    assert (worktree / "file.txt").read_text() == "v1\n"
    assert not (worktree / "nuevo_del_agente.py").exists()

    # 4. Auditado en Merkle con risk_level="critical" (del propio
    # GitCheckpointManager, no solo el genérico tool.invoked del loop).
    recent = orch._merkle.tail(60)
    restore_entries = [
        r for r in recent
        if r.action == "git_checkpoint.restore" and r.result == "ok"
    ]
    assert restore_entries, "no se encontró git_checkpoint.restore en Merkle"
    assert restore_entries[0].risk_level == "critical"

    ok, msg = orch._merkle.verify_chain()
    assert ok, msg


# ===========================================================================
# Denegar deja el worktree intacto
# ===========================================================================


def test_deny_leaves_worktree_intact(orch: Orchestrator, worktree: Path) -> None:
    manager = GitCheckpointManager()
    cp = manager.checkpoint(worktree, run_count=1)

    (worktree / "file.txt").write_text("v2 -- no se debe perder\n")
    (worktree / "nuevo_del_agente.py").write_text("no se debe borrar\n")

    hub = _ScriptedHub([
        _resp(tool_calls=[_restore_call(worktree, cp.ref, cp.run_count, cp.kind)]),
        _resp(text="Entendido, no revierto nada."),
    ])
    orch.enable_gate_d_pipeline(inference_hub=hub)
    task = orch.handle_intent("deshaz el ultimo turno del agente")
    assert task.status == TaskStatus.AWAITING_APPROVAL

    res = orch.approve_pending(task.id, False)  # deny, sin abort

    assert res.get("denied_and_resumed") is True
    assert task.status == TaskStatus.DONE
    # El worktree quedó EXACTAMENTE como estaba: restore() nunca corrió.
    assert (worktree / "file.txt").read_text() == "v2 -- no se debe perder\n"
    assert (worktree / "nuevo_del_agente.py").exists()

    recent = orch._merkle.tail(60)
    assert not any(r.action == "git_checkpoint.restore" for r in recent)


# ===========================================================================
# Nunca auto-aprobada, ni siquiera si el operador la mete en la allowlist
# ===========================================================================


def test_never_auto_approved_even_if_added_to_allowlist(
    orch: Orchestrator, worktree: Path,
) -> None:
    manager = GitCheckpointManager()
    cp = manager.checkpoint(worktree, run_count=1)

    # El operador comete el error de meterla en la allowlist de ADR-033.
    orch.set_agentic_auto_approve({"git_checkpoint_restore"})

    hub = _ScriptedHub([
        _resp(tool_calls=[_restore_call(worktree, cp.ref, cp.run_count, cp.kind)]),
    ])
    orch.enable_gate_d_pipeline(inference_hub=hub)
    task = orch.handle_intent("deshaz el ultimo turno")

    # Sigue exigiendo HITL: la exclusión de git_checkpoint_restore es
    # incondicional (_is_agentic_auto_approved), no depende de la allowlist.
    assert task.status == TaskStatus.AWAITING_APPROVAL
    assert not any(
        r.action == "task.auto_approved" for r in orch._merkle.tail(60)
    )


# ===========================================================================
# Guarda estructural: nunca sobre el checkout git real (no worktree)
# ===========================================================================


def test_restore_rejected_on_main_checkout_not_a_worktree(
    orch: Orchestrator, main_repo: Path,
) -> None:
    manager = GitCheckpointManager()
    cp = manager.checkpoint(main_repo, run_count=1)
    (main_repo / "file.txt").write_text("v2 en el repo real\n")

    hub = _ScriptedHub([
        _resp(tool_calls=[_restore_call(main_repo, cp.ref, cp.run_count, cp.kind)]),
        _resp(text="No se pudo restaurar: no es un worktree efimero."),
    ])
    orch.enable_gate_d_pipeline(inference_hub=hub)
    task = orch.handle_intent("deshaz el ultimo turno")
    assert task.status == TaskStatus.AWAITING_APPROVAL

    orch.approve_pending(task.id, True)  # humano aprueba... pero la guarda estructural manda

    # El repo 'real' no se tocó: la tool rechazó la ejecución antes de llamar
    # a restore() porque main_repo no es un worktree (.git es directorio).
    assert (main_repo / "file.txt").read_text() == "v2 en el repo real\n"
    recent = orch._merkle.tail(60)
    assert not any(r.action == "git_checkpoint.restore" for r in recent)
    # El modelo recibió el error explícito, no una excepción silenciosa.
    tool_msgs = [m for m in hub.calls[1].messages if m["role"] == "tool"]
    assert any("no es un worktree efimero" in m["content"] for m in tool_msgs)
