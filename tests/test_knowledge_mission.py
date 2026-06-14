"""Tests T7 — Mission + MissionReport + MissionRunner.run_once (ADR-049)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from atlas.knowledge.artifact import KnowledgeArtifact
from atlas.knowledge.base import KnowledgeBase
from atlas.knowledge.mission import Mission, MissionReport, MissionRunner
from atlas.knowledge.sources import RawRecord
from atlas.knowledge.verifier import KnowledgeVerifier


# ---------------------------------------------------------------------------
# Fuentes fake — sin red
# ---------------------------------------------------------------------------

class FakeSource:
    def __init__(self, source_id: str, domain: str, records: list[RawRecord]) -> None:
        self.source_id = source_id
        self.domain = domain
        self._records = records

    def fetch(self, query: Any) -> list[RawRecord]:
        return self._records


class BoomSource:
    """Fuente que siempre lanza en fetch."""
    source_id = "boom"
    domain = "test"

    def fetch(self, query: Any) -> list[RawRecord]:
        raise RuntimeError("boom!")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_runner(sources: dict, tmp_path: Path) -> MissionRunner:
    return MissionRunner(
        sources=sources,
        verifier=KnowledgeVerifier(),
        base=KnowledgeBase(tmp_path),
    )


def _mission(*source_ids: str) -> Mission:
    return Mission(
        id="m1",
        domain="test/domain",
        goal="test",
        source_ids=list(source_ids),
        cadence_s=3600,
    )


# ---------------------------------------------------------------------------
# (a) payload válido → ingested=1, rejected=0
# ---------------------------------------------------------------------------

def test_run_once_valid_payload(tmp_path: Path) -> None:
    payload = json.dumps({"vuln": "CVE-2025-0001", "severity": "high"})
    src = FakeSource("src1", "security/cve", [RawRecord(payload=payload, url="https://example.com/vuln", status=200)])

    runner = _make_runner({"src1": src}, tmp_path)
    report = runner.run_once(_mission("src1"))

    assert report.mission_id == "m1"
    assert report.ingested == 1
    assert report.rejected == 0
    assert report.errors == ()
    assert len(report.ingested_ids) == 1
    # El id es determinista: source_id + primeros 16 chars del sha256
    assert report.ingested_ids[0].startswith("src1:")

    # El artifact quedó en la base
    base = KnowledgeBase(tmp_path)
    artifacts = base.query("test/domain")
    assert len(artifacts) == 1
    assert artifacts[0].content == {"vuln": "CVE-2025-0001", "severity": "high"}


# ---------------------------------------------------------------------------
# (b) content vacío → verifier da FAIL → KnowledgeRejected → rejected=1
# ---------------------------------------------------------------------------

def test_run_once_empty_content_rejected(tmp_path: Path) -> None:
    # Payload JSON vacío: content={} → verifier FAIL (content_nonempty check)
    payload = json.dumps({})
    src = FakeSource("src2", "test", [RawRecord(payload=payload, url="https://example.com/empty", status=200)])

    runner = _make_runner({"src2": src}, tmp_path)
    report = runner.run_once(_mission("src2"))

    assert report.ingested == 0
    assert report.rejected == 1
    assert report.errors == ()
    assert report.ingested_ids == ()


# ---------------------------------------------------------------------------
# (c) fuente que lanza en fetch → error capturado, las demás continúan
# ---------------------------------------------------------------------------

def test_run_once_fetch_error_isolated(tmp_path: Path) -> None:
    payload = json.dumps({"data": "ok"})
    good_src = FakeSource("good", "test", [RawRecord(payload=payload, url="https://example.com/good", status=200)])
    boom = BoomSource()

    runner = _make_runner({"good": good_src, "boom": boom}, tmp_path)
    mission = Mission(id="m2", domain="test", goal="test", source_ids=["boom", "good"], cadence_s=60)
    report = runner.run_once(mission)

    # boom falló pero good fue procesado
    assert report.ingested == 1
    assert report.rejected == 0
    assert len(report.errors) == 1
    err_src, err_msg = report.errors[0]
    assert err_src == "boom"
    assert "boom!" in err_msg


# ---------------------------------------------------------------------------
# Fuente no registrada → error en report, continúa
# ---------------------------------------------------------------------------

def test_run_once_missing_source(tmp_path: Path) -> None:
    runner = _make_runner({}, tmp_path)
    report = runner.run_once(_mission("nonexistent"))

    assert report.ingested == 0
    assert report.errors[0][0] == "nonexistent"
    assert "no registrada" in report.errors[0][1]


# ---------------------------------------------------------------------------
# Mission es frozen
# ---------------------------------------------------------------------------

def test_mission_frozen() -> None:
    m = _mission("s1")
    with pytest.raises((AttributeError, TypeError)):
        m.id = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MissionReport es frozen
# ---------------------------------------------------------------------------

def test_mission_report_frozen() -> None:
    r = MissionReport(mission_id="x", ingested=0, rejected=0, errors=())
    with pytest.raises((AttributeError, TypeError)):
        r.ingested = 5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# queries dict se pasa a fetch
# ---------------------------------------------------------------------------

def test_run_once_query_forwarded(tmp_path: Path) -> None:
    received: list[Any] = []

    class QueryCapture:
        source_id = "cap"
        domain = "test"
        def fetch(self, query: Any) -> list[RawRecord]:
            received.append(query)
            payload = json.dumps({"q": str(query)})
            return [RawRecord(payload=payload, url="https://x.com", status=200)]

    runner = _make_runner({"cap": QueryCapture()}, tmp_path)
    runner.run_once(_mission("cap"), queries={"cap": "my-package"})

    assert received == ["my-package"]
