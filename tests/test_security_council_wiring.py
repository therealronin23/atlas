"""Tests del wiring real del Security Council Gate en
`Orchestrator._consult_decider` (ADR-077.4) -- la pieza que cierra el
hallazgo central de la auditoría: bajo `ATLAS_DECIDER=autonomous`,
`RequiresHuman` nunca se alcanzaba (0 desde mayo de 2026 en el log Merkle
real). Este gate produce `RequiresHuman` para un `flagged` confirmado ANTES
de que el decisor subyacente (Human o Autonomous) siquiera se consulte --
independiente del modo activo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.contracts import Task, TaskSource
from atlas.core.decider.decider import Allow, DecisionAction, Deny, RequiresHuman, action_hash
from atlas.core.decider.security_council_gate import AuditFinding, ScanFinding
from atlas.core.decider.security_council_registry import is_rejected
from atlas.core.orchestrator import Orchestrator
from atlas.core.verify import Evidence, Verdict


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "core"))
    monkeypatch.setenv("ATLAS_SECURITY_COUNCIL_GATE", "1")
    monkeypatch.delenv("ATLAS_DECIDER", raising=False)
    (tmp_path / "atlas").mkdir(parents=True)
    (tmp_path / "core").mkdir(parents=True)
    return Orchestrator(workspace=tmp_path / "atlas")


def _stub_gate(monkeypatch: pytest.MonkeyPatch, *, scan_clean: bool, audit_clean: bool) -> None:
    def scan(descriptor: str) -> ScanFinding:
        return ScanFinding(clean=scan_clean, detail="" if scan_clean else "escaneo marcó algo")

    def audit_factory(hub):  # noqa: ANN001
        def audit(descriptor: str) -> AuditFinding:
            return AuditFinding(clean=audit_clean, detail="" if audit_clean else "auditor marcó algo")
        return audit

    monkeypatch.setattr("atlas.core.decider.security_council_gate.default_scan_fn", scan)
    monkeypatch.setattr("atlas.core.decider.security_council_gate.build_llm_audit_fn", audit_factory)


def _stub_never_convenes(monkeypatch: pytest.MonkeyPatch, orch: Orchestrator) -> list[str]:
    calls: list[str] = []

    def fake_convene(descriptor: str, kind: str) -> Evidence | None:
        calls.append(kind)
        return None

    monkeypatch.setattr(orch, "_convene_second_opinion", fake_convene)
    return calls


def _mcp_adopt_action(descriptor: str = "ai.adeu/adeu") -> DecisionAction:
    return DecisionAction(
        kind="mcp_adopt", requires_approval=True, mutating=True,
        reversible=False, sensitivity="high", descriptor=descriptor,
        reason="adopción de server MCP",
    )


def _cold_update_action(descriptor: str = "click 8.4.1 8.4.2 8.4.2 https://pypi.org/pypi/click/json") -> DecisionAction:
    """Kind gateado que NO usa el scanner específico de mcp_adopt -- para
    probar el camino GENÉRICO (default_scan_fn) sin que el scanner real de
    vetting de mcp_adopt (que consulta un reporte en disco) interfiera."""
    return DecisionAction(
        kind="cold_update_apply", requires_approval=True, mutating=True,
        reversible=True, sensitivity="normal", descriptor=descriptor,
        reason="aplicar patch ColdUpdate",
    )


def _write_stage2_report(orch: Orchestrator, rows: list[dict]) -> Path:
    import json

    path = orch._project_root() / "docs" / "design" / "mcp_catalog_stage2_report.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return path


def test_gate_disabled_by_default_without_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin ATLAS_SECURITY_COUNCIL_GATE=1, ningún kind pasa por el gate --
    ni tests ni despliegues existentes cambian de comportamiento por
    accidente (mismo criterio que el resto de capacidades de esta sesión)."""
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "core"))
    monkeypatch.delenv("ATLAS_SECURITY_COUNCIL_GATE", raising=False)
    (tmp_path / "atlas").mkdir(parents=True)
    (tmp_path / "core").mkdir(parents=True)
    orch_no_flag = Orchestrator(workspace=tmp_path / "atlas")

    called = {"n": 0}
    monkeypatch.setattr(
        "atlas.core.decider.security_council_gate.default_scan_fn",
        lambda d: (called.__setitem__("n", called["n"] + 1), ScanFinding(clean=True))[1],
    )
    action = _mcp_adopt_action()
    task = Task(intent="adoptar ai.adeu/adeu", source=TaskSource.INTERNAL)
    orch_no_flag._consult_decider(action, task)
    assert called["n"] == 0


def test_non_gateable_kind_bypasses_gate_entirely(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = {"n": 0}

    def should_not_run(descriptor: str) -> ScanFinding:
        called["n"] += 1
        return ScanFinding(clean=True)

    monkeypatch.setattr("atlas.core.decider.security_council_gate.default_scan_fn", should_not_run)
    action = DecisionAction(kind="gate_f", mutating=True, descriptor="tool_x")
    task = Task(intent="tool_x", source=TaskSource.INTERNAL)
    orch._consult_decider(action, task)
    assert called["n"] == 0


def test_gateable_kind_already_rejected_short_circuits_deny(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    action = _mcp_adopt_action()
    task = Task(intent="adoptar ai.adeu/adeu", source=TaskSource.INTERNAL)
    act_hash = action_hash(action, task.intent)

    from atlas.core.decider.security_council_registry import record_rejection
    from atlas.core.decider.security_council_gate import SecurityReport
    from atlas.core.adversarial_panel import Severity

    registry_path = orch._project_root() / "workspace" / "security_council" / "rejected.jsonl"
    record_rejection(
        act_hash, "mcp_adopt", action.descriptor,
        SecurityReport(severity=Severity.MAJOR, triggered_by="x", recommended_action="y"),
        registry_path,
    )

    called = {"n": 0}
    monkeypatch.setattr(
        "atlas.core.decider.security_council_gate.default_scan_fn",
        lambda d: (called.__setitem__("n", called["n"] + 1), ScanFinding(clean=True))[1],
    )

    verdict, returned_hash = orch._consult_decider(action, task)
    assert isinstance(verdict, Deny)
    assert returned_hash == act_hash
    assert called["n"] == 0  # nunca re-corre el escaneo -- corte en corto real


def test_clean_gateable_kind_falls_through_to_normal_decider(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Camino GENÉRICO (default_scan_fn) -- usa cold_update_apply, no
    mcp_adopt, para no chocar con el scanner de vetting real de mcp_adopt
    (test_mcp_adopt_* más abajo cubre ese camino específico)."""
    _stub_gate(monkeypatch, scan_clean=True, audit_clean=True)
    _stub_never_convenes(monkeypatch, orch)

    action = _cold_update_action()
    task = Task(intent="bump click", source=TaskSource.INTERNAL)
    verdict, _ = orch._consult_decider(action, task)
    # clean -> pasa al decisor existente sin cambios.
    assert isinstance(verdict, RequiresHuman)


def test_flagged_gateable_kind_records_rejection_and_returns_requires_human(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_gate(monkeypatch, scan_clean=False, audit_clean=True)
    _stub_never_convenes(monkeypatch, orch)

    action = _cold_update_action()
    task = Task(intent="bump click", source=TaskSource.INTERNAL)
    act_hash = action_hash(action, task.intent)

    verdict, returned_hash = orch._consult_decider(action, task)
    assert isinstance(verdict, RequiresHuman)
    assert returned_hash == act_hash

    registry_path = orch._project_root() / "workspace" / "security_council" / "rejected.jsonl"
    assert is_rejected(act_hash, registry_path) is True


def test_mcp_adopt_uses_real_vetting_report_not_bare_descriptor(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Corrección del operador (2026-07-24): mcp_adopt NO debe usar el
    escaneo genérico (que solo ve el nombre del candidato) -- debe consultar
    la evidencia REAL de vetting stage2. Un candidato limpio en el reporte
    real (worst_severity=NONE) cae al decisor existente."""
    called_generic = {"n": 0}
    monkeypatch.setattr(
        "atlas.core.decider.security_council_gate.default_scan_fn",
        lambda d: (called_generic.__setitem__("n", called_generic["n"] + 1), ScanFinding(clean=True))[1],
    )
    monkeypatch.setattr(
        "atlas.core.decider.security_council_gate.build_llm_audit_fn",
        lambda hub: (lambda descriptor: AuditFinding(clean=True)),
    )
    _write_stage2_report(orch, [
        {"track": "stdio", "name": "good.package/mcp", "completed": True,
         "stage_reached": "static_scan", "worst_severity": "NONE"},
    ])
    _stub_never_convenes(monkeypatch, orch)

    action = _mcp_adopt_action("good.package/mcp")
    task = Task(intent="adoptar good.package/mcp", source=TaskSource.INTERNAL)
    verdict, _ = orch._consult_decider(action, task)

    assert called_generic["n"] == 0  # NUNCA usa el scanner genérico para mcp_adopt
    assert isinstance(verdict, RequiresHuman)  # clean -> cae al decisor normal


def test_mcp_adopt_major_finding_from_real_report_is_flagged_for_any_candidate(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El fix estructural: NO está anclado a 'ai.adeu/adeu' -- cualquier
    nombre de candidato con worst_severity real MAJOR/BLOCKING en el reporte
    queda cubierto, probado aquí con un nombre completamente distinto."""
    _write_stage2_report(orch, [
        {"track": "stdio", "name": "totalmente.distinto/nunca-visto-antes", "completed": True,
         "stage_reached": "static_scan", "worst_severity": "MAJOR"},
    ])
    _stub_never_convenes(monkeypatch, orch)

    action = _mcp_adopt_action("totalmente.distinto/nunca-visto-antes")
    task = Task(intent="adoptar totalmente.distinto/nunca-visto-antes", source=TaskSource.INTERNAL)
    act_hash = action_hash(action, task.intent)

    verdict, returned_hash = orch._consult_decider(action, task)
    assert isinstance(verdict, RequiresHuman)
    registry_path = orch._project_root() / "workspace" / "security_council" / "rejected.jsonl"
    assert is_rejected(act_hash, registry_path) is True


def test_mcp_adopt_without_any_stage2_report_fails_closed(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin reporte de vetting en absoluto -- fail-closed, nunca se asume
    limpio por falta de evidencia."""
    _stub_never_convenes(monkeypatch, orch)
    action = _mcp_adopt_action("nunca.vetado/candidato")
    task = Task(intent="adoptar nunca.vetado/candidato", source=TaskSource.INTERNAL)
    verdict, _ = orch._consult_decider(action, task)
    assert isinstance(verdict, RequiresHuman)


def test_offensive_action_always_escalates_even_when_clean(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_gate(monkeypatch, scan_clean=True, audit_clean=True)
    calls: list[str] = []

    def fake_convene(descriptor: str, kind: str) -> Evidence | None:
        calls.append(kind)
        return Evidence(verdict=Verdict.FAIL, reason="objeción real del trío")

    monkeypatch.setattr(orch, "_convene_second_opinion", fake_convene)

    action = DecisionAction(
        kind="offensive_action", requires_approval=True, mutating=True,
        reversible=True, sensitivity="moderate", descriptor="capability@target",
        reason="acción ofensiva contenida",
    )
    task = Task(intent="capability@target", source=TaskSource.INTERNAL)
    verdict, _ = orch._consult_decider(action, task)

    assert calls == ["offensive_action"]  # escaló pese a first-pass limpio
    assert isinstance(verdict, RequiresHuman)  # el trío objetó -> flagged final


def test_telegram_notified_on_major_flag(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_gate(monkeypatch, scan_clean=False, audit_clean=True)
    _stub_never_convenes(monkeypatch, orch)

    sent: list[str] = []

    class FakeBot:
        def notify_all(self, text: str) -> int:
            sent.append(text)
            return 1

    orch._telegram_bot = FakeBot()

    action = _cold_update_action()
    task = Task(intent="bump click", source=TaskSource.INTERNAL)
    orch._consult_decider(action, task)

    assert len(sent) == 1
    assert "cold_update_apply" in sent[0]


def test_no_crash_when_telegram_not_configured(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_gate(monkeypatch, scan_clean=False, audit_clean=True)
    _stub_never_convenes(monkeypatch, orch)
    assert orch._telegram_bot is None

    action = _cold_update_action()
    task = Task(intent="bump click", source=TaskSource.INTERNAL)
    verdict, _ = orch._consult_decider(action, task)  # no debe lanzar
    assert isinstance(verdict, RequiresHuman)
