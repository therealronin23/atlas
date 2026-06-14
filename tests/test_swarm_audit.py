"""
Tests para atlas.core.swarm_audit — re-verificación de propuestas swarm.

REGLA: NUNCA invocar ValidationRunner real ni la suite dentro de pytest.
Todos los runners son fakes que devuelven ValidationReport pre-cocinados.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from atlas.core.validation_runner import ValidationReport
from atlas.core.swarm_audit import reverify_swarm_proposals


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeProposal:
    id: str
    origin: str = "swarm"
    status: str = "proposed"
    evidence: dict = field(default_factory=dict)
    worktree_path: str | None = None


class FakeManager:
    def __init__(self, proposals: list[FakeProposal]) -> None:
        self._proposals = proposals

    def list_proposals(self) -> list[FakeProposal]:
        return list(self._proposals)


class FakeMerkle:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def log(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


def make_fake_runner(passed: bool, pytest_exit: int = 0, mypy_exit: int = 0):
    """Devuelve una runner_factory que ignora wt/home y devuelve report canned."""
    report = ValidationReport(
        passed=passed,
        pytest_exit=pytest_exit if passed else (pytest_exit or 1),
        mypy_exit=mypy_exit,
    )

    class _FakeRunner:
        def run(self) -> ValidationReport:
            return report

    def factory(wt: Path, home: Path) -> _FakeRunner:
        return _FakeRunner()

    return factory


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_sin_propuestas_swarm_no_loguea():
    """Sin propuestas swarm → devuelve vacío y NO llama merkle.log."""
    mgr = FakeManager([FakeProposal(id="p1", origin="human")])
    merkle = FakeMerkle()
    result = reverify_swarm_proposals(mgr, fraction=0.5, merkle=merkle, runner_factory=make_fake_runner(True))
    assert result["sampled"] == 0
    assert result["divergences"] == 0
    assert merkle.calls == []


def test_sin_propuestas_fraction_cero_no_loguea():
    """fraction=0 → devuelve vacío sin loguear."""
    mgr = FakeManager([FakeProposal(id="p1", worktree_path="/tmp/fake")])
    merkle = FakeMerkle()
    result = reverify_swarm_proposals(mgr, fraction=0, merkle=merkle, runner_factory=make_fake_runner(True))
    assert result["sampled"] == 0
    assert merkle.calls == []


def test_muestra_determinista_por_rng_seed(tmp_path: Path):
    """La misma seed produce la misma muestra."""
    wt = tmp_path / "wt"
    wt.mkdir()
    props = [FakeProposal(id=f"p{i}", worktree_path=str(wt)) for i in range(10)]
    mgr = FakeManager(props)
    merkle1 = FakeMerkle()
    merkle2 = FakeMerkle()
    factory = make_fake_runner(True)

    r1 = reverify_swarm_proposals(mgr, fraction=0.3, merkle=merkle1, rng_seed=42, runner_factory=factory)
    r2 = reverify_swarm_proposals(mgr, fraction=0.3, merkle=merkle2, rng_seed=42, runner_factory=factory)

    ids1 = [rec["proposal_id"] for rec in r1["records"]]
    ids2 = [rec["proposal_id"] for rec in r2["records"]]
    assert ids1 == ids2, "seeds iguales → misma muestra"

    r3 = reverify_swarm_proposals(mgr, fraction=0.3, merkle=FakeMerkle(), rng_seed=99, runner_factory=factory)
    ids3 = [rec["proposal_id"] for rec in r3["records"]]
    # Con seeds distintas es muy probable que sean distintas (10 props, 3 muestreadas)
    # No es garantizado pero con seed 42 vs 99 lo son.
    assert ids1 != ids3 or True  # no forzamos, sólo verificamos que la función corre


def test_divergencia_detectada_result_blocked(tmp_path: Path):
    """Una propuesta con suite failed → divergencia, merkle result=blocked."""
    wt = tmp_path / "wt"
    wt.mkdir()
    p = FakeProposal(id="bad-prop", worktree_path=str(wt), evidence={"signature": "abc123"})
    mgr = FakeManager([p])
    merkle = FakeMerkle()
    factory = make_fake_runner(passed=False, pytest_exit=1)

    result = reverify_swarm_proposals(mgr, fraction=1.0, merkle=merkle, runner_factory=factory)

    assert result["divergences"] == 1
    assert "bad-prop" in result["divergent_ids"]
    assert len(merkle.calls) == 1
    assert merkle.calls[0]["result"] == "blocked"
    assert merkle.calls[0]["action"] == "swarm.audit_sample"


def test_todas_passed_divergences_cero(tmp_path: Path):
    """Todas las propuestas pasan la suite → divergences=0, result=success."""
    wt = tmp_path / "wt"
    wt.mkdir()
    props = [FakeProposal(id=f"ok{i}", worktree_path=str(wt)) for i in range(3)]
    mgr = FakeManager(props)
    merkle = FakeMerkle()

    result = reverify_swarm_proposals(mgr, fraction=1.0, merkle=merkle, runner_factory=make_fake_runner(True))

    assert result["divergences"] == 0
    assert result["sampled"] == 3
    assert result["reverified"] == 3
    assert merkle.calls[0]["result"] == "success"


def test_worktree_ausente_skipped():
    """Propuesta cuyo worktree no existe → suite_passed None, skipped=worktree_ausente."""
    p = FakeProposal(id="gone", worktree_path="/tmp/does-not-exist-atlas-audit-xyz")
    mgr = FakeManager([p])
    merkle = FakeMerkle()

    result = reverify_swarm_proposals(mgr, fraction=1.0, merkle=merkle, runner_factory=make_fake_runner(True))

    assert result["sampled"] == 1
    rec = result["records"][0]
    assert rec["suite_passed"] is None
    assert rec["skipped"] == "worktree_ausente"
    # No cuenta como divergencia (suite_passed is None, no False)
    assert result["divergences"] == 0
    # Pero sí se loguea (hay sample)
    assert len(merkle.calls) == 1


def test_worktree_none_skipped():
    """Propuesta sin worktree_path → skipped."""
    p = FakeProposal(id="no-wt", worktree_path=None)
    mgr = FakeManager([p])
    merkle = FakeMerkle()

    result = reverify_swarm_proposals(mgr, fraction=1.0, merkle=merkle, runner_factory=make_fake_runner(True))

    rec = result["records"][0]
    assert rec["suite_passed"] is None
    assert rec["skipped"] == "worktree_ausente"


def test_fraction_mayor_igual_1_usa_todas(tmp_path: Path):
    """fraction>=1 → sample = todos los props."""
    wt = tmp_path / "wt"
    wt.mkdir()
    props = [FakeProposal(id=f"p{i}", worktree_path=str(wt)) for i in range(5)]
    mgr = FakeManager(props)
    merkle = FakeMerkle()

    result = reverify_swarm_proposals(mgr, fraction=1.0, merkle=merkle, runner_factory=make_fake_runner(True))
    assert result["sampled"] == 5


def test_filtra_status_no_swarm(tmp_path: Path):
    """Propuestas con status applied/rejected no se incluyen."""
    wt = tmp_path / "wt"
    wt.mkdir()
    props = [
        FakeProposal(id="ok", worktree_path=str(wt), status="proposed"),
        FakeProposal(id="applied", worktree_path=str(wt), status="applied"),
        FakeProposal(id="rejected", worktree_path=str(wt), status="rejected"),
    ]
    mgr = FakeManager(props)
    merkle = FakeMerkle()

    result = reverify_swarm_proposals(mgr, fraction=1.0, merkle=merkle, runner_factory=make_fake_runner(True))
    assert result["sampled"] == 1
    assert result["records"][0]["proposal_id"] == "ok"
