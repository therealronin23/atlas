"""El panel recorría a los reviewers EN SERIE (2026-08-01).

Con 3 asientos ya se midió un cuelgue de 360s (30-jul) arreglado a presupuesto
TOTAL por llamada; pero la serie seguía sumando: 3 asientos × hasta 120s cada
uno en el peor caso. Con el Cónclave ampliándose a 5 asientos y hasta 4 rondas
(ver ADR de rondas por peligrosidad), 20 llamadas en serie recrearían
exactamente el cuelgue que se cerró el 30-jul. Se paraleliza ANTES de ampliar.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from atlas.core.adversarial_panel import AdversarialPanel, Objection, Severity


@dataclass
class _SlowReviewer:
    reviewer_id: str
    provider: str
    delay_s: float = 0.15
    severity: Severity = Severity.NONE

    def review(self, diff: str, context: str = "") -> Objection:
        time.sleep(self.delay_s)
        return Objection(self.reviewer_id, self.provider, self.severity, "")


class TestReviewersRunConcurrently:
    def test_five_reviewers_finish_close_to_the_slowest_one_not_the_sum(self) -> None:
        reviewers = [
            _SlowReviewer(f"r{i}", f"provider{i}", delay_s=0.15) for i in range(5)
        ]
        panel = AdversarialPanel(reviewers, min_providers=5)

        start = time.monotonic()
        panel.verify("diff")
        elapsed = time.monotonic() - start

        # En serie: ~0.75s (5 × 0.15s). En paralelo: ~0.15-0.35s. El corte a
        # 0.5s separa limpiamente ambos mundos sin ser un test de reloj frágil.
        assert elapsed < 0.5, f"tardó {elapsed:.2f}s — parece secuencial, no paralelo"

    def test_all_five_objections_are_still_collected(self) -> None:
        """Paralelizar no puede perder ninguna voz."""
        reviewers = [_SlowReviewer(f"r{i}", f"p{i}", delay_s=0.05) for i in range(5)]
        panel = AdversarialPanel(reviewers, min_providers=5)

        evidence = panel.verify("diff")

        assert len(evidence.checks) == 5

    def test_order_of_checks_matches_order_of_reviewers(self) -> None:
        """El orden de salida no puede volverse aleatorio: quien lea la
        evidencia espera checks[i] correspondiendo a reviewers[i]."""
        reviewers = [
            _SlowReviewer("first", "p0", delay_s=0.05),
            _SlowReviewer("second", "p1", delay_s=0.01),  # termina ANTES
            _SlowReviewer("third", "p2", delay_s=0.03),
        ]
        panel = AdversarialPanel(reviewers, min_providers=3)

        evidence = panel.verify("diff")

        names = [c.name for c in evidence.checks]
        assert names == ["first@p0", "second@p1", "third@p2"]

    def test_one_reviewer_raising_does_not_kill_the_others(self) -> None:
        """Un reviewer que lanza excepción no debe tumbar el panel entero ni
        impedir que los demás terminen — fail-closed por asiento, no por panel."""

        class _Boom:
            reviewer_id = "boom"
            provider = "boom-provider"

            def review(self, diff: str, context: str = "") -> Objection:
                raise RuntimeError("proveedor caído a media llamada")

        reviewers = [
            _SlowReviewer("ok1", "p1", delay_s=0.02),
            _Boom(),
            _SlowReviewer("ok2", "p2", delay_s=0.02),
        ]
        panel = AdversarialPanel(reviewers, min_providers=2)

        evidence = panel.verify("diff")

        assert len(evidence.checks) == 3
        boom_check = evidence.checks[1]
        # Un reviewer inalcanzable no es una opinión (convención ya fijada por
        # TestUnreachableReviewers): no cuenta como objeción sustantiva propia,
        # aunque la severidad conservada sea MAJOR. Lo que importa aquí es que
        # los OTROS DOS sí se completaron pese a la excepción de este.
        assert boom_check.passed
        assert "MAJOR" in boom_check.detail
        assert evidence.checks[0].name == "ok1@p1"
        assert evidence.checks[2].name == "ok2@p2"
