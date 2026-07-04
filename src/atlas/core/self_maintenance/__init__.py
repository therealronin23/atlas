"""Agente de auto-mantenimiento (ADR-039).

Pipeline Scout → Analyst → Proposer → HITL → Executor. Implementado hasta el
slice 2:

- slice 1: ``MaintenanceScout`` read-only (observa salud/deuda, no muta ni propone).
- slice 2: ``MaintenanceAnalyst`` dual-LLM + gate de corroboración → ``McpProposal``
  tipada (solo lo corroborado por fuente autoritativa; sin auto-apply).
- slice 3: ``MaintenanceAdopter`` cablea propuesta → ``add_server`` reusando el
  seam del decisor (ADR-040). No decide; traduce, invoca y audita.
"""

from atlas.core.self_maintenance.adopter import MaintenanceAdopter
from atlas.core.self_maintenance.analyst import MaintenanceAnalyst
from atlas.core.self_maintenance.candidate import (
    PROVENANCE_AUTHORITATIVE,
    PROVENANCE_COMMUNITY,
    CodegenTarget,
    DepCandidate,
    Evidence,
    McpCandidate,
    McpProposal,
    Source,
    TypedSummary,
)
from atlas.core.self_maintenance.codegen_proposer import CodegenProposer
from atlas.core.self_maintenance.community_scout import CommunityScout
from atlas.core.self_maintenance.dep_analyst import DepAnalyst, DepReviewVerdict
from atlas.core.self_maintenance.dep_proposer import DepProposer
from atlas.core.self_maintenance.dep_scout import PYPI_JSON_URL, DepScout
from atlas.core.self_maintenance.presentation import format_proposal
from atlas.core.self_maintenance.registry_scout import REGISTRY_URL, RegistryScout
from atlas.core.self_maintenance.scheduler import MaintenanceScheduler
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
    "PYPI_JSON_URL",
    "REGISTRY_URL",
    "CodegenProposer",
    "CodegenTarget",
    "CommunityScout",
    "DepAnalyst",
    "DepCandidate",
    "DepProposer",
    "DepReviewVerdict",
    "DepScout",
    "RegistryScout",
    "SEVERITY_ALERT",
    "SEVERITY_INFO",
    "SEVERITY_WARN",
    "Evidence",
    "MaintenanceAdopter",
    "MaintenanceAnalyst",
    "MaintenanceScheduler",
    "MaintenanceScout",
    "MaintenanceSignal",
    "McpCandidate",
    "McpProposal",
    "ScoutReport",
    "Source",
    "TypedSummary",
    "format_proposal",
]
