"""Security Council Gate (ADR-077) -- pre-gate de dos etapas delante del
Decider existente (`atlas.core.decider.decider`).

Diseño revisado por un Cónclave real (2026-07-24,
`scripts/council_adr077_design_review.py`): la objeción BLOCKING más
importante fue que el diseño original no especificaba qué pasa si el
escaneo o el auditor fallan. Aquí es explícito y testeado -- fail-closed:
cualquier excepción en CUALQUIER etapa produce `flagged`, nunca `clean`
(mismo principio I6 de ADR-075: lo no-analizable se rechaza, no se asume
limpio).

Este módulo solo cubre la primera etapa (escaneo + auditor único, barato).
La escalada al trío real de `deliberation_council` para `flagged`/`uncertain`
(ADR-077.2) y el registro de rechazo permanente (ADR-077.3) son piezas
separadas que consumen `CouncilVerdict` como entrada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from atlas.core.adversarial_panel import Severity

CouncilStatus = Literal["clean", "flagged"]


@dataclass(frozen=True)
class ScanFinding:
    """Resultado del escaneo automatizado inyectado (semgrep, CWE-audit, IOC/
    credential checks -- lo que el `kind` concreto reuse)."""

    clean: bool
    detail: str = ""


@dataclass(frozen=True)
class AuditFinding:
    """Resultado del auditor LLM único (barato, una sola voz -- NO el trío de
    `deliberation_council`, reservado para decisiones ADR/irreversibles)."""

    clean: bool
    detail: str = ""


@dataclass(frozen=True)
class SecurityReport:
    """Informe estructurado (formato SOC L1→L2: severidad + checks +
    disparador + acción recomendada) -- nunca un `reason` de una línea."""

    severity: Severity
    checks_run: list[str] = field(default_factory=list)
    triggered_by: str = ""
    recommended_action: str = ""


@dataclass(frozen=True)
class CouncilVerdict:
    status: CouncilStatus
    report: SecurityReport | None = None


ScanFn = Callable[[str], ScanFinding]
AuditFn = Callable[[str], AuditFinding]


def default_scan_fn(descriptor: str) -> ScanFinding:
    """Escaneo automatizado por defecto -- reusa las MISMAS regexes IOC/
    credencial que ya viven en `AutonomousDecider` (probadas en producción,
    603 verdicts reales verificados en la auditoría de ADR-077). Primera
    línea de defensa determinista, sin LLM, sin coste de red."""
    from atlas.core.decider.autonomous_decider import _CREDENTIAL_KW, _IOC_REGEXES, _fold

    surface = _fold(descriptor)
    for rx in _IOC_REGEXES:
        if rx.search(surface):
            return ScanFinding(clean=False, detail=f"IOC: patrón peligroso ({rx.pattern})")
    for kw in _CREDENTIAL_KW:
        if kw in surface:
            return ScanFinding(clean=False, detail=f"IOC: menciona credenciales ({kw!r})")
    return ScanFinding(clean=True)


_AUDIT_PROMPT = (
    "Eres un auditor de seguridad hostil. Revisa esta acción candidata antes "
    "de que se ejecute. Responde en la PRIMERA línea SOLO con LIMPIO o "
    "SOSPECHOSO. En las siguientes líneas, explica por qué.\n\nACCIÓN:\n{descriptor}\n"
)


def build_llm_audit_fn(hub: Any) -> AuditFn:
    """Construye el auditor LLM único (barato, una sola voz) a partir de un
    `InferenceHub` ya configurado. NO es el trío de `deliberation_council`
    -- esa es la segunda opinión que se paga solo si esto marca `flagged`
    (ver `security_council_escalation.py`)."""

    def audit(descriptor: str) -> AuditFinding:
        from atlas.core.inference_hub import InferenceRequest

        resp = hub.infer(InferenceRequest(prompt=_AUDIT_PROMPT.format(descriptor=descriptor)))
        if not resp.success or not resp.text.strip():
            raise RuntimeError("auditor LLM sin respuesta")
        first = resp.text.strip().splitlines()[0].strip().strip("[](){}*#:.- ").upper()
        clean = first.startswith("LIMPIO") or first.startswith("CLEAN")
        return AuditFinding(clean=clean, detail=resp.text.strip())

    return audit


def run_security_council_gate(
    descriptor: str, *, scan_fn: ScanFn, audit_fn: AuditFn
) -> CouncilVerdict:
    """Corre escaneo automatizado, luego (solo si limpio) el auditor LLM.

    El escaneo va primero y corta en corto si ya marca algo -- el auditor LLM
    es la etapa cara, no tiene sentido pagarla si el escaneo barato ya
    encontró un problema. Fail-closed en cada etapa: una excepción no
    anticipada NUNCA se trata como "sigue, debe estar limpio" -- se trata
    como `flagged` con severidad `MAJOR`, igual que un hallazgo real."""
    checks_run: list[str] = []

    try:
        scan = scan_fn(descriptor)
    except Exception as exc:  # noqa: BLE001 -- fail-closed, no fail-open
        return CouncilVerdict(
            status="flagged",
            report=SecurityReport(
                severity=Severity.MAJOR,
                checks_run=[*checks_run, "scan:crashed"],
                triggered_by=f"escaneo automatizado falló (fail-closed): {exc}",
                recommended_action="revisar manual -- el escaneo no pudo completarse",
            ),
        )
    checks_run.append("scan")
    if not scan.clean:
        return CouncilVerdict(
            status="flagged",
            report=SecurityReport(
                severity=Severity.MAJOR,
                checks_run=checks_run,
                triggered_by=f"escaneo automatizado: {scan.detail}",
                recommended_action="revisar manual",
            ),
        )

    try:
        audit = audit_fn(descriptor)
    except Exception as exc:  # noqa: BLE001 -- fail-closed, no fail-open
        return CouncilVerdict(
            status="flagged",
            report=SecurityReport(
                severity=Severity.MAJOR,
                checks_run=[*checks_run, "llm_audit:crashed"],
                triggered_by=f"auditor LLM falló (fail-closed): {exc}",
                recommended_action="revisar manual -- el auditor no pudo completarse",
            ),
        )
    checks_run.append("llm_audit")
    if not audit.clean:
        return CouncilVerdict(
            status="flagged",
            report=SecurityReport(
                severity=Severity.MAJOR,
                checks_run=checks_run,
                triggered_by=f"auditor LLM: {audit.detail}",
                recommended_action="revisar manual",
            ),
        )

    return CouncilVerdict(status="clean", report=None)
