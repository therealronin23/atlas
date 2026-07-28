"""Deterministic coverage for the pure embedding compatibility evaluator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.memory.embedding_benchmark import (
    BenchmarkCandidate,
    BenchmarkCase,
    BenchmarkInputError,
    EmbeddingVectorError,
    evaluate_cases,
    load_cases,
)


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
