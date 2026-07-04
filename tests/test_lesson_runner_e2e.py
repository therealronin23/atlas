"""Integration tests for LessonRunner.run_and_promote() full cycle."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from atlas.core.lesson_runner import LessonRunner, promote_if_fixed
from atlas.core.lesson_store import LessonStore, ProveItResult

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_FAKE_TMPDIR = "/tmp/fake_lesson_e2e"
_TEST_PATH = "tests/test_mi_leccion.py"
_FIX_COMMIT = "deadbeef"


def _make_store(tmp_path):
    store_dir = tmp_path / "lesson_store"
    store_dir.mkdir(parents=True, exist_ok=True)
    return LessonStore(store_dir)


def _make_fake_run(before_rc: int, after_rc: int):
    """Return a side_effect callable that simulates git + pytest calls."""
    call_count: dict[str, int] = {"pytest": 0}

    def fake_run(cmd, **kw):
        if cmd[:3] == ["git", "worktree", "add"]:
            return MagicMock(returncode=0, stderr=b"")
        if cmd[:3] == ["git", "worktree", "remove"]:
            return MagicMock(returncode=0)
        if cmd[0] == "pytest":
            call_count["pytest"] += 1
            rc = before_rc if call_count["pytest"] == 1 else after_rc
            return MagicMock(returncode=rc)
        return MagicMock(returncode=0)

    return fake_run


def _run_and_promote(fake_run_side_effect, store: LessonStore, **kwargs):
    defaults = dict(
        failure_id="failure-001",
        title="mi lección",
        detection_heuristic="detect pattern",
        avoid_pattern="avoid pattern",
        tags=(),
    )
    defaults.update(kwargs)
    runner = LessonRunner(repo_root=None)
    with (
        patch("atlas.core.lesson_runner.tempfile.mkdtemp", return_value=_FAKE_TMPDIR),
        patch("atlas.core.lesson_runner.BwrapJail.is_available", return_value=False),
        patch("atlas.core.lesson_runner.subprocess.run", side_effect=fake_run_side_effect),
    ):
        return runner.run_and_promote(
            _TEST_PATH,
            _FIX_COMMIT,
            store=store,
            **defaults,
        )


# ---------------------------------------------------------------------------
# test 1 — red→green: lesson created with correct fields
# ---------------------------------------------------------------------------

def test_run_and_promote_red_green_creates_lesson(tmp_path):
    store = _make_store(tmp_path)
    prove_it, lesson = _run_and_promote(_make_fake_run(before_rc=1, after_rc=0), store)

    assert lesson is not None
    assert lesson.regression_test_path == _TEST_PATH
    assert lesson.title == "mi lección"
    assert prove_it.failed_before is True
    assert prove_it.passes_after is True


# ---------------------------------------------------------------------------
# test 2 — test passes before fix: not red → no lesson
# ---------------------------------------------------------------------------

def test_run_and_promote_not_red_returns_none(tmp_path):
    store = _make_store(tmp_path)
    prove_it, lesson = _run_and_promote(_make_fake_run(before_rc=0, after_rc=0), store)

    assert lesson is None
    assert prove_it.failed_before is False


# ---------------------------------------------------------------------------
# test 3 — test fails after fix: not green → no lesson
# ---------------------------------------------------------------------------

def test_run_and_promote_not_green_returns_none(tmp_path):
    store = _make_store(tmp_path)
    prove_it, lesson = _run_and_promote(_make_fake_run(before_rc=1, after_rc=1), store)

    assert lesson is None
    assert prove_it.passes_after is False


# ---------------------------------------------------------------------------
# test 4 — red→green: lesson is persisted in the real SQLite index
# ---------------------------------------------------------------------------

def test_run_and_promote_lesson_stored_in_index(tmp_path):
    store = _make_store(tmp_path)
    _, lesson = _run_and_promote(_make_fake_run(before_rc=1, after_rc=0), store)

    assert lesson is not None
    retrieved = store.get(lesson.id)
    assert retrieved is not None
    assert retrieved.id == lesson.id
    assert retrieved.title == lesson.title


# ---------------------------------------------------------------------------
# test 5 — promote_if_fixed: idempotente (no duplica lección con mismo failure_id)
# ---------------------------------------------------------------------------

def test_promote_if_fixed_idempotent(tmp_path, monkeypatch):
    """promote_if_fixed no duplica si ya existe lección con mismo failure_id."""
    store = _make_store(tmp_path)
    fake_result = ProveItResult(
        test_path="t",
        fix_commit="abc",
        failed_before=True,
        passes_after=True,
    )
    monkeypatch.setattr(LessonRunner, "run", lambda self, test_path, fix_commit: fake_result)

    # Primera llamada — debe crear la lección.
    lesson = promote_if_fixed(
        "fail-001",
        "abc",
        store,
        title="T",
        detection_heuristic="H",
        avoid_pattern="A",
        test_path="t",
    )
    assert lesson is not None

    # Segunda llamada — idempotente: devuelve None, no crea duplicado.
    result2 = promote_if_fixed(
        "fail-001",
        "abc",
        store,
        title="T",
        detection_heuristic="H",
        avoid_pattern="A",
        test_path="t",
    )
    assert result2 is None
    assert len(store.all()) == 1
