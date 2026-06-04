"""Agente de auto-mantenimiento (ADR-039).

Pipeline Scout → Analyst → Proposer → HITL → Executor. Por ahora solo el
slice 1: ``MaintenanceScout`` read-only (observa salud/deuda, no muta ni
propone).
"""

from atlas.core.self_maintenance.scout import (
    SEVERITY_ALERT,
    SEVERITY_INFO,
    SEVERITY_WARN,
    MaintenanceScout,
    MaintenanceSignal,
    ScoutReport,
)

__all__ = [
    "SEVERITY_ALERT",
    "SEVERITY_INFO",
    "SEVERITY_WARN",
    "MaintenanceScout",
    "MaintenanceSignal",
    "ScoutReport",
]
