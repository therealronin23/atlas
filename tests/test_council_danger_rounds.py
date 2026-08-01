"""Rondas por peligrosidad, no por conteo fijo (2026-08-01, pedido del operador).

"Si en la primera ronda consideran que supera un umbral X de peligrosidad se
concede otra ronda, y así sucesivamente hasta que se pongan de acuerdo o
cierren un plan lo suficientemente menos dañino, con tope 4 rondas -> HITL".

El umbral YA EXISTE: `AdversarialPanel.block_at` (Severity.MAJOR por defecto).
Y el veredicto ya lo traduce: `Evidence.verdict == FAIL` es EXACTAMENTE "algo
superó el umbral" (hay una objeción `reachable and severity >= block_at`).
No se inventa una escala nueva -- se reutiliza la que ya está.

Barato para lo seguro: si nada supera el umbral en la 1ª ronda, se para ahí.
Sólo lo peligroso paga las rondas extra -- alineado con "economiza tokens".
"""

from __future__ import annotations

from dataclasses import dataclass

from atlas.core.adversarial_panel import Objection, Severity
from atlas.core.deliberation_council import MAX_COUNCIL_ROUNDS, convene_for_decision
from atlas.router.cascade import Difficulty


@dataclass
class _ScriptedReviewer:
    """Devuelve una severidad DISTINTA cada vez que se le llama -- simula un
    panel cuya opinión evoluciona ronda a ronda (o no)."""

    reviewer_id: str
    provider: str
    severities: list[Severity]
    detail: str = "objeción"
    calls: int = 0

    def review(self, diff: str, context: str = "") -> Objection:
        sev = self.severities[min(self.calls, len(self.severities) - 1)]
        self.calls += 1
        return Objection(self.reviewer_id, self.provider, sev, f"{self.detail} (llamada {self.calls})")


def _reviewers(*severity_sequences: list[Severity]) -> list[_ScriptedReviewer]:
    return [
        _ScriptedReviewer(f"role{i}", f"provider{i}", seq)
        for i, seq in enumerate(severity_sequences)
    ]


class TestCheapWhenSafe:
    def test_a_safe_decision_stops_after_one_round(self) -> None:
        """Nada supera el umbral -> ni una ronda extra. Esto es el ahorro de
        tokens: lo trivial-seguro no paga 4 rondas por sistema."""
        reviewers = _reviewers(
            [Severity.NONE], [Severity.MINOR], [Severity.NONE],
            [Severity.MINOR], [Severity.NONE],
        )

        convene_for_decision(
            "cambiar un timeout de 30s a 60s", context="",
            difficulty=Difficulty.HARD, risk="low", reviewers=reviewers,
        )

        assert all(r.calls == 1 for r in reviewers), "se gastó una ronda de más sin peligro real"


class TestEscalatesOnDanger:
    def test_a_blocking_objection_earns_a_second_round(self) -> None:
        reviewers = _reviewers(
            [Severity.BLOCKING, Severity.NONE],  # peligroso, luego se retracta
            [Severity.NONE, Severity.NONE],
            [Severity.NONE, Severity.NONE],
        )

        convene_for_decision(
            "borrar la tabla de producción", context="",
            difficulty=Difficulty.HARD, risk="high", reviewers=reviewers,
        )

        assert all(r.calls == 2 for r in reviewers), "no se concedió la segunda ronda"

    def test_it_stops_as_soon_as_danger_drops_below_threshold(self) -> None:
        """3 rondas: peligroso, peligroso, YA SEGURO -- para ahí, no agota las 4."""
        reviewers = _reviewers(
            [Severity.BLOCKING, Severity.MAJOR, Severity.NONE],
            [Severity.NONE, Severity.NONE, Severity.NONE],
            [Severity.NONE, Severity.NONE, Severity.NONE],
        )

        convene_for_decision(
            "decisión que se mitiga progresivamente", context="",
            difficulty=Difficulty.HARD, risk="high", reviewers=reviewers,
        )

        assert all(r.calls == 3 for r in reviewers)

    def test_it_caps_at_max_rounds_and_escalates_to_human(self) -> None:
        """Peligroso SIEMPRE (nunca converge): tope duro, nunca bucle infinito."""
        reviewers = _reviewers(
            [Severity.BLOCKING] * 10,
            [Severity.NONE] * 10,
            [Severity.NONE] * 10,
        )

        evidence = convene_for_decision(
            "decisión que el panel nunca deja de bloquear", context="",
            difficulty=Difficulty.HARD, risk="high", reviewers=reviewers,
        )

        assert all(r.calls == MAX_COUNCIL_ROUNDS for r in reviewers)
        from atlas.core.verify import Verdict
        # Fail-closed: agotadas las rondas SIN bajar del umbral, el veredicto
        # sigue siendo FAIL -- "sin acuerdo no se actúa", nunca se relaja a
        # PASS sólo porque se acabó el presupuesto de rondas.
        assert evidence is not None
        assert evidence.verdict == Verdict.FAIL

    def test_max_rounds_is_four(self) -> None:
        """Decisión explícita del operador: tope 4, no ilimitado."""
        assert MAX_COUNCIL_ROUNDS == 4


class TestAnonymizedPeerReview:
    def test_round_two_context_does_not_name_any_seat_or_provider(self) -> None:
        """La ronda 2+ no debe filtrar QUIÉN dijo qué -- eso es lo que hace
        que la revisión entre pares sea honesta y no una defensa de la
        propia respuesta."""
        seen_contexts: list[str] = []

        @dataclass
        class _Spy:
            reviewer_id: str
            provider: str
            calls: int = 0

            def review(self, diff: str, context: str = "") -> Objection:
                seen_contexts.append(context)
                self.calls += 1
                sev = Severity.BLOCKING if self.calls == 1 else Severity.NONE
                return Objection(self.reviewer_id, self.provider, sev, "detalle real")

        reviewers = [_Spy("contrarian", "p0"), _Spy("first_principles", "p1"), _Spy("executor", "p2")]

        convene_for_decision(
            "decisión peligrosa", context="contexto original",
            difficulty=Difficulty.HARD, risk="high", reviewers=reviewers,
        )

        round_two_contexts = seen_contexts[3:]  # las primeras 3 son la ronda 1
        assert round_two_contexts, "no hubo segunda ronda"
        for ctx in round_two_contexts:
            assert "contrarian" not in ctx.lower()
            assert "first_principles" not in ctx.lower()
            assert "p0" not in ctx and "p1" not in ctx and "p2" not in ctx

    def test_round_two_context_asks_for_the_least_dangerous_variant(self) -> None:
        """La ronda 2 pide MITIGAR, no repetir el ataque -- es lo que
        convierte el bucle en 'cerrar un plan menos peligroso'."""
        seen_contexts: list[str] = []

        @dataclass
        class _Spy:
            reviewer_id: str
            provider: str
            calls: int = 0

            def review(self, diff: str, context: str = "") -> Objection:
                seen_contexts.append(context)
                self.calls += 1
                sev = Severity.MAJOR if self.calls == 1 else Severity.NONE
                return Objection(self.reviewer_id, self.provider, sev, "x")

        reviewers = [_Spy("a", "p0"), _Spy("b", "p1"), _Spy("c", "p2")]

        convene_for_decision(
            "decisión", context="",
            difficulty=Difficulty.HARD, risk="high", reviewers=reviewers,
        )

        round_two = seen_contexts[3]
        assert "menos peligros" in round_two.lower() or "mitigar" in round_two.lower()


class TestNeverHangsOnAFailingSeat:
    def test_a_reviewer_that_raises_mid_round_still_produces_a_verdict(self) -> None:
        """Con el panel PARALELIZADO (2026-08-01), un reviewer que lanza ya
        no tumba `panel.verify()` entero -- se atrapa POR ASIENTO dentro del
        propio panel (fail-closed, `reachable=False`) y el resto de la ronda
        se completa con normalidad. El `try/except` que antes envolvía cada
        ronda en `convene_for_decision` sigue ahí como red de seguridad para
        un fallo a nivel de PANEL (no de un solo asiento), pero ya no es la
        vía habitual por la que esto se resuelve."""

        class _FlakyAfterFirstCall:
            reviewer_id = "flaky"
            provider = "flaky-provider"

            def __init__(self) -> None:
                self.calls = 0

            def review(self, diff: str, context: str = "") -> Objection:
                self.calls += 1
                if self.calls == 1:
                    return Objection(self.reviewer_id, self.provider, Severity.BLOCKING, "x")
                raise RuntimeError("proveedor caído en la ronda 2")

        reviewers = [
            _FlakyAfterFirstCall(),
            _ScriptedReviewer("b", "p1", [Severity.NONE, Severity.NONE]),
            _ScriptedReviewer("c", "p2", [Severity.NONE, Severity.NONE]),
        ]

        evidence = convene_for_decision(
            "decisión", context="",
            difficulty=Difficulty.HARD, risk="high", reviewers=reviewers,
        )

        assert evidence is not None
        # El asiento flaky SÍ se intentó en la ronda 2 (el panel lo atrapó,
        # no convene_for_decision) y los otros dos completaron con él.
        assert reviewers[0].calls == 2  # type: ignore[attr-defined]
