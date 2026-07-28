"""Pure, read-only evaluation of an existing embedding space."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from atlas.memory.embeddings import Embedder


BENCHMARK_SCHEMA_VERSION = "1.0"


class BenchmarkInputError(ValueError):
    """Raised when a benchmark fixture cannot be parsed as a valid case set."""


class EmbeddingVectorError(ValueError):
    """Raised when an embedder returns vectors unsuitable for cosine scoring."""


@dataclass(frozen=True)
class BenchmarkCandidate:
    id: str
    text: str


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    query: str
    candidates: tuple[BenchmarkCandidate, ...]
    relevant_ids: frozenset[str]
    top_k: int


@dataclass(frozen=True)
class RankedCandidate:
    candidate_id: str
    score: float
    rank: int


@dataclass(frozen=True)
class BenchmarkCaseResult:
    case_id: str
    rankings: tuple[RankedCandidate, ...]
    relevant_rank: int | None
    margin: float | None
    passed: bool


@dataclass(frozen=True)
class EmbeddingBenchmarkReport:
    schema_version: str
    identity: str
    fingerprint: str
    dimension: int
    cases: tuple[BenchmarkCaseResult, ...]
    passed: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "identity": self.identity,
            "fingerprint": self.fingerprint,
            "dimension": self.dimension,
            "cases": [
                {
                    "case_id": case.case_id,
                    "rankings": [
                        {
                            "candidate_id": ranking.candidate_id,
                            "score": ranking.score,
                            "rank": ranking.rank,
                        }
                        for ranking in case.rankings
                    ],
                    "relevant_rank": case.relevant_rank,
                    "margin": case.margin,
                    "passed": case.passed,
                }
                for case in self.cases
            ],
            "passed": self.passed,
        }


def load_cases(path: Path) -> tuple[BenchmarkCase, ...]:
    """Load a strict JSON array of benchmark cases without invoking an embedder."""
    try:
        raw_cases = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BenchmarkInputError(f"invalid benchmark fixture: {exc}") from exc

    if not isinstance(raw_cases, list):
        raise BenchmarkInputError("benchmark fixture must be a JSON array")
    if not raw_cases:
        raise BenchmarkInputError("benchmark fixture must contain at least one case")

    cases = tuple(_parse_case(raw_case, index) for index, raw_case in enumerate(raw_cases))
    case_ids = [case.id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise BenchmarkInputError("benchmark case ids must be unique")
    return cases


def evaluate_cases(
    embedder: Embedder, cases: Sequence[BenchmarkCase]
) -> EmbeddingBenchmarkReport:
    """Rank each case using only the supplied embedder and in-memory values."""
    dimension = embedder.dim
    if type(dimension) is not int or dimension <= 0:
        raise EmbeddingVectorError("embedder dimension must be a positive integer")

    results = tuple(_evaluate_case(embedder, case, dimension) for case in cases)
    return EmbeddingBenchmarkReport(
        schema_version=BENCHMARK_SCHEMA_VERSION,
        identity=embedder.identity,
        fingerprint=embedder.fingerprint,
        dimension=dimension,
        cases=results,
        passed=all(result.passed for result in results),
    )


def _parse_case(raw_case: object, index: int) -> BenchmarkCase:
    location = f"case {index}"
    case = _object(raw_case, location)
    _require_exact_keys(case, {"id", "query", "candidates", "relevant_ids", "top_k"}, location)

    case_id = _non_empty_string(case["id"], f"{location}.id")
    query = _non_empty_string(case["query"], f"{location}.query")
    top_k = case["top_k"]
    if type(top_k) is not int or top_k < 1:
        raise BenchmarkInputError(f"{location}.top_k must be a positive integer")
    candidates = _parse_candidates(case["candidates"], location)
    relevant_ids = _parse_relevant_ids(case["relevant_ids"], candidates, location)
    if len(candidates) < 2:
        raise BenchmarkInputError(f"{location}.candidates must contain at least two entries")
    if top_k > len(candidates):
        raise BenchmarkInputError(
            f"{location}.top_k must be an integer from 1 to {len(candidates)}"
        )

    return BenchmarkCase(
        id=case_id,
        query=query,
        candidates=candidates,
        relevant_ids=relevant_ids,
        top_k=top_k,
    )


def _parse_candidates(value: object, location: str) -> tuple[BenchmarkCandidate, ...]:
    if not isinstance(value, list) or not value:
        raise BenchmarkInputError(f"{location}.candidates must be a non-empty array")

    candidates: list[BenchmarkCandidate] = []
    for index, raw_candidate in enumerate(value):
        candidate_location = f"{location}.candidates[{index}]"
        candidate = _object(raw_candidate, candidate_location)
        _require_exact_keys(candidate, {"id", "text"}, candidate_location)
        candidates.append(
            BenchmarkCandidate(
                id=_non_empty_string(candidate["id"], f"{candidate_location}.id"),
                text=_non_empty_string(candidate["text"], f"{candidate_location}.text"),
            )
        )

    candidate_ids = [candidate.id for candidate in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise BenchmarkInputError(f"{location}.candidates ids must be unique")
    return tuple(candidates)


def _parse_relevant_ids(
    value: object,
    candidates: tuple[BenchmarkCandidate, ...],
    location: str,
) -> frozenset[str]:
    if not isinstance(value, list) or not value:
        raise BenchmarkInputError(f"{location}.relevant_ids must be a non-empty array")

    relevant_ids = [_non_empty_string(item, f"{location}.relevant_ids") for item in value]
    if len(relevant_ids) != len(set(relevant_ids)):
        raise BenchmarkInputError(f"{location}.relevant_ids must not contain duplicates")

    candidate_ids = {candidate.id for candidate in candidates}
    unknown_ids = sorted(set(relevant_ids) - candidate_ids)
    if unknown_ids:
        raise BenchmarkInputError(
            f"{location}.relevant_ids contains unknown candidate ids: {', '.join(unknown_ids)}"
        )
    return frozenset(relevant_ids)


def _object(value: object, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BenchmarkInputError(f"{location} must be an object")
    return value


def _require_exact_keys(value: dict[str, Any], expected: set[str], location: str) -> None:
    keys = set(value)
    missing = sorted(expected - keys)
    unexpected = sorted(keys - expected)
    if missing or unexpected:
        details: list[str] = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected: {', '.join(unexpected)}")
        raise BenchmarkInputError(f"{location} has invalid fields ({'; '.join(details)})")


def _non_empty_string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkInputError(f"{location} must be a non-empty string")
    return value


def _evaluate_case(
    embedder: Embedder, case: BenchmarkCase, dimension: int
) -> BenchmarkCaseResult:
    query_vector = _embed_vector(embedder, case.query, dimension)
    scores = [
        (candidate.id, _cosine(query_vector, _embed_vector(embedder, candidate.text, dimension)))
        for candidate in case.candidates
    ]
    scores.sort(key=lambda item: (-item[1], item[0]))
    rankings = tuple(
        RankedCandidate(candidate_id=candidate_id, score=score, rank=rank)
        for rank, (candidate_id, score) in enumerate(scores, start=1)
    )
    relevant_rank = next(
        (ranking.rank for ranking in rankings if ranking.candidate_id in case.relevant_ids),
        None,
    )
    relevant_scores = [score for candidate_id, score in scores if candidate_id in case.relevant_ids]
    non_relevant_scores = [
        score for candidate_id, score in scores if candidate_id not in case.relevant_ids
    ]
    margin = (
        max(relevant_scores) - max(non_relevant_scores)
        if relevant_scores and non_relevant_scores
        else None
    )
    passed = relevant_rank is not None and relevant_rank <= case.top_k
    return BenchmarkCaseResult(
        case_id=case.id,
        rankings=rankings,
        relevant_rank=relevant_rank,
        margin=margin,
        passed=passed,
    )


def _embed_vector(embedder: Embedder, text: str, dimension: int) -> Sequence[float]:
    vector = embedder.embed(text)
    try:
        if len(vector) != dimension:
            raise EmbeddingVectorError("vector dimension mismatch")
    except TypeError as exc:
        raise EmbeddingVectorError("vectors must be non-empty and finite") from exc
    return vector


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise EmbeddingVectorError("vector dimension mismatch")
    try:
        finite = all(math.isfinite(value) for value in (*left, *right))
    except TypeError as exc:
        raise EmbeddingVectorError("vectors must be non-empty and finite") from exc
    if not left or not finite:
        raise EmbeddingVectorError("vectors must be non-empty and finite")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        raise EmbeddingVectorError("vectors must have non-zero norm")
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)
