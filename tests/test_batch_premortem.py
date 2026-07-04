"""Paso 2 del roadmap de juicio real para autoauditoría (tras PreflightGate).

BatchPremortemGate: un LLM barato (mismo patrón dual-LLM de MaintenanceAnalyst)
razona sobre riesgos de COMBINAR varios cambios ya válidos por separado, ANTES
de que ColdUpdateBatcher pague el coste de correr la suite completa de tests.
Camino de escalada: si el lote toca una ruta sensible, se convoca al Cónclave
completo (trío) en vez de confiar en el LLM barato.

Nunca se llama a un LLM real: hub falso (patrón de test_maintenance_analyst.py)
para el camino normal, `convene_fn` inyectado para el camino de escalada.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from atlas.core.inference_hub import InferenceLevel, InferenceResponse
from atlas.core.self_maintenance.batch_premortem import (
    BatchPremortemGate,
    PremortemResult,
)


class FakeHub:
    """Hub falso: enruta por task_id, mismo patrón que test_maintenance_analyst.py."""

    def __init__(self, *, verdict_text: str | None) -> None:
        self._verdict_text = verdict_text
        self.calls: list[str] = []

    def infer(self, request: Any) -> InferenceResponse:
        self.calls.append(request.task_id or "")
        text = self._verdict_text if self._verdict_text is not None else ""
        return InferenceResponse(
            text=text, provider="fake", model="fake",
            level=InferenceLevel.L1, latency_ms=1, success=self._verdict_text is not None,
        )


@dataclass
class FakeProposal:
    """Duck-typed ColdUpdateProposal: solo los campos que el gate lee."""

    id: str
    intent: str
    patch_path: str


class FakeMerkle:
    def log(self, **kwargs: Any) -> None:
        pass


def _patch_file(tmp_path: Path, name: str, content: str) -> str:
    p = tmp_path / name
    p.write_text(content)
    return str(p)


def _proposal(tmp_path: Path, *, id_: str, intent: str, patch_name: str, patch_body: str) -> FakeProposal:
    return FakeProposal(id=id_, intent=intent, patch_path=_patch_file(tmp_path, patch_name, patch_body))


@pytest.fixture
def merkle() -> FakeMerkle:
    return FakeMerkle()


class TestCheapPathOk:
    def test_valid_json_ok_no_risk_flags(self, tmp_path: Path, merkle) -> None:
        hub = FakeHub(verdict_text=json.dumps({"verdict": "ok", "risk_flags": []}))
        proposals = [
            _proposal(tmp_path, id_="p1", intent="fix typo", patch_name="p1.diff",
                      patch_body="--- a/src/foo.py\n+++ b/src/foo.py\n"),
        ]
        gate = BatchPremortemGate(hub=hub, merkle=merkle)
        result = gate.assess(proposals)
        assert result == PremortemResult(escalated=False, verdict="ok", risk_flags=[])
        assert "batch_premortem" in hub.calls

    def test_valid_json_with_risk_flags_propagated(self, tmp_path: Path, merkle) -> None:
        hub = FakeHub(verdict_text=json.dumps(
            {"verdict": "concern", "risk_flags": ["posible colisión de import"]}
        ))
        proposals = [
            _proposal(tmp_path, id_="p1", intent="add helper", patch_name="p1.diff",
                      patch_body="--- a/src/foo.py\n+++ b/src/foo.py\n"),
        ]
        gate = BatchPremortemGate(hub=hub, merkle=merkle)
        result = gate.assess(proposals)
        assert result.escalated is False
        assert result.verdict == "concern"
        assert result.risk_flags == ["posible colisión de import"]


class TestCheapPathUnparseable:
    def test_non_json_text_is_unknown_and_does_not_crash(self, tmp_path: Path, merkle) -> None:
        hub = FakeHub(verdict_text="lo siento, no puedo ayudar con eso")
        proposals = [
            _proposal(tmp_path, id_="p1", intent="fix typo", patch_name="p1.diff",
                      patch_body="--- a/src/foo.py\n+++ b/src/foo.py\n"),
        ]
        gate = BatchPremortemGate(hub=hub, merkle=merkle)
        result = gate.assess(proposals)
        assert result.verdict == "unknown"
        assert result.escalated is False


class TestEscalationPath:
    def test_sensitive_path_escalates_and_skips_cheap_hub(self, tmp_path: Path, merkle) -> None:
        hub = FakeHub(verdict_text=json.dumps({"verdict": "ok", "risk_flags": []}))
        calls: list[dict[str, Any]] = []

        def fake_convene(**kwargs: Any):
            calls.append(kwargs)

            @dataclass
            class _Ev:
                verdict: Any = "HIGH_RISK"
                reason: str = "riesgo de combinación"

            return _Ev()

        proposals = [
            _proposal(
                tmp_path, id_="p1", intent="refactor decider",
                patch_name="p1.diff",
                patch_body="--- a/src/atlas/core/cold_update_manager.py\n+++ b/src/atlas/core/cold_update_manager.py\n",
            ),
            _proposal(tmp_path, id_="p2", intent="fix typo", patch_name="p2.diff",
                      patch_body="--- a/src/foo.py\n+++ b/src/foo.py\n"),
        ]
        gate = BatchPremortemGate(hub=hub, merkle=merkle, convene_fn=fake_convene)
        result = gate.assess(proposals)

        assert result.escalated is True
        assert "batch_premortem" not in hub.calls  # no se llama al LLM barato
        assert len(calls) == 1
        kwargs = calls[0]
        assert "decision" in kwargs and "context" in kwargs
        assert kwargs["difficulty"].name == "HARD"
        assert kwargs["risk"] == "high"
        assert "refactor decider" in kwargs["decision"] or "fix typo" in kwargs["decision"]

    def test_escalation_gating_declines_is_unknown_and_does_not_block(self, tmp_path: Path, merkle) -> None:
        def fake_convene_declines(**kwargs: Any):
            return None  # gating dijo no escalar pese al riesgo detectado

        proposals = [
            _proposal(
                tmp_path, id_="p1", intent="touch governance",
                patch_name="p1.diff",
                patch_body="--- a/src/atlas/governance/rules.py\n+++ b/src/atlas/governance/rules.py\n",
            ),
        ]
        hub = FakeHub(verdict_text=json.dumps({"verdict": "ok", "risk_flags": []}))
        gate = BatchPremortemGate(hub=hub, merkle=merkle, convene_fn=fake_convene_declines)
        result = gate.assess(proposals)

        assert result.verdict == "unknown"
        # No crashea; el gate no bloquea aunque el trío decline evaluar.

    def test_synthesis_recorder_passed_to_convene_on_escalation(self, tmp_path: Path, merkle) -> None:
        recorder = object()
        received: dict[str, Any] = {}

        def fake_convene(**kwargs: Any):
            received.update(kwargs)

            @dataclass
            class _Ev:
                verdict: Any = "HIGH_RISK"
                reason: str = "riesgo real"

            return _Ev()

        proposals = [
            _proposal(
                tmp_path, id_="p1", intent="touch security",
                patch_name="p1.diff",
                patch_body="--- a/src/atlas/security/auth.py\n+++ b/src/atlas/security/auth.py\n",
            ),
        ]
        hub = FakeHub(verdict_text=json.dumps({"verdict": "ok", "risk_flags": []}))
        gate = BatchPremortemGate(
            hub=hub, merkle=merkle, synthesis_recorder=recorder, convene_fn=fake_convene,
        )
        gate.assess(proposals)

        assert received.get("synthesis_recorder") is recorder


class TestToDictRoundtrip:
    def test_to_dict_roundtrip(self) -> None:
        result = PremortemResult(
            escalated=True, verdict="concern", risk_flags=["a", "b"], reason="motivo",
        )
        d = result.to_dict()
        assert d == {
            "escalated": True,
            "verdict": "concern",
            "risk_flags": ["a", "b"],
            "reason": "motivo",
        }
