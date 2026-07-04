"""Tests para EvolutionGate (wrapper genérico sobre openevolve).

Nunca llama a openevolve real ni a ningún LLM real: `run_evolution` se
sustituye siempre por un fake vía monkeypatch. Ver
src/atlas/core/self_maintenance/evolution_gate.py para el alcance del slice.
"""

from __future__ import annotations

from typing import Any

import pytest

from atlas.core.self_maintenance.evolution_gate import EvolutionGate, EvolutionOutcome


def _make_gate(**overrides: Any) -> EvolutionGate:
    kwargs: dict[str, Any] = dict(
        api_base="https://api.groq.com/openai/v1",
        api_key="test-key",
        model="test-model",
        iterations=5,
    )
    kwargs.update(overrides)
    return EvolutionGate(**kwargs)


class _FakeResult:
    def __init__(self, best_code: str, best_score: float) -> None:
        self.best_code = best_code
        self.best_score = best_score


def test_evolve_success_propagates_best_code_and_score(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run_evolution(**kwargs: Any) -> _FakeResult:
        return _FakeResult(best_code="def solve(): return 42", best_score=0.95)

    monkeypatch.setattr(
        "openevolve.api.run_evolution",
        lambda *a, **kw: fake_run_evolution(**kw),
    )

    gate = _make_gate()
    outcome = gate.evolve(initial_code="def solve(): pass", evaluator=lambda path: {"score": 0.0})

    assert outcome.succeeded is True
    assert outcome.best_code == "def solve(): return 42"
    assert outcome.best_score == 0.95


def test_evolve_failure_is_fail_open_never_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    def raising_run_evolution(*a: Any, **kw: Any) -> Any:
        raise RuntimeError("API caída")

    monkeypatch.setattr("openevolve.api.run_evolution", raising_run_evolution)

    gate = _make_gate()
    outcome = gate.evolve(initial_code="def solve(): pass", evaluator=lambda path: {"score": 0.0})

    assert outcome.succeeded is False
    assert "API caída" in outcome.reason
    assert outcome.best_code == ""
    assert outcome.best_score == 0.0


def test_evolve_passes_evaluator_through_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run_evolution(*, initial_program: str, evaluator: Any, **kw: Any) -> _FakeResult:
        captured["evaluator"] = evaluator
        return _FakeResult(best_code="x", best_score=1.0)

    monkeypatch.setattr("openevolve.api.run_evolution", fake_run_evolution)

    def my_identifiable_evaluator(path: str) -> dict[str, Any]:
        return {"score": 1.0}

    gate = _make_gate()
    gate.evolve(initial_code="code", evaluator=my_identifiable_evaluator)

    assert captured["evaluator"] is my_identifiable_evaluator


def test_evolve_builds_config_with_constructor_args(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run_evolution(**kwargs: Any) -> _FakeResult:
        captured.update(kwargs)
        return _FakeResult(best_code="x", best_score=1.0)

    monkeypatch.setattr("openevolve.api.run_evolution", fake_run_evolution)

    gate = _make_gate(
        api_base="https://custom.example/v1",
        api_key="secret-123",
        model="my-model",
        iterations=17,
    )
    gate.evolve(initial_code="code", evaluator=lambda path: {"score": 0.0})

    config = captured["config"]
    assert config.max_iterations == 17
    assert captured["iterations"] == 17
    assert config.llm.api_base == "https://custom.example/v1"
    assert config.llm.api_key == "secret-123"
    assert len(config.llm.models) == 1
    assert config.llm.models[0].name == "my-model"


def test_evolution_outcome_to_dict_roundtrip() -> None:
    outcome = EvolutionOutcome(
        succeeded=True,
        best_code="def f(): pass",
        best_score=0.42,
        reason="",
    )
    data = outcome.to_dict()

    assert data == {
        "succeeded": True,
        "best_code": "def f(): pass",
        "best_score": 0.42,
        "reason": "",
    }
