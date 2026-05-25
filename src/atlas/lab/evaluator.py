"""
ADR-019 — Statistical Validation Framework (minimal v1).

Compares sample series (latency ms, success rate) without external dependencies.
Used optionally by Gate H before promoting generated patterns.
"""

from __future__ import annotations

import os
import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class ComparisonResult:
    recommended: bool
    reason: str
    baseline_mean: float | None = None
    candidate_mean: float | None = None
    sample_count_baseline: int = 0
    sample_count_candidate: int = 0


class StatisticalEvaluator:
    """Lightweight promotion gate from observed execution metrics."""

    def __init__(
        self,
        *,
        min_samples: int = 3,
        max_regression_ratio: float = 0.25,
    ) -> None:
        self._min_samples = min_samples
        self._max_regression = max_regression_ratio

    @staticmethod
    def enabled() -> bool:
        return os.environ.get("ATLAS_STAT_VALIDATE", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )

    def recommend_promotion(
        self,
        baseline_latencies_ms: list[float],
        candidate_latencies_ms: list[float],
        *,
        baseline_success_rate: float | None = None,
        candidate_success_rate: float | None = None,
    ) -> ComparisonResult:
        if len(candidate_latencies_ms) < self._min_samples:
            return ComparisonResult(
                recommended=False,
                reason=f"candidate samples < {self._min_samples}",
                sample_count_candidate=len(candidate_latencies_ms),
            )

        if baseline_latencies_ms:
            if len(baseline_latencies_ms) < self._min_samples:
                return ComparisonResult(
                    recommended=True,
                    reason="insufficient baseline; candidate only gate",
                    sample_count_baseline=len(baseline_latencies_ms),
                    sample_count_candidate=len(candidate_latencies_ms),
                    candidate_mean=statistics.mean(candidate_latencies_ms),
                )
            b_mean = statistics.mean(baseline_latencies_ms)
            c_mean = statistics.mean(candidate_latencies_ms)
            if b_mean > 0 and c_mean > b_mean * (1.0 + self._max_regression):
                return ComparisonResult(
                    recommended=False,
                    reason="candidate latency regression exceeds threshold",
                    baseline_mean=b_mean,
                    candidate_mean=c_mean,
                    sample_count_baseline=len(baseline_latencies_ms),
                    sample_count_candidate=len(candidate_latencies_ms),
                )

        if (
            baseline_success_rate is not None
            and candidate_success_rate is not None
            and candidate_success_rate < baseline_success_rate - 0.05
        ):
            return ComparisonResult(
                recommended=False,
                reason="candidate success rate below baseline",
            )

        final_c = statistics.mean(candidate_latencies_ms) if candidate_latencies_ms else None
        final_b = statistics.mean(baseline_latencies_ms) if baseline_latencies_ms else None
        return ComparisonResult(
            recommended=True,
            reason="ok",
            baseline_mean=final_b,
            candidate_mean=final_c,
            sample_count_baseline=len(baseline_latencies_ms),
            sample_count_candidate=len(candidate_latencies_ms),
        )
