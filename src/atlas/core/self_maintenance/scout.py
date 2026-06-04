"""ADR-039 slice 1 — Scout read-only de salud/deuda.

Front-half del pipeline de auto-mantenimiento (Scout → Analyst → Proposer →
HITL → Executor). En este slice el Scout **solo observa**: recolecta señales
read-only del estado interno y emite un informe estructurado auditado en Merkle.
No muta nada, no propone nada (eso es Analyst/Proposer, slices posteriores).

Desviación consciente respecto al slice 1 *literal* del ADR: aquél descubre
candidatos **externos** (registry MCP + arxiv, egress, contenido no confiable) y
exige registrar sus readers en ``UNTRUSTED_READERS``. Esta primera entrega es
deliberadamente más pequeña: un Scout **interno** que lee estado de confianza
del propio sistema. Por eso ``UNTRUSTED_READERS`` / ``wrap_untrusted`` **no
aplican** — no se ingiere nada untrusted. El Scout externo del ADR (con su
gate de corroboración y dual-LLM) entra en slices siguientes.

Sin LLM: el ADR solo lo exige en el Analyst (slice 2, dual-LLM con separación
datos/control). Aquí las señales se derivan por reglas deterministas.

El Scout no posee sus fuentes: las recibe por inyección (callables) para reusar
las primitivas read-only que ya existen (``health_report``, ``GitReadTools``,
``ErrorRegistry``) sin duplicar su lógica ni acoplarse al ``Orchestrator``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from atlas.logging.merkle_logger import MerkleLogger

SEVERITY_INFO = "info"
SEVERITY_WARN = "warn"
SEVERITY_ALERT = "alert"

# Orden para comparar la severidad agregada del informe.
_SEVERITY_RANK = {SEVERITY_INFO: 0, SEVERITY_WARN: 1, SEVERITY_ALERT: 2}


@dataclass(frozen=True)
class MaintenanceSignal:
    """Una señal read-only de salud o deuda detectada por el Scout.

    ``kind`` la identifica de forma estable (para que slices posteriores la
    correlacionen); ``severity`` es ``info | warn | alert``; ``value`` lleva el
    dato crudo que la disparó (recuento, flag, etc.)."""

    kind: str
    severity: str
    detail: str
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "detail": self.detail,
            "value": self.value,
        }


@dataclass(frozen=True)
class ScoutReport:
    """Informe estructurado de una pasada del Scout. Solo observación."""

    id: str
    generated_at: str
    health: dict[str, Any]
    git: dict[str, Any]
    recent_failures: int
    signals: list[MaintenanceSignal]

    @property
    def max_severity(self) -> str:
        """Severidad agregada (la más alta entre las señales); ``info`` si vacío."""
        if not self.signals:
            return SEVERITY_INFO
        return max(self.signals, key=lambda s: _SEVERITY_RANK.get(s.severity, 0)).severity

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "generated_at": self.generated_at,
            "health": self.health,
            "git": self.git,
            "recent_failures": self.recent_failures,
            "max_severity": self.max_severity,
            "signals": [s.to_dict() for s in self.signals],
        }


class MaintenanceScout:
    """Recolector read-only de señales de salud/deuda (ADR-039 slice 1).

    Pura observación: ``survey()`` llama a los providers inyectados, deriva
    señales por reglas deterministas y audita el informe en Merkle. Nunca
    ejecuta nada mutante.
    """

    AGENT = "self_maintenance.scout"

    def __init__(
        self,
        *,
        merkle: MerkleLogger,
        health_provider: Callable[[], dict[str, Any]],
        git_status_provider: Callable[[], dict[str, Any]],
        failure_provider: Callable[[], Sequence[Any]],
        recent_failure_threshold: int = 3,
    ) -> None:
        self._merkle = merkle
        self._health_provider = health_provider
        self._git_status_provider = git_status_provider
        self._failure_provider = failure_provider
        self._recent_failure_threshold = recent_failure_threshold

    def survey(self) -> ScoutReport:
        """Observa el estado interno y devuelve un informe auditado. Read-only."""
        health = dict(self._health_provider() or {})
        git = dict(self._git_status_provider() or {})
        failures = list(self._failure_provider() or [])

        signals = self._derive_signals(health, git, len(failures))
        report = ScoutReport(
            id=f"scout-{uuid.uuid4().hex[:12]}",
            generated_at=datetime.now(timezone.utc).isoformat(),
            health=health,
            git=git,
            recent_failures=len(failures),
            signals=signals,
        )
        self._audit(report)
        return report

    # ------------------------------------------------------------------
    # Derivación determinista de señales (sin LLM)
    # ------------------------------------------------------------------

    def _derive_signals(
        self, health: dict[str, Any], git: dict[str, Any], failure_count: int
    ) -> list[MaintenanceSignal]:
        signals: list[MaintenanceSignal] = []

        # Integridad de la cadena de auditoría: una cadena rota es lo más grave.
        if health.get("merkle_chain_ok") is False:
            signals.append(MaintenanceSignal(
                kind="merkle_chain_broken",
                severity=SEVERITY_ALERT,
                detail="la cadena Merkle no verifica",
                value=False,
            ))

        if health.get("emergency_mode") is True:
            signals.append(MaintenanceSignal(
                kind="emergency_mode",
                severity=SEVERITY_ALERT,
                detail="GovernanceL0 en modo de emergencia",
                value=True,
            ))

        if health.get("governance_ok") is False:
            signals.append(MaintenanceSignal(
                kind="governance_degraded",
                severity=SEVERITY_ALERT,
                detail="governance_ok=False",
                value=False,
            ))

        thermal = health.get("thermal_mode")
        if thermal is not None and thermal != "normal":
            signals.append(MaintenanceSignal(
                kind="thermal_throttled",
                severity=SEVERITY_WARN,
                detail=f"modo térmico no nominal: {thermal}",
                value=thermal,
            ))

        if health.get("hermes_reachable") is False:
            signals.append(MaintenanceSignal(
                kind="hermes_unreachable",
                severity=SEVERITY_WARN,
                detail="el gemelo Hermes no es alcanzable",
                value=health.get("hermes_mode"),
            ))

        if failure_count >= self._recent_failure_threshold:
            signals.append(MaintenanceSignal(
                kind="failure_backlog",
                severity=SEVERITY_WARN,
                detail=f"{failure_count} fallos en el ErrorRegistry (umbral {self._recent_failure_threshold})",
                value=failure_count,
            ))

        queue_depth = health.get("queue_depth")
        if isinstance(queue_depth, int) and queue_depth > 0:
            signals.append(MaintenanceSignal(
                kind="offline_backlog",
                severity=SEVERITY_INFO,
                detail=f"{queue_depth} tareas en la cola offline",
                value=queue_depth,
            ))

        pending = health.get("pending_approvals_count")
        if isinstance(pending, int) and pending > 0:
            signals.append(MaintenanceSignal(
                kind="pending_approvals",
                severity=SEVERITY_INFO,
                detail=f"{pending} aprobaciones pendientes",
                value=pending,
            ))

        git_signal = self._git_signal(git)
        if git_signal is not None:
            signals.append(git_signal)
        return signals

    def _git_signal(self, git: dict[str, Any]) -> MaintenanceSignal | None:
        """Señal de estado del repo de código (read-only, `git status --short`)."""
        if "error" in git:
            return MaintenanceSignal(
                kind="git_unavailable",
                severity=SEVERITY_WARN,
                detail=f"git no disponible: {git['error']}",
                value=None,
            )
        stdout = str(git.get("stdout") or "").strip()
        if stdout:
            dirty = len([ln for ln in stdout.splitlines() if ln.strip()])
            return MaintenanceSignal(
                kind="workspace_dirty",
                severity=SEVERITY_INFO,
                detail=f"{dirty} entradas sin commitear en el repo de código",
                value=dirty,
            )
        return None

    # ------------------------------------------------------------------

    def _audit(self, report: ScoutReport) -> None:
        try:
            self._merkle.log(
                action="self_maintenance.scout_survey",
                agent=self.AGENT,
                result="ok",
                risk_level="safe",
                payload={
                    "report_id": report.id,
                    "max_severity": report.max_severity,
                    "signal_kinds": [s.kind for s in report.signals],
                    "recent_failures": report.recent_failures,
                },
            )
        except Exception:  # noqa: BLE001 — la auditoría no rompe la observación
            pass
