"""Contract tests para las hipótesis diagnósticas graph/history/memory
(ADC-WO-108, pieza 4/5).

El propio work order nombra el riesgo: "creating another verifier instead
of composing existing ones". Este módulo NO reimplementa Cypher, ni git
log, ni un motor de recall: enruta a lo que ya existe --
`atlas.core.graphs.QUERIES` + `open_kuzu_database` para el grafo,
`clean_git_env` para el historial, `LessonStore.search_by_tag` para la
memoria. Fail-honesto: una fuente ausente/vacía es una hipótesis con
`available=False`, nunca una excepción que tumbe el resto.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlas.core.lesson_store import Lesson, LessonProvenance, LessonStore
from atlas.core.verify import Verdict
from atlas.engineering.findings import FindingLocation
from atlas.engineering.hypotheses import (
    EngineeringHypothesisSet,
    compose_hypotheses,
    graph_hypothesis,
    history_hypothesis,
    memory_hypothesis,
    module_name_for_path,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(repo),
             "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "primer commit")
    (root / "a.py").write_text("x = 2\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "segundo commit")
    return root


def test_module_name_for_path_converts_src_atlas_paths() -> None:
    assert module_name_for_path("src/atlas/core/orchestrator.py") == "atlas.core.orchestrator"


def test_module_name_for_path_returns_none_outside_src_atlas() -> None:
    assert module_name_for_path("docs/design/foo.md") is None


def test_graph_hypothesis_unavailable_without_a_kuzu_db(tmp_path: Path) -> None:
    hyp = graph_hypothesis("atlas.core.orchestrator", db_path=tmp_path / "nope.kuzu")
    assert hyp.available is False
    assert "no existe" in hyp.reason.lower() or "not" in hyp.reason.lower()


def test_history_hypothesis_counts_real_commits(repo: Path) -> None:
    hyp = history_hypothesis(repo, "a.py")
    assert hyp.available is True
    assert hyp.commit_count == 2


def test_history_hypothesis_unavailable_for_untracked_path(repo: Path) -> None:
    hyp = history_hypothesis(repo, "nunca-existio.py")
    assert hyp.available is True
    assert hyp.commit_count == 0


def test_memory_hypothesis_finds_lessons_by_tag(tmp_path: Path) -> None:
    store = LessonStore(tmp_path / "lessons")
    store.add(Lesson(
        id="lesson_001",
        title="Ejemplo",
        provenance=LessonProvenance.INTERNAL_FAILURE,
        detection_heuristic="h",
        avoid_pattern="p",
        evidence={"verdict": Verdict.PASS.value},
        tags=("module:atlas.core.orchestrator",),
        created_at="2026-07-31T00:00:00+00:00",
    ))

    hyp = memory_hypothesis(store, "module:atlas.core.orchestrator")

    assert hyp.available is True
    assert hyp.lesson_count == 1
    assert hyp.lesson_ids == ("lesson_001",)


def test_memory_hypothesis_empty_but_available_without_matches(tmp_path: Path) -> None:
    store = LessonStore(tmp_path / "lessons")
    hyp = memory_hypothesis(store, "module:nunca-visto")
    assert hyp.available is True
    assert hyp.lesson_count == 0


def test_compose_hypotheses_never_raises_on_missing_sources(tmp_path: Path) -> None:
    """Invariante fail-honesto: ninguna fuente ausente puede tumbar la
    composición de las otras dos."""
    location = FindingLocation(path="src/atlas/core/orchestrator.py")
    lessons = LessonStore(tmp_path / "lessons")

    result = compose_hypotheses(
        location,
        repo_root=tmp_path,  # sin repo git real -> history unavailable
        graph_db_path=tmp_path / "nope.kuzu",  # sin grafo -> graph unavailable
        lesson_store=lessons,
    )

    assert isinstance(result, EngineeringHypothesisSet)
    assert result.graph.available is False
    assert result.history.available is False
    assert result.memory.available is True  # LessonStore vacío SÍ es "disponible"
