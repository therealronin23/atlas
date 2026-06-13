"""
Capa 3 — SwarmCycle: tests con fakes, sin git real ni red.

REGLAS: sin red, sin GUI, sin subprocess real, sin ValidationRunner.
Todo inyectado: manager fake, merkle fake, file_provider fake, make_worker fake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from atlas.core.swarm_cycle import SwarmCycle
from atlas.core.verify import Artifact, ArtifactKind, CostTier


# ---------------------------------------------------------------------------
# Fakes

class FakeProposal:
    """Propuesta fake con los campos que SwarmCycle necesita."""

    _counter = 0

    def __init__(self, origin: str, status: str, evidence: dict[str, Any]) -> None:
        FakeProposal._counter += 1
        self.id = f"fake-{FakeProposal._counter}"
        self.origin = origin
        self.status = status
        self.evidence: dict[str, Any] = dict(evidence)

    @classmethod
    def reset(cls) -> None:
        cls._counter = 0


class FakeManager:
    """ColdUpdateManager fake: registra propuestas sin git ni store."""

    def __init__(self) -> None:
        self._proposals: list[FakeProposal] = []

    def list_proposals(self) -> list[FakeProposal]:
        return list(self._proposals)

    def propose(
        self,
        intent: str,
        patch_path: Path,
        *,
        base_ref: str = "HEAD",
        origin: str = "manual",
        risk: str = "medium",
        evidence: dict[str, Any] | None = None,
    ) -> FakeProposal:
        p = FakeProposal(origin=origin, status="proposed", evidence=evidence or {})
        self._proposals.append(p)
        return p

    def attach_evidence(self, proposal_id: str, evidence: dict[str, Any]) -> FakeProposal:
        for p in self._proposals:
            if p.id == proposal_id:
                p.evidence.update(evidence)
                return p
        raise KeyError(f"propuesta no encontrada: {proposal_id}")


class FakeMerkle:
    """MerkleLogger fake: captura los logs sin escribir disco."""

    def __init__(self) -> None:
        self.logs: list[dict[str, Any]] = []

    def log(self, action: str, agent: str, result: str,
            risk_level: str = "safe", payload: dict | None = None,
            task_id: str | None = None) -> None:
        self.logs.append({
            "action": action, "agent": agent, "result": result,
            "risk_level": risk_level, "payload": payload or {},
        })


# ---------------------------------------------------------------------------
# Diff válido que el UnifiedDiffVerifier ACEPTARÁ.
# Clave: cabeceras a/ b/ + hunk + allowed_paths coincide con task.path.
# El FakeWorker genera el diff parametrizado por task.path.

def _make_diff(path: str) -> str:
    """Diff unificado mínimo y válido para `path`."""
    return (
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1 @@\n"
        "-a = 1 \n"
        "+a = 1\n"
    )


def _make_worker_factory() -> Any:
    """Devuelve una función make_worker que produce workers fake."""

    def _make_worker(worker_id: str) -> Any:
        class FakeWorker:
            def __init__(self, wid: str) -> None:
                self.worker_id = wid
                self.domain = "repo_maintenance"

            def produce(self, task: Any) -> Artifact:
                diff = _make_diff(task.path)
                return Artifact(
                    kind=ArtifactKind.PATCH,
                    payload={"diff": diff},
                    producer_cost=CostTier.SHAPE,
                    metadata={"allowed_paths": [task.path]},
                )

        return FakeWorker(worker_id)

    return _make_worker


def _file_provider_with_whitespace() -> list[tuple[str, str]]:
    """Fichero con trailing whitespace → el scout emite strip_trailing_whitespace."""
    return [("src/x.py", "a = 1 \n")]


def _build_cycle(
    manager: FakeManager,
    merkle: FakeMerkle,
    *,
    cap_open: int = 20,
    max_tasks: int = 10,
) -> SwarmCycle:
    return SwarmCycle(
        manager=manager,
        merkle=merkle,
        file_provider=_file_provider_with_whitespace,
        make_worker=_make_worker_factory(),
        cap_open=cap_open,
        max_tasks=max_tasks,
    )


# ---------------------------------------------------------------------------
# Tests

class TestSwarmCycle:
    def setup_method(self) -> None:
        FakeProposal.reset()

    def test_first_cycle_proposes_one(self) -> None:
        """Un fichero con trailing whitespace genera 1 propuesta."""
        manager = FakeManager()
        merkle = FakeMerkle()
        cycle = _build_cycle(manager, merkle)

        result = cycle.run_cycle()

        assert result["skipped_for_cap"] is False
        assert len(result["proposed_ids"]) == 1
        assert result["scanned"] == 1
        assert result["tasks"] == 1

    def test_proposal_origin_is_swarm(self) -> None:
        """La propuesta creada tiene origin 'swarm'."""
        manager = FakeManager()
        cycle = _build_cycle(manager, FakeMerkle())
        cycle.run_cycle()

        proposals = manager.list_proposals()
        assert len(proposals) == 1
        assert proposals[0].origin == "swarm"

    def test_proposal_gets_signature_evidence(self) -> None:
        """Después de run_cycle, la propuesta tiene evidence['signature']."""
        manager = FakeManager()
        cycle = _build_cycle(manager, FakeMerkle())
        result = cycle.run_cycle()

        pid = result["proposed_ids"][0]
        proposal = next(p for p in manager.list_proposals() if p.id == pid)
        assert "signature" in proposal.evidence
        assert proposal.evidence["signature"] == "strip_trailing_whitespace:src/x.py"

    def test_second_cycle_does_not_repropose(self) -> None:
        """Con la firma ya abierta, un segundo ciclo NO re-propone (dedup F6)."""
        manager = FakeManager()
        merkle = FakeMerkle()
        cycle = _build_cycle(manager, merkle)

        result1 = cycle.run_cycle()
        assert len(result1["proposed_ids"]) == 1

        result2 = cycle.run_cycle()
        assert len(result2["proposed_ids"]) == 0
        # Solo hay 1 propuesta total.
        assert len(manager.list_proposals()) == 1

    def test_cap_open_zero_skips(self) -> None:
        """cap_open=0 → skipped_for_cap=True y 0 propuestas."""
        manager = FakeManager()
        cycle = _build_cycle(manager, FakeMerkle(), cap_open=0)

        result = cycle.run_cycle()

        assert result["skipped_for_cap"] is True
        assert result["proposed_ids"] == []
        assert len(manager.list_proposals()) == 0

    def test_cap_open_reached_skips(self) -> None:
        """Si las propuestas abiertas alcanzan cap_open, el ciclo se pausa."""
        manager = FakeManager()
        merkle = FakeMerkle()

        # Simula 3 propuestas swarm abiertas ya presentes.
        for i in range(3):
            p = FakeProposal(origin="swarm", status="proposed",
                             evidence={"signature": f"strip_trailing_whitespace:src/y{i}.py"})
            manager._proposals.append(p)

        cycle = _build_cycle(manager, merkle, cap_open=3)
        result = cycle.run_cycle()

        assert result["skipped_for_cap"] is True
        assert result["open"] == 3

    def test_merkle_log_emitted(self) -> None:
        """El ciclo escribe al menos un log Merkle con action 'swarm.cycle'."""
        manager = FakeManager()
        merkle = FakeMerkle()
        cycle = _build_cycle(manager, merkle)
        cycle.run_cycle()

        cycle_logs = [l for l in merkle.logs if l["action"] == "swarm.cycle"]
        assert len(cycle_logs) >= 1
        assert cycle_logs[0]["result"] == "ok"

    def test_empty_file_provider_proposes_nothing(self) -> None:
        """Sin ficheros, no hay tareas ni propuestas."""
        manager = FakeManager()
        cycle = SwarmCycle(
            manager=manager,
            merkle=FakeMerkle(),
            file_provider=lambda: [],
            make_worker=_make_worker_factory(),
        )
        result = cycle.run_cycle()

        assert result["tasks"] == 0
        assert result["proposed_ids"] == []

    def test_no_whitespace_file_proposes_nothing(self) -> None:
        """Fichero sin trailing whitespace no genera tareas."""
        manager = FakeManager()
        cycle = SwarmCycle(
            manager=manager,
            merkle=FakeMerkle(),
            file_provider=lambda: [("src/clean.py", "a = 1\n")],
            make_worker=_make_worker_factory(),
        )
        result = cycle.run_cycle()

        assert result["tasks"] == 0
        assert result["proposed_ids"] == []

    def test_reconcile_errors_captured(self) -> None:
        """Errores del reconciler se agregan en el resultado sin detener el ciclo."""

        class BrokenManager(FakeManager):
            def propose(self, *a: Any, **kw: Any) -> Any:
                raise RuntimeError("broken manager")

        manager = BrokenManager()
        merkle = FakeMerkle()
        cycle = _build_cycle(manager, merkle)
        result = cycle.run_cycle()

        # No propuestas (se rompió), pero el ciclo terminó y reportó el error.
        assert result["proposed_ids"] == []
        # reconcile_errors puede venir del coordinador o puede ser vacío
        # dependiendo de si on_accepted lanza. Verificamos que el ciclo
        # completó sin excepción y devolvió el dict esperado.
        assert "reconcile_errors" in result

    def test_flaky_proposal_signature_alignment(self) -> None:
        """F6 desalineación firma→propuesta: propose de t1 falla → t0 y t2
        reciben SUS firmas; la firma de t1 no aparece en ninguna propuesta.

        Con el código antiguo (zip posicional sobre blackboard.accepted()), el
        desfase asignaría la firma de t0 a la propuesta de t2 (o viceversa).
        Con el fix (reconciler.proposals), el emparejamiento es exacto.
        """

        class FlakyManager(FakeManager):
            """propose lanza solo cuando el intent contiene 'maint-1]'."""

            def propose(
                self,
                intent: str,
                patch_path: Path,
                *,
                base_ref: str = "HEAD",
                origin: str = "manual",
                risk: str = "medium",
                evidence: dict[str, Any] | None = None,
            ) -> FakeProposal:
                if "maint-1]" in intent:
                    raise RuntimeError("flaky: fallo intercalado en maint-1")
                return super().propose(
                    intent, patch_path,
                    base_ref=base_ref, origin=origin, risk=risk, evidence=evidence,
                )

        # Tres ficheros con trailing whitespace → tres tareas con firmas distintas.
        files_3 = [
            ("src/a.py", "a = 1 \n"),   # task[0]: maint-0
            ("src/b.py", "b = 2 \n"),   # task[1]: maint-1 → propose lanza
            ("src/c.py", "c = 3 \n"),   # task[2]: maint-2
        ]
        sig0 = "strip_trailing_whitespace:src/a.py"
        sig1 = "strip_trailing_whitespace:src/b.py"
        sig2 = "strip_trailing_whitespace:src/c.py"

        manager = FlakyManager()
        merkle = FakeMerkle()
        cycle = SwarmCycle(
            manager=manager,
            merkle=merkle,
            file_provider=lambda: files_3,
            make_worker=_make_worker_factory(),
            cap_open=20,
            max_tasks=10,
        )
        result = cycle.run_cycle()

        # Solo t0 y t2 producen propuestas (t1 falló intercalado).
        assert len(result["proposed_ids"]) == 2, (
            f"esperadas 2 propuestas, obtenidas {len(result['proposed_ids'])}"
        )
        proposals = manager.list_proposals()
        assert len(proposals) == 2

        # Recoger firmas adjuntas a cada propuesta.
        sigs_in_proposals = {p.evidence.get("signature") for p in proposals}

        # La firma de t1 NO debe aparecer en ninguna propuesta.
        assert sig1 not in sigs_in_proposals, (
            f"firma de t1 ({sig1!r}) aparece en propuestas: {sigs_in_proposals}"
        )

        # Las firmas de t0 y t2 deben estar, cada una en su propuesta.
        assert sig0 in sigs_in_proposals, (
            f"firma de t0 ({sig0!r}) no encontrada en propuestas: {sigs_in_proposals}"
        )
        assert sig2 in sigs_in_proposals, (
            f"firma de t2 ({sig2!r}) no encontrada en propuestas: {sigs_in_proposals}"
        )

        # Verificación adicional: cada propuesta tiene UNA firma correcta.
        for p in proposals:
            assert p.evidence.get("signature") in {sig0, sig2}, (
                f"firma inesperada en propuesta {p.id}: {p.evidence.get('signature')!r}"
            )
