"""ADR-040 slice 5 — HybridDecider + flip de config (ATLAS_DECIDER)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from atlas.core.decider import (
    Allow,
    AutonomousDecider,
    DecisionAction,
    Decider,
    Deny,
    HumanDecider,
    HybridDecider,
    RequiresHuman,
    make_decider,
)


class _Spy:
    """Decisor que registra si fue invocado y devuelve un veredicto fijo."""

    def __init__(self, verdict) -> None:
        self._verdict = verdict
        self.called = False

    def decide(self, action: DecisionAction, sanctioned_intent: str, context: Mapping[str, object]):
        self.called = True
        return self._verdict


def _hybrid(auto_verdict, human_verdict):
    auto = _Spy(auto_verdict)
    human = _Spy(human_verdict)
    return HybridDecider(autonomous=auto, human=human), auto, human


class TestHybridRouting:
    def test_high_tier_routes_to_human(self) -> None:
        dec, auto, human = _hybrid(Allow(), RequiresHuman(reason="h"))
        verdict = dec.decide(DecisionAction(kind="route", sensitivity="high"), "i", {})
        assert human.called and not auto.called
        assert isinstance(verdict, RequiresHuman)

    def test_normal_tier_routes_to_autonomous(self) -> None:
        dec, auto, human = _hybrid(Allow(reason="a"), RequiresHuman())
        verdict = dec.decide(DecisionAction(kind="route", sensitivity="normal"), "i", {})
        assert auto.called and not human.called
        assert isinstance(verdict, Allow)

    def test_satisfies_decider_protocol(self) -> None:
        assert isinstance(HybridDecider(), Decider)


class TestHybridWithRealComponents:
    def test_high_suspends_via_human(self) -> None:
        dec = HybridDecider()
        verdict = dec.decide(DecisionAction(kind="route", sensitivity="high"), "i", {})
        assert isinstance(verdict, RequiresHuman)

    def test_normal_ioc_denied_by_autonomous(self) -> None:
        dec = HybridDecider()
        verdict = dec.decide(
            DecisionAction(kind="agentic_tool", descriptor="rm -rf /"), "i", {}
        )
        assert isinstance(verdict, Deny)

    def test_normal_reversible_allowed_by_autonomous(self) -> None:
        dec = HybridDecider()
        verdict = dec.decide(
            DecisionAction(kind="route", requires_approval=True, sensitivity="normal"), "i", {}
        )
        assert isinstance(verdict, Allow)


class TestFactory:
    def test_default_is_human(self) -> None:
        assert isinstance(make_decider(None), HumanDecider)

    def test_unknown_falls_back_to_human(self) -> None:
        assert isinstance(make_decider("garbage"), HumanDecider)

    @pytest.mark.parametrize(
        "name,cls",
        [
            ("human", HumanDecider),
            ("autonomous", AutonomousDecider),
            ("hybrid", HybridDecider),
            ("  HYBRID  ", HybridDecider),
        ],
    )
    def test_named_selection(self, name, cls) -> None:
        assert isinstance(make_decider(name), cls)


class TestConfigFlip:
    def _orch(self, tmp_path: Path):
        from atlas.core.orchestrator import Orchestrator
        import atlas.governance.governance_l0 as g

        g.GovernanceL0._instance = None
        ws = tmp_path / "atlas"
        ws.mkdir()
        return Orchestrator(workspace=ws)

    def test_env_flip_to_hybrid(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ATLAS_DECIDER", "hybrid")
        orch = self._orch(tmp_path)
        assert isinstance(orch._decider, HybridDecider)

    def test_env_flip_to_autonomous(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ATLAS_DECIDER", "autonomous")
        orch = self._orch(tmp_path)
        assert isinstance(orch._decider, AutonomousDecider)

    def test_default_env_is_human(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("ATLAS_DECIDER", raising=False)
        orch = self._orch(tmp_path)
        assert isinstance(orch._decider, HumanDecider)
