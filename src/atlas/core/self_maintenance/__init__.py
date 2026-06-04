"""Agente de auto-mantenimiento (ADR-039).

Pipeline Scout → Analyst → Proposer → HITL → Executor. Implementado hasta el
slice 2:

- slice 1: ``MaintenanceScout`` read-only (observa salud/deuda, no muta ni propone).
- slice 2: ``MaintenanceAnalyst`` dual-LLM + gate de corroboración → ``McpProposal``
  tipada (solo lo corroborado por fuente autoritativa; sin auto-apply).
"""

from atlas.core.self_maintenance.analyst import MaintenanceAnalyst
from atlas.core.self_maintenance.candidate import (
    PROVENANCE_AUTHORITATIVE,
    PROVENANCE_COMMUNITY,
    Evidence,
    McpCandidate,
    McpProposal,
    Source,
    TypedSummary,
)
from atlas.core.self_maintenance.presentation import format_proposal
from atlas.core.self_maintenance.scout import (
    SEVERITY_ALERT,
    SEVERITY_INFO,
    SEVERITY_WARN,
    MaintenanceScout,
    MaintenanceSignal,
    ScoutReport,
)

__all__ = [
    "PROVENANCE_AUTHORITATIVE",
    "PROVENANCE_COMMUNITY",
    "SEVERITY_ALERT",
    "SEVERITY_INFO",
    "SEVERITY_WARN",
    "Evidence",
    "MaintenanceAnalyst",
    "MaintenanceScout",
    "MaintenanceSignal",
    "McpCandidate",
    "McpProposal",
    "ScoutReport",
    "Source",
    "TypedSummary",
    "format_proposal",
]
