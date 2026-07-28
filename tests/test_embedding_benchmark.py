"""Deterministic coverage for the pure embedding compatibility evaluator."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

from atlas.memory.embedding_benchmark import (
    BenchmarkCandidate,
    BenchmarkCase,
    BenchmarkInputError,
    EmbeddingVectorError,
    evaluate_cases,
    load_cases,
)
from atlas.memory.embeddings import FastEmbedEmbedder


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "fastembed_compatibility_cases.json"
)
RUNNER_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "benchmark_fastembed_compatibility.py"
)
_HAS_FASTEMBED = importlib.util.find_spec("fastembed") is not None


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "benchmark_fastembed_compatibility_under_test", RUNNER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _output_status(capsys: pytest.CaptureFixture[str]) -> str:
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    return str(json.loads(lines[0])["status"])


class StaticEmbedder:
    """In-process vectors for evaluator tests; it has no model or network side effects."""

    identity = "static:v1"
    fingerprint = "static:fingerprint"

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    @property
    def dim(self) -> int:
        return len(next(iter(self._vectors.values())))

    def embed(self, text: str) -> list[float]:
        return self._vectors[text]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]

    @classmethod
    def with_query(cls, query: list[float]) -> "StaticEmbedder":
        return cls(
            {
                "consulta": query,
                "relevante": [0.9, 0.1],
                "ruido": [0.0, 1.0],
            }
        )

    @classmethod
    def with_candidate(cls, candidate: list[float]) -> "StaticEmbedder":
        return cls(
            {
                "consulta": [1.0, 0.0],
                "relevante": candidate,
                "ruido": [0.0, 1.0],
            }
        )


def valid_case() -> BenchmarkCase:
    return BenchmarkCase(
        id="semantic-rank",
        query="consulta",
        candidates=(
            BenchmarkCandidate("relevant", "relevante"),
            BenchmarkCandidate("noise", "ruido"),
        ),
        relevant_ids=frozenset({"relevant"}),
        top_k=1,
    )


def test_evaluate_cases_ranks_the_relevant_candidate_and_binds_identity() -> None:
    """Changing ranking or copied embedder metadata must fail this contract."""
    embedder = StaticEmbedder(
        {
            "consulta": [1.0, 0.0],
            "relevante": [0.9, 0.1],
            "ruido": [0.0, 1.0],
        }
    )
    case = valid_case()

    report = evaluate_cases(embedder, (case,))

    assert report.passed is True
    assert report.identity == "static:v1"
    assert report.cases[0].relevant_rank == 1
    assert report.cases[0].rankings[0].candidate_id == "relevant"


def test_evaluate_cases_rejects_non_finite_or_dimension_mismatched_vectors() -> None:
    """Removing vector validation or using zip truncation must fail this test."""
    case = valid_case()

    with pytest.raises(EmbeddingVectorError, match="finite"):
        evaluate_cases(StaticEmbedder.with_query([float("nan"), 0.0]), (case,))

    with pytest.raises(EmbeddingVectorError, match="dimension"):
        evaluate_cases(StaticEmbedder.with_candidate([1.0, 0.0, 0.0]), (case,))


def test_evaluate_cases_breaks_score_ties_by_candidate_id_and_reports_margin() -> None:
    """Changing the deterministic tie rule or margin calculation must fail."""
    case = BenchmarkCase(
        id="tie-break",
        query="consulta",
        candidates=(
            BenchmarkCandidate("b", "empate-b"),
            BenchmarkCandidate("a", "empate-a"),
        ),
        relevant_ids=frozenset({"a"}),
        top_k=1,
    )
    embedder = StaticEmbedder(
        {
            "consulta": [1.0, 0.0],
            "empate-a": [1.0, 0.0],
            "empate-b": [1.0, 0.0],
        }
    )

    result = evaluate_cases(embedder, (case,)).cases[0]

    assert [ranked.candidate_id for ranked in result.rankings] == ["a", "b"]
    assert result.margin == 0.0


def test_load_cases_rejects_invalid_top_k(tmp_path: Path) -> None:
    """Accepting a non-positive top-k threshold would make a case meaningless."""
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "bad",
                    "query": "q",
                    "candidates": [
                        {"id": "a", "text": "a"},
                        {"id": "b", "text": "b"},
                    ],
                    "relevant_ids": ["a"],
                    "top_k": 0,
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(BenchmarkInputError, match="top_k"):
        load_cases(path)


def test_load_cases_reports_invalid_top_k_before_candidate_cardinality(
    tmp_path: Path,
) -> None:
    """The threshold error remains actionable even when the case has other defects."""
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "bad",
                    "query": "q",
                    "candidates": [{"id": "a", "text": "a"}],
                    "relevant_ids": ["a"],
                    "top_k": 0,
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(BenchmarkInputError, match="top_k"):
        load_cases(path)


def test_load_cases_reports_unknown_relevant_before_candidate_cardinality(
    tmp_path: Path,
) -> None:
    """Unknown relevance is actionable even if the case also lacks a distractor."""
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "bad",
                    "query": "q",
                    "candidates": [{"id": "a", "text": "a"}],
                    "relevant_ids": ["missing"],
                    "top_k": 1,
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(BenchmarkInputError, match="relevant"):
        load_cases(path)


def test_load_cases_rejects_fewer_than_two_candidates(tmp_path: Path) -> None:
    """A single candidate cannot measure semantic ranking compatibility."""
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "bad",
                    "query": "q",
                    "candidates": [{"id": "a", "text": "a"}],
                    "relevant_ids": ["a"],
                    "top_k": 1,
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(BenchmarkInputError, match="candidates"):
        load_cases(path)


def test_load_cases_rejects_unknown_relevant_id(tmp_path: Path) -> None:
    """Accepting a relevant id absent from candidates would invalidate ranking."""
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "bad",
                    "query": "q",
                    "candidates": [
                        {"id": "a", "text": "a"},
                        {"id": "b", "text": "b"},
                    ],
                    "relevant_ids": ["missing"],
                    "top_k": 1,
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(BenchmarkInputError, match="relevant"):
        load_cases(path)


def test_versioned_fixture_has_three_valid_spanish_cases() -> None:
    """Removing the measured corpus or weakening its ranking cases must fail."""
    cases = load_cases(FIXTURE_PATH)

    assert len(cases) >= 3
    assert all(
        case.top_k == 1
        and len(case.candidates) >= 2
        and len(case.relevant_ids) == 1
        for case in cases
    )


def test_runner_forces_offline_before_constructing_fastembed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Constructing FastEmbed before offline mode could trigger a model download."""
    runner = _load_runner()
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    observed: dict[str, str | None] = {}

    class OfflineProbe:
        def __init__(self) -> None:
            observed["offline"] = os.environ.get("HF_HUB_OFFLINE")

    class FakeReport:
        passed = True

        def as_dict(self) -> dict[str, object]:
            return {"passed": True}

    monkeypatch.setattr(runner, "FastEmbedEmbedder", OfflineProbe)
    monkeypatch.setattr(runner, "evaluate_cases", lambda _embedder, _cases: FakeReport())

    assert runner.main([]) == 0
    assert observed["offline"] == "1"


def test_runner_classifies_missing_optional_extra(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An absent optional package must remain distinguishable from a bad model cache."""
    runner = _load_runner()

    class MissingFastEmbed:
        def __init__(self) -> None:
            raise RuntimeError("fastembed no instalado")

    monkeypatch.setattr(runner, "FastEmbedEmbedder", MissingFastEmbed)

    assert runner.main([]) == 2
    assert _output_status(capsys) == "OPTIONAL_DEPENDENCY_MISSING"


def test_runner_classifies_unavailable_model_artifact(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A local artifact failure must not be mislabeled as a missing dependency."""
    runner = _load_runner()

    class MissingArtifact:
        def __init__(self) -> None:
            raise RuntimeError("modelo FastEmbed no disponible en la caché local")

    monkeypatch.setattr(runner, "FastEmbedEmbedder", MissingArtifact)

    assert runner.main([]) == 3
    assert _output_status(capsys) == "MODEL_ARTIFACT_UNAVAILABLE"


def test_runner_classifies_invalid_benchmark_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing or malformed corpus is configuration input, not a model failure."""
    runner = _load_runner()
    missing_cases = tmp_path / "missing-cases.json"

    assert runner.main(["--cases", str(missing_cases)]) == 4
    assert _output_status(capsys) == "INVALID_BENCHMARK_INPUT"


def test_runner_classifies_vector_measurement_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An invalid vector must become an explicit measured-run failure."""
    runner = _load_runner()

    def fail_vectors(_embedder: object, _cases: object) -> object:
        raise EmbeddingVectorError("vector dimension mismatch")

    monkeypatch.setattr(runner, "FastEmbedEmbedder", lambda: object())
    monkeypatch.setattr(runner, "evaluate_cases", fail_vectors)

    assert runner.main([]) == 1
    assert _output_status(capsys) == "MEASUREMENT_FAILED"


def test_runner_classifies_unexpected_measurement_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unexpected evaluator faults must still have one explicit failure result."""
    runner = _load_runner()

    def fail_measurement(_embedder: object, _cases: object) -> object:
        raise RuntimeError("fallo del evaluador")

    monkeypatch.setattr(runner, "FastEmbedEmbedder", lambda: object())
    monkeypatch.setattr(runner, "evaluate_cases", fail_measurement)

    assert runner.main([]) == 1
    assert _output_status(capsys) == "MEASUREMENT_FAILED"


def test_runner_returns_nonzero_when_measurement_misses_its_threshold(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A measured ranking miss must be visible to automation through exit status 5."""
    runner = _load_runner()

    class ThresholdMiss:
        passed = False

        def as_dict(self) -> dict[str, object]:
            return {"passed": False}

    monkeypatch.setattr(runner, "FastEmbedEmbedder", lambda: object())
    monkeypatch.setattr(runner, "evaluate_cases", lambda _embedder, _cases: ThresholdMiss())

    assert runner.main([]) == 5
    assert _output_status(capsys) == "COMPATIBILITY_THRESHOLD_NOT_MET"


@pytest.mark.skipif(
    not (_HAS_FASTEMBED and os.environ.get("ATLAS_RUN_FASTEMBED_COMPAT") == "1"),
    reason="requiere fastembed, artefacto local y opt-in explícito",
)
def test_cached_fastembed_satisfies_versioned_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The opt-in integration check detects a real local semantic compatibility loss."""
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")

    report = evaluate_cases(FastEmbedEmbedder(), load_cases(FIXTURE_PATH))

    assert report.passed is True
