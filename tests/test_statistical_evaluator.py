"""ADR-019 — StatisticalEvaluator tests."""

from __future__ import annotations

from atlas.lab.evaluator import StatisticalEvaluator


def test_recommend_promotion_insufficient_samples() -> None:
    ev = StatisticalEvaluator(min_samples=3)
    r = ev.recommend_promotion([10.0, 20.0], [30.0])
    assert not r.recommended
    assert "samples" in r.reason


def test_recommend_promotion_ok_when_baseline_empty() -> None:
    ev = StatisticalEvaluator(min_samples=2)
    r = ev.recommend_promotion([], [10.0, 12.0, 11.0])
    assert r.recommended


def test_recommend_promotion_rejects_latency_regression() -> None:
    ev = StatisticalEvaluator(min_samples=3, max_regression_ratio=0.1)
    baseline = [100.0, 110.0, 105.0]
    candidate = [500.0, 520.0, 510.0]
    r = ev.recommend_promotion(baseline, candidate)
    assert not r.recommended
    assert "regression" in r.reason


def test_enabled_env(monkeypatch) -> None:
    monkeypatch.delenv("ATLAS_STAT_VALIDATE", raising=False)
    assert StatisticalEvaluator.enabled() is False
    monkeypatch.setenv("ATLAS_STAT_VALIDATE", "1")
    assert StatisticalEvaluator.enabled() is True
