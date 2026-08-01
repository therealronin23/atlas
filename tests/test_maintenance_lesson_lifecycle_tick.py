"""Tests de `maintenance_lesson_lifecycle_tick` (2026-08-01).

`LessonStore.apply_lifecycle_transitions()` se portó de Hermes-Agent
(`curator.py`) el 2026-07-18, con 9 tests propios en verde — y CERO callers de
producción hasta hoy. Se dejó parado a propósito el mismo día que se destapó:
las 17 lecciones reales tenían `recall_count=0` porque el `LessonRecaller` del
daemon leía un almacén VACÍO (bug de rutas divergentes, arreglado el mismo día
con lectura dual curado+runtime). Con `recall_count` ya real, cablear el
envejecido por fin tiene sentido.

Mismo patrón que el resto de `maintenance_*_tick`: opt-in por env, guardia
anti-recursión, cadencia propia por fichero de estado, Merkle. NUNCA borra
ficheros — `archived` es sólo una etiqueta recuperable.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from atlas.core.lesson_store import Lesson, LessonProvenance, LessonStore
from atlas.core.orchestrator import Orchestrator


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "repo"))
    monkeypatch.setenv("ATLAS_REPO_ROOT", str(tmp_path / "repo"))
    monkeypatch.delenv("ATLAS_LESSON_LIFECYCLE", raising=False)
    monkeypatch.delenv("ATLAS_NESTED_TEST_RUN", raising=False)
    (tmp_path / "repo" / "workspace" / "lessons").mkdir(parents=True)
    return Orchestrator(workspace=tmp_path / "atlas")


def _old_lesson(root: Path, lid: str, *, days_old: int, recall_count: int = 0) -> None:
    store = LessonStore(root / "repo" / "workspace" / "lessons")
    created = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
    lesson = Lesson(
        id=lid, title="t", provenance=LessonProvenance.INTERNAL_FAILURE,
        detection_heuristic="h", avoid_pattern="p", evidence={"verdict": "pass"},
        created_at=created,
    )
    store.add(lesson)
    if recall_count:
        for _ in range(recall_count):
            store.record_recall(lid)


class TestDisabledAndGuard:
    def test_disabled_without_env_flag(self, orch: Orchestrator) -> None:
        assert orch.maintenance_lesson_lifecycle_tick() == {"status": "disabled"}

    def test_nested_run_guard_beats_enabled_env(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_LESSON_LIFECYCLE", "1")
        monkeypatch.setenv("ATLAS_NESTED_TEST_RUN", "1")
        assert orch.maintenance_lesson_lifecycle_tick() == {"status": "nested_run_guard"}


class TestAppliesTransitions:
    def test_an_old_never_recalled_lesson_goes_stale(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("ATLAS_LESSON_LIFECYCLE", "1")
        _old_lesson(tmp_path, "old-unused", days_old=35)

        result = orch.maintenance_lesson_lifecycle_tick()

        assert result["status"] == "ran"
        assert result["marked_stale"] == 1
        store = LessonStore(tmp_path / "repo" / "workspace" / "lessons")
        assert store.get("old-unused").state == "stale"

    def test_a_recently_recalled_lesson_stays_active(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("ATLAS_LESSON_LIFECYCLE", "1")
        _old_lesson(tmp_path, "used-recently", days_old=35, recall_count=1)

        result = orch.maintenance_lesson_lifecycle_tick()

        assert result["marked_stale"] == 0
        store = LessonStore(tmp_path / "repo" / "workspace" / "lessons")
        assert store.get("used-recently").state == "active"

    def test_a_young_never_recalled_lesson_is_not_judged_yet(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Grace floor: ausencia de evidencia no es evidencia de obsolescencia."""
        monkeypatch.setenv("ATLAS_LESSON_LIFECYCLE", "1")
        _old_lesson(tmp_path, "young", days_old=2)

        result = orch.maintenance_lesson_lifecycle_tick()

        assert result["marked_stale"] == 0
        store = LessonStore(tmp_path / "repo" / "workspace" / "lessons")
        assert store.get("young").state == "active"

    def test_never_deletes_or_moves_any_file(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("ATLAS_LESSON_LIFECYCLE", "1")
        _old_lesson(tmp_path, "old-unused", days_old=200)

        orch.maintenance_lesson_lifecycle_tick()

        assert (tmp_path / "repo" / "workspace" / "lessons" / "old-unused.json").is_file()


class TestWiredIntoTheRealScheduler:
    """Todo `maintenance_*_tick` anterior demostró que EXISTIR no basta: hace
    falta un caller de producción real. El caller real de estos ticks es
    `MaintenanceScheduler._extra_cycles`, corrido por su propio hilo daemon
    cada `poll_interval_seconds` (default 24h) dentro de `atlas serve` -- no
    `AtlasServiceRunner.tick()` (que sólo barre TTLs), como parecía a primera
    vista antes de trazar `service_runner.py:108 -> maintenance_scheduler()`.
    """

    def test_the_cycle_is_registered_in_the_scheduler(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_LESSON_LIFECYCLE", "1")
        scheduler = orch.maintenance_scheduler()

        assert len(scheduler._extra_cycles) >= 15

    def test_a_full_scheduler_tick_actually_ages_a_lesson(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """No basta con que el closure exista: un `scheduler.tick()` real
        debe recorrer `_extra_cycles` y llegar hasta el envejecido."""
        monkeypatch.setenv("ATLAS_LESSON_LIFECYCLE", "1")
        _old_lesson(tmp_path, "old-unused", days_old=35)
        scheduler = orch.maintenance_scheduler()
        # discover/analyze/notify del MCP scheduler no son el objeto de este
        # test: se aíslan para que tick() no intente red real.
        scheduler._discover = lambda: []

        scheduler.tick()

        store = LessonStore(tmp_path / "repo" / "workspace" / "lessons")
        assert store.get("old-unused").state == "stale"


class TestCadenceAndAudit:
    def test_running_twice_the_same_day_is_a_noop_the_second_time(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("ATLAS_LESSON_LIFECYCLE", "1")
        _old_lesson(tmp_path, "old-unused", days_old=35)

        first = orch.maintenance_lesson_lifecycle_tick()
        second = orch.maintenance_lesson_lifecycle_tick()

        assert first["status"] == "ran"
        assert second == {"status": "already_ran_today"}

    def test_it_logs_to_merkle(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("ATLAS_LESSON_LIFECYCLE", "1")
        _old_lesson(tmp_path, "old-unused", days_old=35)

        calls: list[dict] = []
        orch._merkle.log = lambda **kw: calls.append(kw)  # type: ignore[method-assign]

        orch.maintenance_lesson_lifecycle_tick()

        assert any("lesson_lifecycle" in str(c.get("action", "")) for c in calls)
