"""Integración devil_advocate ↔ ruta dorada (Foundry Fase C, ADR-069, T1.2).

Punto de enganche: `GoldenRouteSession.soul_review()`, invocado ANTES de
`approve()` — exactamente el ejemplo de acceptance del backlog ("antes de
`approve()` en GoldenRoute"). La soul solo informa: nunca decide por el
humano (invariante D2 intacta). Este test demuestra el caso real que pide el
ítem: una misión de riesgo alto recibe una objeción de la soul, el veredicto
queda registrado de forma verificable en el log Merkle, y el humano —
informado por esa objeción— rechaza la misión.

Reusa el mismo fixture_repo + runner de subprocesos reales de
tests/acceptance/test_self_construction_golden_route.py (misma convención:
checks baratos pero de verdad, nunca mocks del motor)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from atlas.core.inference_hub import InferenceRequest, InferenceResponse
from atlas.core.validation_runner import ValidationReport
from atlas.missions.golden_route import GoldenRoute
from atlas.missions.souls.devil_advocate import DevilAdvocateVerdict


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture()
def fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "demo-repo"
    (repo / "docs" / "demo").mkdir(parents=True)
    (repo / "docs" / "demo" / "GOLDEN_ROUTE_DEMO.md").write_text(
        "# Golden Route Demo\n\nLínea base.\n", encoding="utf-8"
    )
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "test@atlas.local")
    _run_git(repo, "config", "user.name", "atlas-test")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "base")
    return repo


class _SubprocessRunner:
    def __init__(self, path: Path) -> None:
        self._path = path

    def run(self, timeout_s: int = 600) -> ValidationReport:
        code = subprocess.run(
            [sys.executable, "-c", "raise SystemExit(0)"], cwd=self._path
        ).returncode
        return ValidationReport(
            passed=code == 0, pytest_exit=code, mypy_exit=code,
            pytest_summary="fixture subprocess check",
            mypy_summary="fixture subprocess check",
        )


class _ScriptedHub:
    """Doble determinista de InferenceHub: sin llamar a ningún proveedor
    real (mismo patrón `_SubprocessRunner`/`_RunnerLike` ya usado en los
    tests de la ruta dorada)."""

    def __init__(self, verdict_json: dict[str, object]) -> None:
        self._text = json.dumps(verdict_json)
        self.calls = 0

    def infer_for_role(self, role: str, request: InferenceRequest) -> InferenceResponse:
        self.calls += 1
        return InferenceResponse(
            text=self._text, provider="fake", model="fake-model",
            level=request.level, latency_ms=1, success=True,
        )


def _route(fixture_repo: Path, tmp_path: Path) -> GoldenRoute:
    return GoldenRoute.for_repo(
        fixture_repo,
        store_dir=tmp_path / "updates",
        audit_dir=tmp_path / "audit",
        runner_factory=_SubprocessRunner,
    )


def test_soul_review_before_approve_exposes_verdict_on_session(
    fixture_repo: Path, tmp_path: Path
) -> None:
    route = _route(fixture_repo, tmp_path)
    session = route.request(
        "añade una línea al final de docs/demo/GOLDEN_ROUTE_DEMO.md", risk="high"
    )
    session.execute()

    hub = _ScriptedHub({
        "verdict": "objection",
        "reasoning": "Riesgo alto sin justificación adicional en el intent.",
        "confidence": 0.75,
    })
    verdict = session.soul_review(hub)

    assert isinstance(verdict, DevilAdvocateVerdict)
    assert verdict.objection is True
    assert hub.calls == 1
    # el veredicto queda expuesto en la sesión, no solo devuelto
    assert session.soul_verdict is verdict
    assert session.soul_verdict.objection is True


def test_soul_objection_is_registered_verifiably_in_merkle(
    fixture_repo: Path, tmp_path: Path
) -> None:
    """El requisito central del ítem: el veredicto queda en el receipt/Merkle
    de forma VERIFICABLE, no solo en memoria del objeto Python."""
    route = _route(fixture_repo, tmp_path)
    session = route.request(
        "añade una línea al final de docs/demo/GOLDEN_ROUTE_DEMO.md", risk="critical"
    )
    session.execute()

    hub = _ScriptedHub({
        "verdict": "objection",
        "reasoning": "Cambio de riesgo crítico revisado por devil_advocate.",
        "confidence": 0.9,
    })
    session.soul_review(hub)

    # cadena Merkle íntegra y verificable (no-repudio forense)
    ok, detail = route._merkle.verify_chain()  # noqa: SLF001 — inspección de test
    assert ok, detail

    records = route._merkle.read_all()  # noqa: SLF001 — inspección de test
    reviewed = [r for r in records if r.action == "golden_route.soul_reviewed"]
    assert len(reviewed) == 1
    payload = reviewed[0].payload
    assert payload["proposal_id"] == session.proposal_id
    assert payload["verdict"]["verdict"] == "objection"
    assert payload["verdict"]["soul_id"] == "soul_devil_advocate"


def test_mission_rejected_after_soul_objection_links_verdict_to_decision(
    fixture_repo: Path, tmp_path: Path
) -> None:
    """Caso real que pide el ítem: una misión rechazada tras la objeción de
    la soul, con el veredicto ligado a la decisión humana en el mismo
    registro Merkle — nunca la soul decidiendo por su cuenta (D2)."""
    route = _route(fixture_repo, tmp_path)
    session = route.request(
        'añade la línea "cambio arriesgado" al final de docs/demo/GOLDEN_ROUTE_DEMO.md',
        risk="critical",
    )
    session.execute()

    hub = _ScriptedHub({
        "verdict": "objection",
        "reasoning": "El intent no justifica un cambio de riesgo crítico.",
        "confidence": 0.85,
    })
    verdict = session.soul_review(hub)
    assert verdict.objection is True

    # el HUMANO decide, informado por la objeción — la soul no rechazó nada
    session.approve(actor="operator", decision="reject")
    assert session.state == "rejected"

    with pytest.raises(PermissionError):
        session.apply()
    assert (fixture_repo / "docs" / "demo" / "GOLDEN_ROUTE_DEMO.md").read_text(
        encoding="utf-8"
    ) == "# Golden Route Demo\n\nLínea base.\n"

    records = route._merkle.read_all()  # noqa: SLF001 — inspección de test
    decision = [r for r in records if r.action == "golden_route.decision.reject"]
    assert len(decision) == 1
    assert decision[0].payload["soul_verdict"]["verdict"] == "objection"
    assert decision[0].payload["decision"] == "reject"


def test_soul_no_objection_does_not_block_approval(
    fixture_repo: Path, tmp_path: Path
) -> None:
    route = _route(fixture_repo, tmp_path)
    session = route.request(
        "añade una línea al final de docs/demo/GOLDEN_ROUTE_DEMO.md", risk="low"
    )
    session.execute()

    hub = _ScriptedHub({
        "verdict": "no_objection",
        "reasoning": "Cambio acotado, riesgo bajo, validación pasó.",
        "confidence": 0.95,
    })
    verdict = session.soul_review(hub)
    assert verdict.objection is False

    session.approve(actor="operator", decision="approve")
    result = session.apply()
    assert result.receipt["verifiable"] is True
    assert session.state == "applied"


def test_soul_review_never_sends_tools_to_hub(
    fixture_repo: Path, tmp_path: Path
) -> None:
    """Contrato del manifiesto: tools_allowed=[] — la soul jamás puede mutar
    nada, ni siquiera a través de tool-calling."""
    route = _route(fixture_repo, tmp_path)
    session = route.request(
        "añade una línea al final de docs/demo/GOLDEN_ROUTE_DEMO.md", risk="high"
    )
    session.execute()

    captured: list[InferenceRequest] = []

    class _CapturingHub:
        def infer_for_role(self, role: str, request: InferenceRequest) -> InferenceResponse:
            captured.append(request)
            return InferenceResponse(
                text=json.dumps({"verdict": "no_objection", "reasoning": "ok", "confidence": 0.5}),
                provider="fake", model="fake", level=request.level,
                latency_ms=1, success=True,
            )

    session.soul_review(_CapturingHub())
    assert len(captured) == 1
    assert captured[0].tools is None
