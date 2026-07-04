"""ADR-039 slice 6 (paso 4 del roadmap "juicio real para autoauditoría").

``DepAnalyst`` juzga el riesgo de UN bump de dependencia concreto ANTES de que
entre al lote. A diferencia de ``MaintenanceAnalyst`` (dual-LLM porque procesa
prosa no confiable de fuentes externas), un ``DepCandidate`` ya viene tipado y
autoritativo de PyPI — no hay prosa que extraer, así que un solo LLM de
control basta. Señal para el humano, nunca gate: nunca bloquea
``propose_bump()``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atlas.core.inference_hub import InferenceLevel, InferenceResponse
from atlas.core.self_maintenance.candidate import PROVENANCE_AUTHORITATIVE, DepCandidate, Source
from atlas.core.self_maintenance.dep_analyst import DepAnalyst, DepReviewVerdict
from atlas.core.self_maintenance.dep_proposer import DepProposer
from atlas.logging.merkle_logger import MerkleLogger


@pytest.fixture
def merkle(tmp_path: Path) -> MerkleLogger:
    return MerkleLogger(tmp_path / "merkle")


def _candidate(name: str = "click", current: str = "8.1", latest: str = "8.2.0") -> DepCandidate:
    return DepCandidate(
        name=name, current=current, latest=latest,
        source=Source(PROVENANCE_AUTHORITATIVE, f"https://pypi.org/pypi/{name}/json", ""),
    )


class FakeHub:
    """Hub de inferencia falso: un solo rol de control (sin processing-LLM,
    a diferencia del FakeHub dual-rol de test_maintenance_analyst.py)."""

    def __init__(self, *, text: str | None, success: bool = True, raise_error: bool = False) -> None:
        self._text = text
        self._success = success
        self._raise_error = raise_error
        self.calls: list[str] = []

    def infer(self, request: Any) -> InferenceResponse:
        self.calls.append(request.task_id or "")
        if self._raise_error:
            raise RuntimeError("hub caído")
        return InferenceResponse(
            text=self._text or "", provider="fake", model="fake",
            level=InferenceLevel.L1, latency_ms=1, success=self._success,
        )


class TestDepAnalystReview:
    def test_valid_low_risk_propagates(self, merkle) -> None:
        hub = FakeHub(text='{"risk":"low","summary":"parche menor","concerns":[]}')
        verdict = DepAnalyst(hub=hub, merkle=merkle).review(_candidate())
        assert verdict.risk == "low"
        assert verdict.summary == "parche menor"
        assert verdict.concerns == []

    def test_valid_high_risk_with_concerns_propagates(self, merkle) -> None:
        hub = FakeHub(text=(
            '{"risk":"high","summary":"salto mayor 1.x->2.x",'
            '"concerns":["API rota","breaking changes"]}'
        ))
        verdict = DepAnalyst(hub=hub, merkle=merkle).review(_candidate(current="1.0", latest="2.0.0"))
        assert verdict.risk == "high"
        assert verdict.concerns == ["API rota", "breaking changes"]

    def test_unparseable_text_becomes_unknown(self, merkle) -> None:
        hub = FakeHub(text="lo siento, no puedo ayudar con eso")
        verdict = DepAnalyst(hub=hub, merkle=merkle).review(_candidate())
        assert verdict.risk == "unknown"

    def test_risk_outside_enum_becomes_unknown(self, merkle) -> None:
        hub = FakeHub(text='{"risk":"muy_alto","summary":"x","concerns":[]}')
        verdict = DepAnalyst(hub=hub, merkle=merkle).review(_candidate())
        assert verdict.risk == "unknown"

    def test_hub_exception_becomes_unknown(self, merkle) -> None:
        hub = FakeHub(text=None, raise_error=True)
        verdict = DepAnalyst(hub=hub, merkle=merkle).review(_candidate())
        assert verdict.risk == "unknown"

    def test_to_dict_shape(self, merkle) -> None:
        hub = FakeHub(text='{"risk":"low","summary":"s","concerns":["c"]}')
        verdict = DepAnalyst(hub=hub, merkle=merkle).review(_candidate())
        assert verdict.to_dict() == {"risk": "low", "summary": "s", "concerns": ["c"]}


_PYPROJECT = """\
[project]
name = "demo"
dependencies = [
    "click>=8.1",
]
"""


class TestDepProposerIntegration:
    """Sigue el patrón exacto de TestDepProposer en test_dep_scout.py."""

    def test_with_analyst_injects_judgment_into_evidence(self, merkle, tmp_path) -> None:
        pp = tmp_path / "pyproject.toml"
        pp.write_text(_PYPROJECT, encoding="utf-8")
        seen: dict[str, Any] = {}

        def _propose(intent, patch_path, **kw):
            seen["kw"] = kw
            return type("P", (), {"id": "cold-0001"})()

        class _FakeAnalyst:
            def review(self, candidate: DepCandidate) -> DepReviewVerdict:
                return DepReviewVerdict(risk="moderate", summary="ojo", concerns=["breaking"])

        proposal = DepProposer(
            merkle=merkle, propose=_propose, pyproject_path=pp,
            installed_version=lambda _n: "8.2.0",
            analyst=_FakeAnalyst(),
        ).propose_bump(_candidate())

        assert proposal.id == "cold-0001"
        assert seen["kw"]["evidence"]["judgment"] == {
            "risk": "moderate", "summary": "ojo", "concerns": ["breaking"],
        }

    def test_without_analyst_behaves_identically(self, merkle, tmp_path) -> None:
        pp = tmp_path / "pyproject.toml"
        pp.write_text(_PYPROJECT, encoding="utf-8")
        seen: dict[str, Any] = {}

        def _propose(intent, patch_path, **kw):
            seen["kw"] = kw
            return type("P", (), {"id": "x"})()

        DepProposer(
            merkle=merkle, propose=_propose, pyproject_path=pp,
            installed_version=lambda _n: "8.2.0",
        ).propose_bump(_candidate())

        assert "judgment" not in seen["kw"]["evidence"]

    def test_analyst_exception_never_blocks_proposal(self, merkle, tmp_path) -> None:
        pp = tmp_path / "pyproject.toml"
        pp.write_text(_PYPROJECT, encoding="utf-8")
        seen: dict[str, Any] = {}

        def _propose(intent, patch_path, **kw):
            seen["kw"] = kw
            return type("P", (), {"id": "x"})()

        class _BoomAnalyst:
            def review(self, candidate: DepCandidate) -> DepReviewVerdict:
                raise RuntimeError("boom")

        proposal = DepProposer(
            merkle=merkle, propose=_propose, pyproject_path=pp,
            installed_version=lambda _n: "8.2.0",
            analyst=_BoomAnalyst(),
        ).propose_bump(_candidate())

        assert proposal is not None
        assert "judgment" not in seen["kw"]["evidence"]
