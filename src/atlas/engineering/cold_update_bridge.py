"""Puente ColdUpdate→plano de ingeniería (F1.3, 2026-07-31).

`ColdUpdateManager.validate()` ya clasificaba la causa raíz de cada
validación fallida (`cold_update_manager.py:459-468`) y guardaba el veredicto
en `proposal.forensics["root_cause"]` como dict crudo. **Ahí moría**: nadie lo
proyectaba al journal versionado de `EngineeringFinding`.

Por qué importa más de lo que parece: `diagnostics.py:320` es el ÚNICO
productor del repo que rellena `locations` en un finding — `review.py:141` y
la normalización de `findings.py` emiten `locations=()`. Y
`hypotheses.compose_hypotheses()` necesita justamente un `FindingLocation`.
Sin este puente, cablear `hypotheses.py` produciría un caller que itera
siempre sobre una tupla vacía: cableado hueco, la misma trampa de ADC-WO-108.

Este módulo COMPONE lo que ya existe (`EngineeringDiagnosticCoordinator` +
`EngineeringDiagnosticRequest.from_validation_report` + el veredicto ya
calculado) en vez de crear otro clasificador, que es el riesgo que el propio
work order nombra.

Dos invariantes:

- **Coste**: el veredicto ya calculado se REUTILIZA vía `PrecomputedRootCause`.
  Volver a llamar a `RootCauseClassifier.classify()` duplicaría su camino LLM.
- **Señal, nunca puerta**: un fallo aquí jamás puede tumbar una validación
  gobernada de ColdUpdate. Mismo criterio que el bloque del clasificador.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from atlas.core.validation_runner import ValidationReport
from atlas.engineering.diagnostics import (
    EngineeringDiagnosticCoordinator,
    EngineeringDiagnosticRequest,
)
from atlas.engineering.findings import (
    _SELF_AUDIT_SEVERITIES,
    EngineeringFinding,
    EngineeringFindingStore,
    FindingSeverity,
)
from atlas.events.schemas import Risk

_SAFE_CHARS = frozenset("_.:-")


class _VerdictLike(Protocol):
    classification: str
    reason: str
    evidence_paths: list[str]
    used_llm: bool


class _ProposalLike(Protocol):
    id: str
    base_ref: str
    patch_sha256: str
    risk: str


class PrecomputedRootCause:
    """Adapta un `RootCauseVerdict` YA calculado al seam que
    `EngineeringDiagnosticCoordinator` espera.

    Existe por coste, no por elegancia: el coordinador llama a
    `classify()` por dentro, y `RootCauseClassifier` tiene un camino LLM.
    Como `ColdUpdateManager` ya clasificó ese mismo fallo un instante antes,
    reclasificar sería pagar dos veces por la misma respuesta."""

    def __init__(self, verdict: _VerdictLike) -> None:
        self._verdict = verdict

    def classify(
        self, *, pytest_summary: str, mypy_summary: str, base_ref: str = "HEAD"
    ) -> _VerdictLike:
        return self._verdict


def _safe_correlation_id(raw: str) -> str:
    """`_SAFE_CORRELATION_ID` exige `[A-Za-z0-9_.:-]{1,160}`; un id de
    propuesta ya suele cumplirlo, pero no se asume."""
    cleaned = "".join(c if c.isalnum() or c in _SAFE_CHARS else "_" for c in raw)
    return (cleaned or "unknown")[:160]


class ColdUpdateDiagnosticSink:
    """Proyecta una validación FALLIDA de ColdUpdate al journal de findings.

    Se inyecta en `ColdUpdateManager` igual que `root_cause_classifier`
    (`orchestrator.py:793`): opcional, `None` por defecto, y el Orchestrator
    es quien decide construirlo."""

    def __init__(self, *, store: EngineeringFindingStore, repository: str) -> None:
        self._store = store
        self._repository = repository

    def record(
        self,
        *,
        proposal: _ProposalLike,
        report: ValidationReport,
        verdict: _VerdictLike,
    ) -> EngineeringFinding | None:
        """Devuelve el finding registrado, o `None` si no había nada que
        registrar o si algo falló. NUNCA lanza: es señal, no puerta."""
        if report.passed:
            return None
        try:
            return self._record(proposal, report, verdict)
        except Exception:  # noqa: BLE001 — señal, jamás bloquea validate()
            return None

    def _record(
        self,
        proposal: _ProposalLike,
        report: ValidationReport,
        verdict: _VerdictLike,
    ) -> EngineeringFinding | None:
        # Se reusa el vocabulario de riesgo YA gobernado (low/medium/high/
        # critical) en vez de inventar una escala nueva.
        severity, risk = _SELF_AUDIT_SEVERITIES.get(
            proposal.risk, (FindingSeverity.MAJOR, Risk.MEDIUM)
        )
        request = EngineeringDiagnosticRequest.from_validation_report(
            validation=report,
            run_id=f"cold_update-{proposal.id}",
            task_id=None,
            mission_id=None,
            repository=self._repository,
            base_revision=proposal.base_ref,
            # El candidato no es un commit: es el parche staged en el worktree
            # aislado. Su sha256 es su identidad honesta.
            candidate_revision=proposal.patch_sha256 or proposal.id,
            correlation_id=_safe_correlation_id(proposal.id),
            # La ruta real que dispara esto (`cli.py:645`, `golden_route.py:297`).
            command=("atlas", "update", "validate", proposal.id),
            # No se captura entorno: `_sanitize_environment` redacta, pero lo
            # que no se recoge no se puede filtrar.
            environment=(),
            at=datetime.now(timezone.utc).isoformat(),
            severity=severity,
            risk=risk,
        )
        coordinator = EngineeringDiagnosticCoordinator(
            store=self._store, classifier=PrecomputedRootCause(verdict)
        )
        return coordinator.diagnose(request).finding


def build_sink(store_path: Path, repository: str) -> ColdUpdateDiagnosticSink:
    """Constructor de conveniencia para el Orchestrator."""
    return ColdUpdateDiagnosticSink(
        store=EngineeringFindingStore(store_path), repository=repository
    )
