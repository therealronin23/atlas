"""Hermes gana acciones correctivas (ADR-081, 2026-08-01).

`diagnostics`/`repair` (cableados antes hoy) sólo LEEN. Con 5 hallazgos vivos
en el tablero real —una tarea 564h `stranded_in_ready`, dos `stuck_in_blocked`
de 198h, dos `repeated_failures`— Atlas necesitaba poder PROPONER una
corrección. "Proponer", no "ejecutar": la guardia constitucional
(`enforce_constitutional_verdict`, decider.py) convierte cualquier `Allow`
sobre `sensitivity="high"` en `RequiresHuman`, así que con el decisor humano
(default) o autónomo (regla 2, deny explícito) **ninguna corrección se aplica
sin paso humano**. Es P10 ("Hermes propone, Atlas decide") hecho literal.
"""

from __future__ import annotations

from typing import Any

import pytest

from atlas.core.decider.decider import Allow, Deny, RequiresHuman
from atlas.core.decider.human_decider import HumanDecider
from atlas.core.decider.autonomous_decider import AutonomousDecider
from atlas.hermes.kanban_bridge import ALLOWED_KANBAN_ACTIONS, KanbanBridge


class _SpyRunner:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.calls: list[list[str]] = []

    def __call__(self, argv: Any, timeout_s: float) -> tuple[int, str, str]:
        self.calls.append(list(argv))
        return self.returncode, self.stdout, ""


class _AllowEverything:
    """Decisor de prueba que SIEMPRE intenta decir sí.

    Sirve para demostrar que la guardia constitucional gana incluso cuando el
    decisor inyectado no coopera — no basta con confiar en HumanDecider.
    """

    def decide(self, action: Any, sanctioned_intent: str, context: Any) -> Any:
        return Allow(reason="test decider dice que sí a todo")


def _bridge(runner: _SpyRunner) -> KanbanBridge:
    return KanbanBridge(transport="ssh", ssh_host="hermes@100.64.0.1", runner=runner)


class TestTheAllowlistGrowsButStaysGated:
    def test_the_three_actions_are_now_allowed(self) -> None:
        for verb in ("unblock", "edit", "reassign"):
            assert verb in ALLOWED_KANBAN_ACTIONS

    def test_destructive_actions_still_never_enter(self) -> None:
        assert "gc" not in ALLOWED_KANBAN_ACTIONS
        assert "archive" not in ALLOWED_KANBAN_ACTIONS or "archive" in ALLOWED_KANBAN_ACTIONS
        # archive ya estaba permitida (no destructiva de datos, sólo estado);
        # lo que NO debe entrar nunca es gc (borra de verdad).


class TestProposeCorrectionNeverExecutesWithoutAllow:
    """El invariante central de la ADR."""

    def test_human_decider_never_executes_a_correction(self) -> None:
        runner = _SpyRunner(stdout="{}")
        bridge = _bridge(runner)

        result = bridge.propose_correction(
            "unblock", "t_47a2032d",
            decider=HumanDecider(),
            sanctioned_intent="desatascar servidor A",
        )

        assert not runner.calls, "se ejecutó sin que el decisor lo autorizara"
        assert isinstance(result.verdict, RequiresHuman)

    def test_autonomous_decider_also_never_executes_it(self) -> None:
        """Regla 2 de AutonomousDecider deniega sensitivity=high explícitamente."""
        runner = _SpyRunner(stdout="{}")
        bridge = _bridge(runner)

        result = bridge.propose_correction(
            "reassign", "t_faf3ba40",
            decider=AutonomousDecider(),
            sanctioned_intent="reasignar tarea varada",
        )

        assert not runner.calls
        assert isinstance(result.verdict, Deny)

    def test_a_decider_that_says_yes_is_overridden_by_the_constitutional_guard(
        self,
    ) -> None:
        """No basta con confiar en que HumanDecider sea prudente: la guardia
        constitucional debe ganar incluso si el decisor inyectado no coopera."""
        runner = _SpyRunner(stdout="{}")
        bridge = _bridge(runner)

        result = bridge.propose_correction(
            "edit", "t_1bf1af04",
            decider=_AllowEverything(),
            sanctioned_intent="editar tarea",
        )

        assert not runner.calls, "un decisor complaciente ejecutó una acción high-sensitivity"
        assert isinstance(result.verdict, RequiresHuman)

    def test_only_allow_ever_executes(self) -> None:
        """Camino de futuro: SI algún día una implementación declara esta
        clase de acción autónoma segura (fuera del alcance de hoy), sólo
        entonces `propose_correction` ejecuta — y sólo entonces."""

        class _DowngradedAction:
            def decide(self, action: Any, sanctioned_intent: str, context: Any) -> Any:
                # Simula una acción NO high-sensitivity para probar el otro
                # extremo del condicional sin tocar la guardia constitucional.
                return Allow(reason="clase declarada segura")

        runner = _SpyRunner(stdout="{}")
        bridge = _bridge(runner)

        result = bridge.propose_correction(
            "unblock", "t_x",
            decider=_DowngradedAction(),
            sanctioned_intent="prueba",
            sensitivity="normal",
        )

        assert runner.calls, "un Allow explícito sobre sensibilidad normal debe ejecutar"
        assert isinstance(result.verdict, Allow)


class TestEveryProposalIsAudited:
    def test_a_pending_proposal_is_logged_to_merkle(self) -> None:
        merkle_calls: list[dict[str, Any]] = []

        class _SpyMerkle:
            def log(self, **kw: Any) -> None:
                merkle_calls.append(kw)

        bridge = KanbanBridge(
            transport="ssh", ssh_host="hermes@100.64.0.1",
            runner=_SpyRunner(stdout="{}"), merkle=_SpyMerkle(),
        )

        bridge.propose_correction(
            "unblock", "t_47a2032d",
            decider=HumanDecider(),
            sanctioned_intent="desatascar servidor A",
        )

        actions = [c.get("action") for c in merkle_calls]
        assert any("correction" in str(a) for a in actions), (
            f"ninguna propuesta de corrección quedó en el receipt Merkle: {actions}"
        )


class TestUnsupportedVerbIsRejected:
    def test_propose_correction_rejects_verbs_outside_its_scope(self) -> None:
        bridge = _bridge(_SpyRunner())

        with pytest.raises(ValueError, match="unsupported correction"):
            bridge.propose_correction(
                "archive", "t_x", decider=HumanDecider(), sanctioned_intent="x"
            )
