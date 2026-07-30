"""
ADR-047 — Panel adversarial. Revisores fake (sin LLM real): se fija la
diversidad obligatoria, el gating y la agregación de objeciones.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from atlas.core.adversarial_panel import (
    AdversarialPanel,
    IrreversibleActionVerifier,
    Objection,
    Severity,
    should_convene,
)
from atlas.router.cascade import Difficulty
from atlas.core.verify import Artifact, ArtifactKind, CostTier, Verdict


@dataclass
class FakeReviewer:
    reviewer_id: str
    provider: str
    severity: Severity = Severity.NONE
    detail: str = ""
    reachable: bool = True

    def review(self, diff: str, context: str = "") -> Objection:
        return Objection(self.reviewer_id, self.provider, self.severity, self.detail, self.reachable)


def _panel(*reviewers, **kw) -> AdversarialPanel:
    return AdversarialPanel(list(reviewers), **kw)


class TestGating:
    @pytest.mark.parametrize(
        "difficulty,risk,irreversible,expected",
        [
            (Difficulty.MECHANICAL, "low", False, False),   # typo trivial → salta
            (Difficulty.MECHANICAL, "low", True, True),     # irreversible → convoca
            (Difficulty.MECHANICAL, "high", False, True),   # alto riesgo → convoca
            (Difficulty.HARD, "low", False, True),          # difícil → convoca
            (Difficulty.STANDARD, "medium", False, False),  # del montón → salta
            (Difficulty.STANDARD, "critical", False, True),
        ],
    )
    def test_should_convene(self, difficulty, risk, irreversible, expected) -> None:
        assert should_convene(difficulty, risk, irreversible=irreversible) is expected


class TestDiversity:
    def test_same_provider_is_unknown_not_certifiable(self) -> None:
        panel = _panel(
            FakeReviewer("a", "groq"),
            FakeReviewer("b", "groq"),  # mismo proveedor
            FakeReviewer("c", "groq"),
        )
        ev = panel.verify("diff")
        assert ev.verdict is Verdict.UNKNOWN
        assert "diversidad" in ev.reason

    def test_distinct_providers_can_certify(self) -> None:
        panel = _panel(FakeReviewer("a", "groq"), FakeReviewer("b", "gemini"))
        assert panel.verify("diff").verdict is Verdict.PASS

    def test_min_providers_configurable(self) -> None:
        panel = _panel(FakeReviewer("a", "groq"), min_providers=1)
        assert panel.verify("diff").verdict is Verdict.PASS


class TestUnreachableReviewers:
    """2026-07-30: hallazgo de un Cónclave real -- nvidia_glm entró muerto
    (provider_smoke ya lo sabía), respondió fail-closed, y el panel lo contó
    como voz viva de un trío de 3 Y como objeción sustantiva bloqueante. Un
    reviewer inalcanzable no es una opinión: no debe contar para diversidad
    ni para bloquear."""

    def test_unreachable_reviewer_does_not_count_toward_diversity(self) -> None:
        panel = _panel(
            FakeReviewer("a", "gemini", Severity.NONE),
            FakeReviewer("b", "nvidia_glm", Severity.MAJOR, "revisión no disponible (fail-closed)", reachable=False),
            FakeReviewer("c", "mistral", Severity.MAJOR, "objeción real"),
        )
        ev = panel.verify("diff")
        # Solo 2 proveedores ALCANZABLES distintos (gemini, mistral) de 3
        # configurados -- por debajo del mínimo de 3 exigido por defecto? No:
        # min_providers por defecto es 2, así que con 2 alcanzables SÍ certifica,
        # pero la objeción bloqueante real de "mistral" debe seguir bloqueando.
        assert ev.verdict is Verdict.FAIL
        assert "objeción real" in ev.reason
        # La voz muerta NO aparece como si fuera una objeción sustantiva propia.
        assert "fail-closed" not in ev.reason

    def test_unreachable_reviewer_never_counts_as_blocking_objection(self) -> None:
        """Caso puro: SOLO el reviewer muerto tendría severidad MAJOR. Si
        contara, el panel diría FAIL sin que nadie haya objetado nada real."""
        panel = _panel(
            FakeReviewer("a", "gemini", Severity.NONE),
            FakeReviewer("b", "mistral", Severity.NONE),
            FakeReviewer("c", "nvidia_glm", Severity.MAJOR, "revisión no disponible (fail-closed)", reachable=False),
        )
        ev = panel.verify("diff")
        assert ev.verdict is Verdict.PASS

    def test_falls_below_min_providers_after_unreachable_is_excluded(self) -> None:
        """3 configurados, diversidad de CONSTRUCCIÓN pasa (3 proveedores
        distintos), pero solo 2 respondieron de verdad -- con min_providers=3
        el veredicto debe caer a UNKNOWN, no colarse como PASS/FAIL con un
        panel de 2 voces reales disfrazado de panel de 3."""
        panel = _panel(
            FakeReviewer("a", "gemini", Severity.NONE),
            FakeReviewer("b", "mistral", Severity.NONE),
            FakeReviewer("c", "nvidia_glm", Severity.MAJOR, "revisión no disponible (fail-closed)", reachable=False),
            min_providers=3,
        )
        ev = panel.verify("diff")
        assert ev.verdict is Verdict.UNKNOWN
        assert "diversidad" in ev.reason or "alcanzable" in ev.reason.lower()

    def test_unreachable_reviewer_still_recorded_in_checks(self) -> None:
        """Transparencia: la voz muerta debe seguir apareciendo en checks
        (para que se pueda auditar QUIÉN no respondió), solo que no cuenta
        como objeción sustantiva ni como voz de diversidad."""
        panel = _panel(
            FakeReviewer("a", "gemini", Severity.NONE),
            FakeReviewer("b", "mistral", Severity.NONE),
            FakeReviewer("c", "nvidia_glm", Severity.MAJOR, "revisión no disponible (fail-closed)", reachable=False),
        )
        ev = panel.verify("diff")
        names = {chk.name for chk in ev.checks}
        assert "c@nvidia_glm" in names

    def test_objection_reachable_defaults_to_true(self) -> None:
        """Compatibilidad hacia atrás: construir Objection posicionalmente
        con 4 argumentos (como hace todo el código existente) no debe romper."""
        obj = Objection("id", "prov", Severity.NONE, "detalle")
        assert obj.reachable is True


class TestAggregation:
    def test_no_objections_passes(self) -> None:
        panel = _panel(
            FakeReviewer("a", "groq", Severity.NONE),
            FakeReviewer("b", "gemini", Severity.MINOR, "matiz menor"),
        )
        ev = panel.verify("diff")
        assert ev.verdict is Verdict.PASS  # MINOR no bloquea
        assert len(ev.checks) == 2

    def test_major_objection_fails(self) -> None:
        panel = _panel(
            FakeReviewer("a", "groq", Severity.NONE),
            FakeReviewer("b", "gemini", Severity.MAJOR, "rompe el caso vacío"),
        )
        ev = panel.verify("diff")
        assert ev.verdict is Verdict.FAIL
        assert "rompe el caso vacío" in ev.reason
        assert "b:" in ev.reason

    def test_blocking_objection_fails(self) -> None:
        panel = _panel(
            FakeReviewer("a", "groq", Severity.BLOCKING, "introduce eval()"),
            FakeReviewer("b", "gemini", Severity.NONE),
        )
        assert panel.verify("diff").verdict is Verdict.FAIL

    def test_block_threshold_configurable(self) -> None:
        # Con block_at=BLOCKING, una MAJOR ya no bloquea.
        panel = _panel(
            FakeReviewer("a", "groq", Severity.MAJOR, "discutible"),
            FakeReviewer("b", "gemini", Severity.NONE),
            block_at=Severity.BLOCKING,
        )
        assert panel.verify("diff").verdict is Verdict.PASS

    def test_checks_record_each_reviewer(self) -> None:
        panel = _panel(
            FakeReviewer("rev1", "groq", Severity.NONE),
            FakeReviewer("rev2", "gemini", Severity.MAJOR, "x"),
        )
        ev = panel.verify("diff")
        names = {c.name for c in ev.checks}
        assert names == {"rev1@groq", "rev2@gemini"}
        passed = {c.name: c.passed for c in ev.checks}
        assert passed["rev1@groq"] is True
        assert passed["rev2@gemini"] is False

    def test_evidence_serializable(self) -> None:
        import json

        panel = _panel(FakeReviewer("a", "groq"), FakeReviewer("b", "gemini"))
        json.dumps(panel.verify("diff").to_dict())


class TestReviewerReceivesArtifact:
    def test_diff_and_context_passed(self) -> None:
        seen = {}

        @dataclass
        class Capturing:
            reviewer_id: str = "cap"
            provider: str = "groq"

            def review(self, diff: str, context: str = "") -> Objection:
                seen["diff"] = diff
                seen["context"] = context
                return Objection(self.reviewer_id, self.provider, Severity.NONE)

        _panel(Capturing(), FakeReviewer("b", "gemini")).verify("el diff", "el contexto")
        assert seen == {"diff": "el diff", "context": "el contexto"}


def _irreversible_artifact(action: str = "enviar email al cliente") -> Artifact:
    return Artifact(
        kind=ArtifactKind.IRREVERSIBLE_ACTION,
        payload={"action": action, "context": "contexto de la tarea"},
        producer_cost=CostTier.FRONTIER,
    )


class TestIrreversibleActionVerifier:
    """t1-irreversible-action-verifier (ADR-047): el verificador ES el
    AdversarialPanel con disenso obligatorio — consenso procede con
    evidencia adjunta, sin consenso escala al humano y NUNCA auto-aprueba."""

    def test_applies_only_to_irreversible_action(self) -> None:
        verifier = IrreversibleActionVerifier(_panel(FakeReviewer("a", "groq")))
        assert verifier.applies_to(_irreversible_artifact()) is True
        code_artifact = Artifact(
            kind=ArtifactKind.CODE, payload={"code": "x=1"}, producer_cost=CostTier.FRONTIER
        )
        assert verifier.applies_to(code_artifact) is False

    def test_blocked_by_dissent_when_reviewer_objects(self) -> None:
        # Acción irreversible sintética: un reviewer levanta una objeción
        # sustantiva (MAJOR) -> el panel no logra consenso -> FAIL, nunca PASS.
        panel = _panel(
            FakeReviewer("a", "groq", Severity.NONE),
            FakeReviewer(
                "b", "gemini", Severity.MAJOR,
                "el plan asume que el destinatario todavía trabaja ahí; si no, se filtra info sensible",
            ),
        )
        verifier = IrreversibleActionVerifier(panel)
        evidence = verifier.verify(_irreversible_artifact())

        assert evidence.verdict is Verdict.FAIL
        assert "se filtra info sensible" in evidence.reason
        assert "escala al humano" in evidence.reason
        assert "irreversible_action_panel" in evidence.verifier_ids

    def test_passes_with_dissent_evidence_attached_on_consensus(self) -> None:
        # Consenso: ningún reviewer objeta sustantivamente -> PASS, pero con
        # la evidencia de disenso (los checks de cada reviewer) adjunta.
        panel = _panel(
            FakeReviewer("a", "groq", Severity.NONE, "sin objeciones tras revisar el peor caso"),
            FakeReviewer("b", "gemini", Severity.MINOR, "matiz menor, no bloquea"),
        )
        verifier = IrreversibleActionVerifier(panel)
        evidence = verifier.verify(_irreversible_artifact())

        assert evidence.verdict is Verdict.PASS
        assert len(evidence.checks) == 2  # evidencia de disenso de cada reviewer, adjunta
        assert "irreversible_action_panel" in evidence.verifier_ids

    def test_never_auto_approves_without_diversity(self) -> None:
        # Sin diversidad de proveedores el panel no puede certificar (UNKNOWN).
        # Debe escalar al humano, NUNCA convertirse en PASS silencioso.
        panel = _panel(
            FakeReviewer("a", "groq"),
            FakeReviewer("b", "groq"),  # mismo proveedor -> sin diversidad
        )
        verifier = IrreversibleActionVerifier(panel)
        evidence = verifier.verify(_irreversible_artifact())

        assert evidence.verdict is Verdict.UNKNOWN
        assert evidence.verdict is not Verdict.PASS
        assert "escala al humano" in evidence.reason

    def test_dissent_questions_reach_the_reviewer_context(self) -> None:
        seen = {}

        @dataclass
        class Capturing:
            reviewer_id: str = "cap"
            provider: str = "groq"

            def review(self, diff: str, context: str = "") -> Objection:
                seen["context"] = context
                return Objection(self.reviewer_id, self.provider, Severity.NONE)

        panel = _panel(Capturing(), FakeReviewer("b", "gemini"))
        IrreversibleActionVerifier(panel).verify(_irreversible_artifact())

        assert "¿Por qué esto es un error?" in seen["context"]
        assert "¿Qué asume el plan que podría ser falso?" in seen["context"]
        assert "¿Qué se rompe en el peor caso?" in seen["context"]
        assert "contexto de la tarea" in seen["context"]  # no descarta el contexto original

    def test_wired_into_universal_verifier_seam(self) -> None:
        # Integración real con el seam de capa 1: registrar el verificador y
        # que UniversalVerifier lo aplique de punta a punta sin relajar la
        # regla asimétrica (cost MODEL < producer_cost FRONTIER).
        from atlas.core.verify import UniversalVerifier

        panel = _panel(
            FakeReviewer("a", "groq", Severity.BLOCKING, "introduce un compromiso irreversible sin confirmar"),
            FakeReviewer("b", "gemini", Severity.NONE),
        )
        uv = UniversalVerifier([IrreversibleActionVerifier(panel)])
        evidence = uv.verify(_irreversible_artifact())

        assert evidence.verdict is Verdict.FAIL
