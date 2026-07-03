"""
TDD — CodeCycle: fix del bug synthesis_recorder (Cónclave v2 slice).

Bug real confirmado: `_council_review` llamaba a `convene_for_decision` sin
`synthesis_recorder`, así que los veredictos del Cónclave nunca se destilaban
en LessonStore. Estos tests confirman el fix: si CodeCycle recibe un
`lesson_store`, construye un `LessonSynthesisRecorder` y lo pasa.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from atlas.core.code_cycle import CodeCycle
from atlas.core.parallel_coder import ParallelCoderResult


class _FakeHub:
    def infer(self, request):  # noqa: ANN001
        raise AssertionError("no debería llamarse en estos tests")


def _make_result(success: bool) -> ParallelCoderResult:
    return ParallelCoderResult(
        subtasks_total=1,
        subtasks_passed=1 if success else 0,
        subtasks_failed=0 if success else 1,
        results=[],
    )


def test_council_review_passes_synthesis_recorder_when_lesson_store_present(tmp_path: Path) -> None:
    from atlas.core.lesson_store import LessonStore

    store = LessonStore(tmp_path / "lessons")
    cycle = CodeCycle(_FakeHub(), repo_root=tmp_path, lesson_store=store)  # type: ignore[arg-type]

    captured = {}

    def _fake_convene(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        captured.update(kwargs)
        from atlas.core.verify import Evidence, Verdict
        return Evidence(verdict=Verdict.PASS)

    with patch("atlas.core.deliberation_council.convene_for_decision", _fake_convene):
        cycle._council_review("tarea", _make_result(True))

    assert "synthesis_recorder" in captured
    assert captured["synthesis_recorder"] is not None


def test_council_review_passes_none_recorder_without_lesson_store(tmp_path: Path) -> None:
    cycle = CodeCycle(_FakeHub(), repo_root=tmp_path)  # type: ignore[arg-type]  # sin lesson_store

    captured = {}

    def _fake_convene(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        captured.update(kwargs)
        from atlas.core.verify import Evidence, Verdict
        return Evidence(verdict=Verdict.PASS)

    with patch("atlas.core.deliberation_council.convene_for_decision", _fake_convene):
        cycle._council_review("tarea", _make_result(True))

    assert captured.get("synthesis_recorder") is None
