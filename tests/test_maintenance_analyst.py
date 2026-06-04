"""ADR-039 slice 2 — Analyst dual-LLM + gate de corroboración.

El Analyst digiere un candidato bajo separación datos/control y propone solo lo
corroborado por fuente autoritativa. La inferencia se mockea con un hub falso que
enruta por ``task_id`` (processing vs control); nunca se llama a un LLM real.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.core.inference_hub import InferenceLevel, InferenceResponse
from atlas.core.self_maintenance import (
    PROVENANCE_AUTHORITATIVE,
    PROVENANCE_COMMUNITY,
    MaintenanceAnalyst,
    McpCandidate,
    McpProposal,
    Source,
    format_proposal,
)
from atlas.logging.merkle_logger import MerkleLogger


class FakeHub:
    """Hub de inferencia falso. Enruta por ``task_id``: el processing-LLM
    devuelve el resumen tipado, el control-LLM la lista de riesgos."""

    def __init__(self, *, summary: dict | str | None, risks: list | str | None) -> None:
        self._summary = summary
        self._risks = risks
        self.calls: list[str] = []

    def infer(self, request) -> InferenceResponse:
        self.calls.append(request.task_id or "")
        if request.task_id == "analyst.processing":
            text = self._summary if isinstance(self._summary, str) else json.dumps(self._summary)
            success = self._summary is not None
        else:
            text = self._risks if isinstance(self._risks, str) else json.dumps(self._risks)
            success = True
        return InferenceResponse(
            text=text or "", provider="fake", model="fake",
            level=InferenceLevel.L1, latency_ms=1, success=success,
        )


@pytest.fixture
def merkle(tmp_path: Path) -> MerkleLogger:
    return MerkleLogger(tmp_path / "merkle")


def _candidate(*, provenance: str = PROVENANCE_AUTHORITATIVE, name="fs-mcp", version="1.2.0") -> McpCandidate:
    return McpCandidate(
        name=name,
        version=version,
        cmd=["npx", "-y", "@modelcontextprotocol/server-filesystem"],
        declared_tools=["read_file", "write_file"],
        sources=[Source(provenance=provenance, url="https://reg.example/fs-mcp", raw_excerpt="...")],
    )


class TestCorroborationGate:
    def test_authoritative_match_produces_proposal(self, merkle) -> None:
        hub = FakeHub(
            summary={"name": "fs-mcp", "version": "1.2.0", "maintainer": "mcp", "purpose": "FS access"},
            risks=["acceso a disco"],
        )
        prop = MaintenanceAnalyst(merkle=merkle, hub=hub).analyze(_candidate())
        assert isinstance(prop, McpProposal)
        assert prop.capability == "fs-mcp" and prop.version == "1.2.0"
        assert prop.purpose == "FS access"
        assert prop.risks == ["acceso a disco"]
        assert any(e.corroborates for e in prop.evidence)
        assert prop.status == "proposed"

    def test_community_only_is_dropped(self, merkle) -> None:
        hub = FakeHub(
            summary={"name": "fs-mcp", "version": "1.2.0", "maintainer": "x", "purpose": "y"},
            risks=[],
        )
        prop = MaintenanceAnalyst(merkle=merkle, hub=hub).analyze(
            _candidate(provenance=PROVENANCE_COMMUNITY)
        )
        assert prop is None  # foro nunca corrobora → fail-closed

    def test_version_mismatch_is_dropped(self, merkle) -> None:
        hub = FakeHub(
            summary={"name": "fs-mcp", "version": "9.9.9", "maintainer": "x", "purpose": "y"},
            risks=[],
        )
        prop = MaintenanceAnalyst(merkle=merkle, hub=hub).analyze(_candidate(version="1.2.0"))
        assert prop is None

    def test_unparseable_processing_output_fails_closed(self, merkle) -> None:
        hub = FakeHub(summary="lo siento, no puedo ayudar con eso", risks=[])
        prop = MaintenanceAnalyst(merkle=merkle, hub=hub).analyze(_candidate())
        assert prop is None

    def test_processing_failure_fails_closed(self, merkle) -> None:
        hub = FakeHub(summary=None, risks=[])
        prop = MaintenanceAnalyst(merkle=merkle, hub=hub).analyze(_candidate())
        assert prop is None


class TestDualLLMSeparation:
    def test_both_roles_invoked(self, merkle) -> None:
        hub = FakeHub(
            summary={"name": "fs-mcp", "version": "1.2.0", "maintainer": "m", "purpose": "p"},
            risks=["r"],
        )
        MaintenanceAnalyst(merkle=merkle, hub=hub).analyze(_candidate())
        assert "analyst.processing" in hub.calls
        assert "analyst.control" in hub.calls

    def test_control_not_invoked_when_dropped(self, merkle) -> None:
        # Sin corroboración no hay redacción de control: nada que proponer.
        hub = FakeHub(summary=None, risks=[])
        MaintenanceAnalyst(merkle=merkle, hub=hub).analyze(_candidate(provenance=PROVENANCE_COMMUNITY))
        assert "analyst.control" not in hub.calls

    def test_garbage_risks_become_empty(self, merkle) -> None:
        hub = FakeHub(
            summary={"name": "fs-mcp", "version": "1.2.0", "maintainer": "m", "purpose": "p"},
            risks="no es json",
        )
        prop = MaintenanceAnalyst(merkle=merkle, hub=hub).analyze(_candidate())
        assert prop is not None and prop.risks == []


class TestAudit:
    def test_proposal_audited(self, merkle) -> None:
        hub = FakeHub(
            summary={"name": "fs-mcp", "version": "1.2.0", "maintainer": "m", "purpose": "p"},
            risks=["r"],
        )
        prop = MaintenanceAnalyst(merkle=merkle, hub=hub).analyze(_candidate())
        recs = [r.to_dict() for r in merkle.tail(20)]
        rec = next(r for r in recs if r["action"] == "self_maintenance.analyst_analyze")
        assert rec["result"] == "proposed"
        assert rec["payload"]["proposal_id"] == prop.id
        assert rec["payload"]["corroborated"] is True

    def test_drop_audited(self, merkle) -> None:
        hub = FakeHub(summary=None, risks=[])
        MaintenanceAnalyst(merkle=merkle, hub=hub).analyze(_candidate(provenance=PROVENANCE_COMMUNITY))
        recs = [r.to_dict() for r in merkle.tail(20)]
        rec = next(r for r in recs if r["action"] == "self_maintenance.analyst_analyze")
        assert rec["result"] == "dropped"
        assert rec["payload"]["corroborated"] is False

    def test_audit_failure_does_not_break(self, merkle, monkeypatch) -> None:
        def _boom(*a, **k):
            raise RuntimeError("merkle caído")

        monkeypatch.setattr(merkle, "log", _boom)
        hub = FakeHub(
            summary={"name": "fs-mcp", "version": "1.2.0", "maintainer": "m", "purpose": "p"},
            risks=["r"],
        )
        prop = MaintenanceAnalyst(merkle=merkle, hub=hub).analyze(_candidate())
        assert isinstance(prop, McpProposal)


class TestPresentation:
    def test_format_contains_key_fields(self, merkle) -> None:
        hub = FakeHub(
            summary={"name": "fs-mcp", "version": "1.2.0", "maintainer": "m", "purpose": "acceso FS"},
            risks=["acceso a disco"],
        )
        prop = MaintenanceAnalyst(merkle=merkle, hub=hub).analyze(_candidate())
        msg = format_proposal(prop)
        assert "fs-mcp" in msg and "1.2.0" in msg
        assert "acceso a disco" in msg
        assert "reg.example" in msg
        assert "aprobación" in msg

    def test_to_dict_shape(self, merkle) -> None:
        hub = FakeHub(
            summary={"name": "fs-mcp", "version": "1.2.0", "maintainer": "m", "purpose": "p"},
            risks=["r"],
        )
        prop = MaintenanceAnalyst(merkle=merkle, hub=hub).analyze(_candidate())
        d = prop.to_dict()
        assert set(d) == {
            "id", "capability", "version", "cmd",
            "purpose", "risks", "evidence", "status",
        }
        assert all("corroborates" in e for e in d["evidence"])
