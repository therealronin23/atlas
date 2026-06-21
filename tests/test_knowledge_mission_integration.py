"""Tests T2b — Integración de run_mission con dependencias deterministas reales.

Ejercita run_mission de extremo a extremo usando FakeSource (sin red) y el
KnowledgeVerifier REAL. Sin monkeypatch sobre el verifier.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from atlas.knowledge.base import KnowledgeBase
from atlas.knowledge.mission import Mission, MissionReport
from atlas.knowledge.run import run_mission
from atlas.knowledge.sources import RawRecord
from atlas.knowledge.verifier import KnowledgeVerifier


# ---------------------------------------------------------------------------
# Fuente fake determinista — patrón FakeSource de test_knowledge_mission.py
# ---------------------------------------------------------------------------

class FakeSource:
    def __init__(self, source_id: str, domain: str, records: list[RawRecord]) -> None:
        self.source_id = source_id
        self.domain = domain
        self._records = records

    def fetch(self, query: Any) -> list[RawRecord]:
        return self._records


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mission(source_id: str, domain: str = "seguridad/cve") -> Mission:
    return Mission(
        id="integ-m1",
        domain=domain,
        goal="prueba de integracion",
        source_ids=[source_id],
        cadence_s=3600,
    )


# ---------------------------------------------------------------------------
# Camino feliz: payload JSON no vacío → ingested==1, rejected==0
# El artifact queda en la base con el content esperado.
# ---------------------------------------------------------------------------

def test_run_mission_camino_feliz(tmp_path: Path) -> None:
    payload_dict = {"vuln": "CVE-2099-9999", "severity": "critical"}
    payload = json.dumps(payload_dict)
    fuente = FakeSource(
        "fuente-real",
        "seguridad/cve",
        [RawRecord(payload=payload, url="https://example.com/vuln", status=200)],
    )
    base = KnowledgeBase(tmp_path)
    verifier = KnowledgeVerifier()
    mission = _mission("fuente-real")

    report: MissionReport = run_mission(
        mission,
        sources={"fuente-real": fuente},
        base=base,
        verifier=verifier,
    )

    assert report.ingested == 1
    assert report.rejected == 0
    assert report.errors == ()

    # El artifact debe estar persistido en la base
    artifacts = KnowledgeBase(tmp_path).query(mission.domain)
    assert len(artifacts) == 1
    assert artifacts[0].content == payload_dict


# ---------------------------------------------------------------------------
# Camino de rechazo real: content vacío → verifier FAIL → rejected==1
# ---------------------------------------------------------------------------

def test_run_mission_rechazo_content_vacio(tmp_path: Path) -> None:
    payload_vacio = json.dumps({})
    fuente = FakeSource(
        "fuente-vacia",
        "seguridad/cve",
        [RawRecord(payload=payload_vacio, url="https://example.com/empty", status=200)],
    )
    base = KnowledgeBase(tmp_path)
    verifier = KnowledgeVerifier()
    mission = _mission("fuente-vacia")

    report: MissionReport = run_mission(
        mission,
        sources={"fuente-vacia": fuente},
        base=base,
        verifier=verifier,
    )

    assert report.ingested == 0
    assert report.rejected == 1
    assert report.errors == ()
