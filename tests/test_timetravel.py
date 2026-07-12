"""
Tests de Checkpoint + TimeTravel (ADR-021, Gate D/D5).
Verifica encadenado hash, persistencia, fork, verify_chain y
registro en MerkleLogger.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.checkpoint import (
    GENESIS_HASH,
    Checkpoint,
    CheckpointError,
    CheckpointStore,
)
from atlas.core.timetravel import HistoryEntry, TimeTravel
from atlas.logging.merkle_logger import MerkleLogger


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def store(tmp_path: Path) -> CheckpointStore:
    return CheckpointStore(tmp_path / "checkpoints")


@pytest.fixture
def merkle(tmp_path: Path) -> MerkleLogger:
    log_dir = tmp_path / "audit"
    log_dir.mkdir()
    return MerkleLogger(log_dir)


@pytest.fixture
def tt(tmp_path: Path, merkle: MerkleLogger) -> TimeTravel:
    return TimeTravel(store_path=tmp_path / "tt-store", merkle=merkle)


# ===========================================================================
# CheckpointStore — encadenado hash
# ===========================================================================


class TestCheckpointStore:

    def test_save_returns_checkpoint(self, store: CheckpointStore) -> None:
        cp = store.save("t1", "first step", {"x": 1})
        assert isinstance(cp, Checkpoint)
        assert cp.task_id == "t1"
        assert cp.hash_self != ""
        assert cp.hash_prev == GENESIS_HASH

    def test_save_rejects_empty_task_id(self, store: CheckpointStore) -> None:
        with pytest.raises(CheckpointError):
            store.save("", "x", {})

    def test_chain_links_consecutive(self, store: CheckpointStore) -> None:
        a = store.save("t1", "a", {"i": 0})
        b = store.save("t1", "b", {"i": 1})
        assert b.hash_prev == a.hash_self

    def test_load_recovers_state(self, store: CheckpointStore) -> None:
        saved = store.save("t1", "x", {"k": "v"})
        loaded = store.load("t1", saved.step_id)
        assert loaded.state == {"k": "v"}
        assert loaded.hash_self == saved.hash_self

    def test_load_missing_raises(self, store: CheckpointStore) -> None:
        with pytest.raises(CheckpointError):
            store.load("t1", "ghost")

    def test_list_steps_ordered_by_timestamp(self, store: CheckpointStore) -> None:
        store.save("t1", "a", {})
        store.save("t1", "b", {})
        store.save("t1", "c", {})
        steps = store.list_steps("t1")
        labels = [s.label for s in steps]
        assert labels == ["a", "b", "c"]

    def test_latest_returns_last(self, store: CheckpointStore) -> None:
        store.save("t1", "a", {})
        latest = store.save("t1", "b", {})
        assert store.latest("t1") is not None
        result = store.latest("t1")
        assert result is not None
        assert result.step_id == latest.step_id

    def test_tasks_lists_unique(self, store: CheckpointStore) -> None:
        store.save("t1", "x", {})
        store.save("t2", "y", {})
        store.save("t1", "z", {})
        assert sorted(store.tasks()) == ["t1", "t2"]

    def test_duplicate_step_id_rejected(self, store: CheckpointStore) -> None:
        store.save("t1", "a", {}, step_id="s-1")
        with pytest.raises(CheckpointError):
            store.save("t1", "b", {}, step_id="s-1")


class TestVerifyChain:

    def test_empty_task_ok(self, store: CheckpointStore) -> None:
        ok, msg = store.verify_chain("nope")
        assert ok

    def test_linear_chain_ok(self, store: CheckpointStore) -> None:
        store.save("t1", "a", {})
        store.save("t1", "b", {})
        store.save("t1", "c", {})
        ok, msg = store.verify_chain("t1")
        assert ok, msg

    def test_tampered_hash_detected(
        self, store: CheckpointStore, tmp_path: Path
    ) -> None:
        store.save("t1", "a", {})
        cp = store.save("t1", "b", {})
        # Modificar el JSON del segundo step en disco
        path = tmp_path / "checkpoints" / "t1" / f"{cp.step_id}.json"
        import json
        data = json.loads(path.read_text())
        data["state"]["tampered"] = True   # ahora hash_self ya no coincide
        path.write_text(json.dumps(data))
        ok, msg = store.verify_chain("t1")
        assert not ok
        assert "hash_self" in msg


class TestLoadRejectsCorruption:
    """tech-8-snapshot-integrity: load() debe rechazar un snapshot corrupto
    con error explícito, no solo verify_chain() (que es opt-in y de cadena
    completa) — un caller que solo hace store.load(task_id, step_id) no
    debe poder restaurar estado manipulado en silencio."""

    def test_load_raises_on_tampered_state(
        self, store: CheckpointStore, tmp_path: Path
    ) -> None:
        cp = store.save("t1", "a", {"balance": 100})
        path = tmp_path / "checkpoints" / "t1" / f"{cp.step_id}.json"
        import json
        data = json.loads(path.read_text())
        data["state"]["balance"] = 999999  # manipulación silenciosa
        path.write_text(json.dumps(data))

        with pytest.raises(CheckpointError, match="corrupto"):
            store.load("t1", cp.step_id)

    def test_load_raises_on_tampered_hash_field_directly(
        self, store: CheckpointStore, tmp_path: Path
    ) -> None:
        cp = store.save("t1", "a", {})
        path = tmp_path / "checkpoints" / "t1" / f"{cp.step_id}.json"
        import json
        data = json.loads(path.read_text())
        data["hash_self"] = "0" * 64  # hash falsificado directamente
        path.write_text(json.dumps(data))

        with pytest.raises(CheckpointError, match="hash_self invalido"):
            store.load("t1", cp.step_id)

    def test_load_succeeds_for_untampered_checkpoint(
        self, store: CheckpointStore
    ) -> None:
        cp = store.save("t1", "a", {"x": 1})
        loaded = store.load("t1", cp.step_id)
        assert loaded.state == {"x": 1}
        assert loaded.hash_self == cp.hash_self


class TestFork:

    def test_fork_creates_new_task(self, store: CheckpointStore) -> None:
        store.save("t1", "a", {"v": 1})
        b = store.save("t1", "b", {"v": 2})
        forked = store.fork("t1", b.step_id)
        assert forked.task_id != "t1"
        assert forked.state == {"v": 2}
        # El nuevo task aparece en tasks()
        assert forked.task_id in store.tasks()

    def test_fork_explicit_task_id(self, store: CheckpointStore) -> None:
        a = store.save("t1", "a", {"k": "v"})
        forked = store.fork("t1", a.step_id, new_task_id="branch-X", new_label="alt")
        assert forked.task_id == "branch-X"
        assert "alt" in forked.label


# ===========================================================================
# TimeTravel API
# ===========================================================================


class TestTimeTravelAPI:

    def test_new_task_creates_initial_step(self, tt: TimeTravel) -> None:
        tid = tt.new_task("debug timeout")
        history = tt.list_history(tid)
        assert len(history) == 1
        assert isinstance(history[0], HistoryEntry)
        assert "start" in history[0].label

    def test_record_step(self, tt: TimeTravel) -> None:
        tid = tt.new_task("flow")
        cp = tt.record_step(tid, "step-1", {"phase": "load"})
        assert cp.label == "step-1"
        assert cp.state == {"phase": "load"}
        history = tt.list_history(tid)
        assert len(history) == 2  # start + step-1

    def test_resume_from(self, tt: TimeTravel) -> None:
        tid = tt.new_task("resume-test")
        cp = tt.record_step(tid, "midpoint", {"counter": 42})
        state = tt.resume_from(tid, cp.step_id)
        assert state["counter"] == 42

    def test_fork_creates_branch(self, tt: TimeTravel) -> None:
        tid = tt.new_task("original")
        a = tt.record_step(tid, "a", {"x": 1})
        tt.record_step(tid, "b", {"x": 2})
        branch = tt.fork(tid, a.step_id, label="what if")
        assert branch != tid
        branch_history = tt.list_history(branch)
        assert len(branch_history) == 1
        assert "what if" in branch_history[0].label

    def test_verify_chain_via_api(self, tt: TimeTravel) -> None:
        tid = tt.new_task("verify-test")
        tt.record_step(tid, "a", {})
        tt.record_step(tid, "b", {})
        ok, _ = tt.verify_chain(tid)
        assert ok

    def test_list_tasks(self, tt: TimeTravel) -> None:
        t1 = tt.new_task("alpha")
        t2 = tt.new_task("beta")
        tasks = tt.list_tasks()
        assert t1 in tasks
        assert t2 in tasks


class TestMerkleIntegration:

    def test_record_step_logged_to_merkle(
        self, tt: TimeTravel, merkle: MerkleLogger
    ) -> None:
        tid = tt.new_task("audit")
        tt.record_step(tid, "step-X", {"foo": "bar"})

        ok, _ = merkle.verify_chain()
        assert ok

        recent = merkle.tail(10)
        actions = [r.action for r in recent]
        assert "timetravel.task_started" in actions
        assert "timetravel.checkpoint" in actions

    def test_fork_logged_to_merkle(
        self, tt: TimeTravel, merkle: MerkleLogger
    ) -> None:
        tid = tt.new_task("base")
        a = tt.record_step(tid, "a", {})
        tt.fork(tid, a.step_id, label="alt")
        recent = merkle.tail(10)
        actions = [r.action for r in recent]
        assert "timetravel.fork" in actions
