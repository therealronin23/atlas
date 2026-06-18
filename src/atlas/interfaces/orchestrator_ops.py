"""
Adaptador del Orchestrator al protocolo AtlasOps que consume TelegramBot.

Vive en interfaces/ (no en core/) porque pertenece a la frontera entre el
nucleo y las superficies de interaccion (CLI, Telegram, futuro dashboard).
El bot no sabe nada del Orchestrator; el Orchestrator no sabe nada del bot.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any


class OrchestratorOps:
    """
    Implementa el protocolo AtlasOps (telegram_bot.AtlasOps) sobre un
    Orchestrator concreto. Tambien expone approve(task_id, approved) y
    pending_approvals() para el flujo de aprobacion con botones inline.
    """

    def __init__(self, orchestrator: Any) -> None:
        self._orch = orchestrator

    def status(self) -> dict[str, Any]:
        st = self._orch.status()
        return asdict(st)  # dataclasses.asdict returns dict[str,Any]

    def submit_task(self, intent: str) -> dict[str, Any]:
        task = self._orch.handle_intent(intent)
        out: dict[str, Any] = {
            "task_id": task.id,
            "status": task.status.value,
            "route": task.route.value if task.route else None,
        }
        if task.result:
            out["result"] = task.result
        if task.error:
            out["error"] = task.error
        return out

    def recent_audit(self, n: int = 10) -> list[dict[str, Any]]:
        return self._orch.audit_tail(n)  # type: ignore[no-any-return]

    def list_tools(self) -> list[dict[str, Any]]:
        return self._orch.tools()  # type: ignore[no-any-return]

    def triage(self) -> dict[str, Any]:
        thermal = getattr(self._orch, "_thermal_watchdog", None)
        if thermal is None:
            return {"mode": "UNKNOWN", "temperature_c": None, "ram_free_mb": None}
        state = thermal.current_state()
        return {
            "mode": state.operational_mode.value,
            "temperature_c": state.temperature_celsius,
            "ram_free_mb": state.ram_free_mb,
            "policy": state.policy,
            "emergency": state.emergency,
        }

    def pending_approvals(self) -> list[dict[str, Any]]:
        return self._orch.pending_approvals()  # type: ignore[no-any-return]

    def approve(
        self,
        task_id: str,
        approved: bool,
        *,
        abort: bool = False,
        approve_only: list[str] | None = None,
    ) -> dict[str, Any]:
        # ADR-033 #3: `abort` cancela del todo; `approve_only` ejecuta solo un
        # subconjunto del lote de mutaciones (aprobación parcial).
        return self._orch.approve_pending(  # type: ignore[no-any-return]
            task_id, approved, abort=abort, approve_only=approve_only,
        )

    def sweep_suspensions(self, ttl_seconds: float | None = None) -> list[str]:
        """ADR-033 #1: barre loops suspendidos expirados. Devuelve task_ids."""
        return self._orch.sweep_expired_suspensions(ttl_seconds=ttl_seconds)  # type: ignore[no-any-return]
