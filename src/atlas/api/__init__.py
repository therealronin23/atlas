"""Atlas OS — Backend Bridge (ADR-058).

App FastAPI separada del dashboard (7331) y de exec_api. Read-only sobre el
core: PROHIBIDO instanciar Orchestrator aquí (bug del doble Orchestrator =
corrupción Merkle; ver docs/continuation/KNOWN_RISKS.md #1). El único estado
que escribe es el event store OS.
"""

from atlas.api.server import create_app

__all__ = ["create_app"]
