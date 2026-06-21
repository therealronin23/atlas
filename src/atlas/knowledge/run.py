"""
Consumidor vivo de atlas.knowledge.mission (cierra el "no-cableado" de F3).

Provee run_mission como entrypoint puro e inyectable: construye un MissionRunner
con las dependencias recibidas y delega en run_once. Sin I/O propio; todo el
acceso a red o disco lo decide el caller a través de KnowledgeBase y las fuentes.
"""

from __future__ import annotations

from atlas.knowledge.mission import Mission, MissionReport, MissionRunner
from atlas.knowledge.sources import KnowledgeSource
from atlas.knowledge.base import KnowledgeBase
from atlas.knowledge.verifier import KnowledgeVerifier


def run_mission(
    mission: Mission,
    *,
    sources: dict[str, KnowledgeSource],
    base: KnowledgeBase,
    verifier: KnowledgeVerifier,
    queries: dict[str, object] | None = None,
) -> MissionReport:
    """Construye un MissionRunner con las dependencias inyectadas y ejecuta run_once.

    Args:
        mission:  Misión a ejecutar (dominio, goal, source_ids).
        sources:  Mapa source_id → KnowledgeSource registrado.
        base:     KnowledgeBase donde se persistirán los artefactos verificados.
        verifier: KnowledgeVerifier que valida cada artefacto antes de ingestarlo.
        queries:  Parámetros opcionales por source_id pasados a KnowledgeSource.fetch.

    Returns:
        MissionReport con conteos de ingesta, rechazo y errores por fuente.
    """
    runner = MissionRunner(sources=sources, verifier=verifier, base=base)
    return runner.run_once(mission, queries=queries)
