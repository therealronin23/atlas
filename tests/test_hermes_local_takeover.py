"""Hermes pausado → takeover local (ATLAS_HERMES_LOCAL=1).

Con el VPS dado de baja, una tarea clasificada ``DELEGATE_HERMES`` no debe
pudrirse en la ``OfflineQueue``: con el flag activo y el adapter en mock, la
delegación se convierte en ejecución local auditada.

Reglas que estos tests fijan:

- **Default intacto:** sin el flag, la conducta es la de siempre (DELEGATED +
  encolado en OfflineQueue).
- **Takeover solo con mock:** el flag NO secuestra un adapter Hermes real (kanban).
- **Auditoría:** el reruteo deja ``hermes.local_takeover`` en Merkle.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.contracts import Task, TaskSource, TaskStatus
from atlas.core.orchestrator import Orchestrator


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.delenv("ATLAS_PIPELINE_GATE_D", raising=False)
    monkeypatch.delenv("HERMES_BASE_URL", raising=False)
    monkeypatch.delenv("HERMES_KANBAN_TRANSPORT", raising=False)
    return Orchestrator(workspace=tmp_path / "atlas")


def _task(intent: str = "investiga a fondo el estado del arte") -> Task:
    # El pipeline real llega a la rama DELEGATE en estado ROUTING.
    task = Task(intent=intent, source=TaskSource.CLI)
    task.transition(TaskStatus.CLASSIFYING)
    task.transition(TaskStatus.ROUTING)
    return task


class TestDefaultUnchanged:
    def test_without_flag_delegates_to_queue(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ATLAS_HERMES_LOCAL", raising=False)
        task = _task()
        depth_before = orch._offline_queue.depth
        orch._delegate_to_hermes(task)
        assert task.status == TaskStatus.DELEGATED
        assert orch._offline_queue.depth == depth_before + 1


class TestTakeover:
    def test_flag_reroutes_to_local_execution(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_HERMES_LOCAL", "1")
        executed: list[str] = []
        monkeypatch.setattr(
            orch, "_execute_task", lambda t: executed.append(t.id)
        )
        task = _task()
        depth_before = orch._offline_queue.depth
        orch._delegate_to_hermes(task)
        # Ejecutó local, no encoló nada
        assert executed == [task.id]
        assert task.status == TaskStatus.EXECUTING
        assert orch._offline_queue.depth == depth_before

    def test_takeover_audited_in_merkle(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_HERMES_LOCAL", "1")
        monkeypatch.setattr(orch, "_execute_task", lambda t: None)
        task = _task()
        orch._delegate_to_hermes(task)
        actions = [r.to_dict()["action"] for r in orch._merkle.tail(10)]
        assert "hermes.local_takeover" in actions

    def test_flag_does_not_hijack_real_kanban_adapter(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_HERMES_LOCAL", "1")
        # Simular un adapter Hermes real (kanban, ADR-028): el takeover NO debe
        # aplicar. El canal REST legado que este caso cubria antes fue retirado
        # en ADR-070 — HermesKanbanAdapter es ahora el unico adapter real.
        from atlas.hermes.hermes import HermesKanbanAdapter

        orch._hermes = HermesKanbanAdapter.__new__(HermesKanbanAdapter)
        assert orch._hermes_local_takeover() is False
