"""Tests de `resolve_council_verdict` (ADR-077.2) -- escalada de dos niveles:
el auditor único (barato) resuelve la mayoría de los casos; solo lo `flagged`
(o `offensive_action`, siempre, dado su perfil de consecuencias externas
irreversibles) paga una segunda opinión del trío REAL de
`deliberation_council`. Objeción de diversidad cognitiva del Cónclave que
revisó ADR-077 (2026-07-24): un solo LLM no debe ser la última palabra en
casos flagged -- incorporada aquí.
"""

from __future__ import annotations

from atlas.core.adversarial_panel import Severity
from atlas.core.decider.security_council_gate import CouncilVerdict, SecurityReport
from atlas.core.decider.security_council_escalation import resolve_council_verdict
from atlas.core.verify import Check, Evidence, Verdict


_CLEAN = CouncilVerdict(status="clean", report=None)
_FLAGGED = CouncilVerdict(
    status="flagged",
    report=SecurityReport(
        severity=Severity.MAJOR, checks_run=["scan", "llm_audit"],
        triggered_by="auditor LLM: riesgo detectado", recommended_action="revisar manual",
    ),
)


def test_clean_non_offensive_never_escalates() -> None:
    called = {"n": 0}

    def convene(descriptor: str) -> Evidence | None:
        called["n"] += 1
        return None

    result = resolve_council_verdict(kind="mcp_adopt", first_pass=_CLEAN, descriptor="x", convene_fn=convene)
    assert result is _CLEAN
    assert called["n"] == 0


def test_flagged_escalates_to_trio() -> None:
    called = {"n": 0}

    def convene(descriptor: str) -> Evidence | None:
        called["n"] += 1
        return Evidence(verdict=Verdict.FAIL, reason="confirmado")

    resolve_council_verdict(kind="mcp_adopt", first_pass=_FLAGGED, descriptor="x", convene_fn=convene)
    assert called["n"] == 1


def test_offensive_action_always_escalates_even_when_clean() -> None:
    called = {"n": 0}

    def convene(descriptor: str) -> Evidence | None:
        called["n"] += 1
        return Evidence(verdict=Verdict.PASS)

    resolve_council_verdict(kind="offensive_action", first_pass=_CLEAN, descriptor="x", convene_fn=convene)
    assert called["n"] == 1


def test_trio_pass_overrides_flagged_to_clean() -> None:
    def convene(descriptor: str) -> Evidence | None:
        return Evidence(verdict=Verdict.PASS)

    result = resolve_council_verdict(kind="mcp_adopt", first_pass=_FLAGGED, descriptor="x", convene_fn=convene)
    assert result.status == "clean"


def test_trio_fail_keeps_flagged_with_enriched_report() -> None:
    def convene(descriptor: str) -> Evidence | None:
        return Evidence(
            verdict=Verdict.FAIL,
            reason="objeción real",
            checks=(Check(name="gemini_free", passed=False, detail="riesgo confirmado"),),
        )

    result = resolve_council_verdict(kind="mcp_adopt", first_pass=_FLAGGED, descriptor="x", convene_fn=convene)
    assert result.status == "flagged"
    assert "trío" in result.report.triggered_by.lower()
    assert "objeción real" in result.report.triggered_by


def test_trio_unknown_does_not_clear_flagged_fail_closed() -> None:
    """UNKNOWN no es PASS -- unknown > mentir. No se trata como 'limpio'."""
    def convene(descriptor: str) -> Evidence | None:
        return Evidence(verdict=Verdict.UNKNOWN, reason="sin diversidad real de proveedores")

    result = resolve_council_verdict(kind="mcp_adopt", first_pass=_FLAGGED, descriptor="x", convene_fn=convene)
    assert result.status == "flagged"


def test_convene_declined_by_gating_keeps_first_pass() -> None:
    """should_convene() puede devolver False -> convene_for_decision devuelve
    None -- no hay segunda opinión disponible, la primera pasada es la final."""
    def convene(descriptor: str) -> Evidence | None:
        return None

    result = resolve_council_verdict(kind="mcp_adopt", first_pass=_FLAGGED, descriptor="x", convene_fn=convene)
    assert result is _FLAGGED


def test_offensive_action_flagged_first_pass_still_only_escalates_once() -> None:
    called = {"n": 0}

    def convene(descriptor: str) -> Evidence | None:
        called["n"] += 1
        return Evidence(verdict=Verdict.FAIL)

    resolve_council_verdict(kind="offensive_action", first_pass=_FLAGGED, descriptor="x", convene_fn=convene)
    assert called["n"] == 1
