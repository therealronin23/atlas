"""Escalada de dos niveles del Security Council Gate (ADR-077.2).

El auditor único de `security_council_gate.py` resuelve la mayoría de los
casos (barato, cubre el volumen). Objeción de diversidad cognitiva del
Cónclave real que revisó ADR-077 (2026-07-24): un solo LLM puede sobreajustar
a patrones conocidos y no debe ser la última palabra sobre algo `flagged` --
solo eso paga una segunda opinión del trío real de `deliberation_council`.

`offensive_action` es la excepción: escala SIEMPRE, incluso si la primera
pasada vino `clean`, dado su perfil de consecuencias externas irreversibles
(otra objeción concreta del mismo Cónclave -- no todos los `kind` tienen el
mismo riesgo).

`convene_fn` es la única dependencia inyectada: en producción envuelve
`deliberation_council.convene_for_decision` con `difficulty`/`risk`/
`reviewers` ya fijados por el caller; en tests es un stub -- nunca red real
aquí.
"""

from __future__ import annotations

from typing import Callable

from atlas.core.adversarial_panel import Severity
from atlas.core.decider.security_council_gate import CouncilVerdict, SecurityReport
from atlas.core.verify import Evidence, Verdict

ConveneFn = Callable[[str], "Evidence | None"]


def resolve_council_verdict(
    *, kind: str, first_pass: CouncilVerdict, descriptor: str, convene_fn: ConveneFn
) -> CouncilVerdict:
    """Decide si la primera pasada es el veredicto final o si hace falta una
    segunda opinión real. Fail-closed en la lectura del veredicto del trío:
    solo `Verdict.PASS` limpia un `flagged` -- `UNKNOWN` no es evidencia de
    que esté limpio (unknown > mentir), se queda `flagged`."""
    needs_second_opinion = kind == "offensive_action" or first_pass.status == "flagged"
    if not needs_second_opinion:
        return first_pass

    evidence = convene_fn(descriptor)
    if evidence is None:
        # should_convene() decidió que esto no ameritaba escalar -- sin
        # segunda opinión disponible, la primera pasada es la final.
        return first_pass

    if evidence.verdict == Verdict.PASS:
        return CouncilVerdict(status="clean", report=None)

    detail = evidence.reason or "; ".join(
        c.detail for c in evidence.checks if not c.passed and c.detail
    )
    prior_checks = list(first_pass.report.checks_run) if first_pass.report else []
    return CouncilVerdict(
        status="flagged",
        report=SecurityReport(
            severity=Severity.BLOCKING if evidence.verdict == Verdict.FAIL else Severity.MAJOR,
            checks_run=[*prior_checks, "council_trio"],
            triggered_by=f"trío real ({evidence.verdict.value}): {detail}",
            recommended_action="revisar manual -- segunda opinión del trío confirma o no descarta el riesgo",
        ),
    )
