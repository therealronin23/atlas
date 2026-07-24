"""Tests del registro de rechazo permanente (ADR-077.3) -- mismo patrón
append-only que `GatedLessonRecorder`: un rechazo nunca se borra, un
`unblock` es una línea nueva que revoca, no una mutación de la original.
Corta en corto los reintentos en bucle (hallazgo real: `mcp_adopt` contra
`ai.adeu/adeu` se reintentó 6 veces en un día en el log Merkle real).

También cubre la objeción del Cónclave sobre entropía de `descriptor`: un
regression test contra el esquema REAL de evidence de dep_proposer.py
(`from`/`to`/`latest`/`source`) confirma que dos bumps de versión distintos
producen `action_hash` distinto -- no colisiona y bloquea una actualización
legítima futura solo porque el paquete es el mismo.
"""

from __future__ import annotations

from pathlib import Path

from atlas.core.adversarial_panel import Severity
from atlas.core.decider.decider import DecisionAction, action_hash
from atlas.core.decider.security_council_gate import SecurityReport
from atlas.core.decider.security_council_registry import (
    is_rejected,
    record_rejection,
    unblock,
)

_REPORT = SecurityReport(
    severity=Severity.MAJOR,
    checks_run=["scan", "llm_audit"],
    triggered_by="riesgo detectado",
    recommended_action="revisar manual",
)


def test_not_rejected_when_registry_missing(tmp_path: Path) -> None:
    assert is_rejected("abc123", tmp_path / "rejected.jsonl") is False


def test_rejected_after_record_rejection(tmp_path: Path) -> None:
    path = tmp_path / "rejected.jsonl"
    record_rejection("abc123", "mcp_adopt", "ai.adeu/adeu", _REPORT, path)
    assert is_rejected("abc123", path) is True
    assert is_rejected("otro-hash", path) is False


def test_record_rejection_persists_full_report(tmp_path: Path) -> None:
    import json

    path = tmp_path / "rejected.jsonl"
    record_rejection("abc123", "mcp_adopt", "ai.adeu/adeu", _REPORT, path)
    line = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert line["report"]["severity"] == "MAJOR"
    assert line["report"]["triggered_by"] == "riesgo detectado"
    assert line["kind"] == "mcp_adopt"
    assert line["descriptor"] == "ai.adeu/adeu"


def test_unblock_clears_rejection(tmp_path: Path) -> None:
    path = tmp_path / "rejected.jsonl"
    record_rejection("abc123", "mcp_adopt", "ai.adeu/adeu", _REPORT, path)
    assert unblock("abc123", path, reason="falso positivo confirmado", actor="operador") is True
    assert is_rejected("abc123", path) is False


def test_unblock_returns_false_when_nothing_to_unblock(tmp_path: Path) -> None:
    path = tmp_path / "rejected.jsonl"
    assert unblock("nunca-rechazado", path, reason="x", actor="operador") is False


def test_unblock_never_deletes_the_original_line(tmp_path: Path) -> None:
    """Append-only: el rechazo original sigue en el fichero tras el unblock --
    trazabilidad completa, no reescritura."""
    path = tmp_path / "rejected.jsonl"
    record_rejection("abc123", "mcp_adopt", "ai.adeu/adeu", _REPORT, path)
    unblock("abc123", path, reason="x", actor="operador")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert '"event": "rejected"' in lines[0] or '"rejected"' in lines[0]


def test_reject_again_after_unblock_is_rejected_again(tmp_path: Path) -> None:
    path = tmp_path / "rejected.jsonl"
    record_rejection("abc123", "mcp_adopt", "ai.adeu/adeu", _REPORT, path)
    unblock("abc123", path, reason="x", actor="operador")
    record_rejection("abc123", "mcp_adopt", "ai.adeu/adeu", _REPORT, path)
    assert is_rejected("abc123", path) is True


def test_action_hash_differs_for_distinguishable_dependency_bump_descriptors() -> None:
    """Esquema real de evidence.values() de dep_proposer.py (from/to/latest/
    source) -- dos bumps de versión distintos del MISMO paquete no deben
    colisionar en el mismo action_hash (objeción real del Cónclave: un
    rechazo permanente no debe bloquear una actualización legítima futura)."""
    def descriptor_for(from_v: str, to_v: str) -> str:
        evidence = {
            "dependency": "click", "from": from_v, "to": to_v,
            "latest": to_v, "source": "https://pypi.org/pypi/click/json",
        }
        return " ".join(str(v) for v in evidence.values()).strip()

    action_a = DecisionAction(
        kind="cold_update_apply", descriptor=descriptor_for("8.4.1", "8.4.2"),
        mutating=True, reversible=True,
    )
    action_b = DecisionAction(
        kind="cold_update_apply", descriptor=descriptor_for("8.4.2", "8.4.3"),
        mutating=True, reversible=True,
    )
    assert action_hash(action_a, "bump click") != action_hash(action_b, "bump click")
