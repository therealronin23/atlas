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

    def status(self) -> dict:
        st = self._orch.status()
        return asdict(st)

    def submit_task(self, intent: str) -> dict:
        task = self._orch.handle_intent(intent)
        out = {
            "task_id": task.id,
            "status": task.status.value,
            "route": task.route.value if task.route else None,
        }
        if task.result:
            out["result"] = task.result
        if task.error:
            out["error"] = task.error
        return out

    def recent_audit(self, n: int = 10) -> list[dict]:
        return self._orch.audit_tail(n)

    def list_tools(self) -> list[dict]:
        return self._orch.tools()

    def triage(self) -> dict:
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

    def pending_approvals(self) -> list[dict]:
        return self._orch.pending_approvals()

    def approve(self, task_id: str, approved: bool) -> dict:
        return self._orch.approve_pending(task_id, approved)
