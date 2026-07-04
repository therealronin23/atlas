"""Tests para EvolutionGate (wrapper genérico sobre openevolve).

Nunca llama a openevolve real ni a ningún LLM real: `run_evolution` se
sustituye siempre por un fake vía sys.modules. Ver
src/atlas/core/self_maintenance/evolution_gate.py para el alcance del slice.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest

from atlas.core.self_maintenance.evolution_gate import EvolutionGate, EvolutionOutcome


def _install_fake_openevolve(monkeypatch: pytest.MonkeyPatch, run_evolution: Any) -> None:
    """Inyecta openevolve falso — no requiere el extra [evolution] en CI."""
    config_mod = ModuleType("openevolve.config")

    class Config:
        def __init__(self, max_iterations: int = 10) -> None:
            self.max_iterations = max_iterations
            self.llm: Any = None

    class LLMConfig:
        def __init__(self, api_base: str = "", api_key: str = "", models: list[Any] | None = None) -> None:
            self.api_base = api_base
            self.api_key = api_key
            self.models = models or []

    class LLMModelConfig:
        def __init__(self, name: str = "", weight: float = 1.0) -> None:
            self.name = name
            self.weight = weight

    config_mod.Config = Config
    config_mod.LLMConfig = LLMConfig
    config_mod.LLMModelConfig = LLMModelConfig

    api_mod = ModuleType("openevolve.api")
    api_mod.run_evolution = run_evolution

    root = ModuleType("openevolve")
    root.api = api_mod
    root.config = config_mod

    monkeypatch.setitem(sys.modules, "openevolve", root)
    monkeypatch.setitem(sys.modules, "openevolve.api", api_mod)
    monkeypatch.setitem(sys.modules, "openevolve.config", config_mod)


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

    _install_fake_openevolve(monkeypatch, fake_run_evolution)

    gate = _make_gate()
    outcome = gate.evolve(initial_code="def solve(): pass", evaluator=lambda path: {"score": 0.0})

    assert outcome.succeeded is True
    assert outcome.best_code == "def solve(): return 42"
    assert outcome.best_score == 0.95


def test_evolve_failure_is_fail_open_never_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    def raising_run_evolution(*a: Any, **kw: Any) -> Any:
        raise RuntimeError("API caída")

    _install_fake_openevolve(monkeypatch, raising_run_evolution)

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

    _install_fake_openevolve(monkeypatch, fake_run_evolution)

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

    _install_fake_openevolve(monkeypatch, fake_run_evolution)

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
