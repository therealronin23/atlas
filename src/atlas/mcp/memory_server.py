"""
Atlas Core — Shell FastMCP de la raíz de memoria (MCP trunk portable, F1).

Capa de TRANSPORTE: traduce las tools neutras de `MemoryTrunk` a un servidor MCP
real (stdio) que cualquier cliente —Claude Code, Codex, Cursor…— conecta. Esto es
el cross-play: una sola conexión MCP y el agente "te conoce" sin importar el
cliente/modelo.

El SDK `mcp` es una dependencia OPCIONAL (`pip install 'atlas-core[mcp]'`); todo el
valor del núcleo (`MemoryTrunk`) es usable sin ella. El import se hace dentro de
las funciones para no romper el arranque donde el SDK no está.

Diseño: docs/design/mcp_trunk_portable.md (F1).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from atlas.mcp.memory_trunk import MemoryTrunk, MemoryTrunkRouter

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def build_memory_server(trunk: MemoryTrunk, *, name: str = "atlas-memory") -> "FastMCP":
    """Construye un servidor FastMCP que expone `recall`/`add`/`supersede` de un
    `MemoryTrunk`. No arranca transporte; eso es responsabilidad de `serve()`."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(name)

    @server.tool()
    def recall(query: str, k: int = 5) -> list[dict[str, object]]:
        """Recuerda lo que el usuario/agente ya sabe, con texto y procedencia."""
        return [
            {
                "record_id": h.record_id,
                "text": h.text,
                "score": h.score,
                "matched": h.matched,
                "merkle_leaf_hash": h.merkle_leaf_hash,
            }
            for h in trunk.recall(query, k=k)
        ]

    @server.tool()
    def add(text: str, record_id: str | None = None, record_type: str | None = None) -> str:
        """Recuerda un hecho nuevo. Devuelve su id."""
        return trunk.add(text, record_id=record_id, record_type=record_type)

    @server.tool()
    def supersede(old_id: str, new_text: str, record_id: str | None = None) -> str:
        """Reemplaza un recuerdo: el viejo caduca (auditable), el nuevo entra
        vigente con lineage. Devuelve el id nuevo."""
        return trunk.supersede(old_id, new_text, record_id=record_id)

    return server


def build_tenant_memory_server(
    router: MemoryTrunkRouter,
    tenant_resolver: Callable[[], str],
    *,
    name: str = "atlas-memory",
) -> "FastMCP":
    """Construye un servidor FastMCP multi-tenant donde cada ejecución de tool
    deriva el tenant mediante `tenant_resolver()`.

    El tenant se resuelve server-side en cada llamada: el cliente NO lo pasa
    como argumento (evita suplantación). Registra las mismas tools que
    `build_memory_server` pero enrutando al trunk correcto por sesión."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(name)

    @server.tool()
    def recall(query: str, k: int = 5) -> list[dict[str, object]]:
        """Recuerda lo que el usuario/agente ya sabe, con texto y procedencia."""
        trunk = router.for_tenant(tenant_resolver())
        return [
            {
                "record_id": h.record_id,
                "text": h.text,
                "score": h.score,
                "matched": h.matched,
                "merkle_leaf_hash": h.merkle_leaf_hash,
            }
            for h in trunk.recall(query, k=k)
        ]

    @server.tool()
    def add(text: str, record_id: str | None = None, record_type: str | None = None) -> str:
        """Recuerda un hecho nuevo para el tenant activo. Devuelve su id."""
        trunk = router.for_tenant(tenant_resolver())
        return trunk.add(text, record_id=record_id, record_type=record_type)

    @server.tool()
    def supersede(old_id: str, new_text: str, record_id: str | None = None) -> str:
        """Reemplaza un recuerdo del tenant activo. Devuelve el id nuevo."""
        trunk = router.for_tenant(tenant_resolver())
        return trunk.supersede(old_id, new_text, record_id=record_id)

    return server


def serve(db_path: Path, *, name: str = "atlas-memory") -> None:
    """Punto de entrada stdio: monta la raíz de memoria sobre el índice en
    `db_path` y la sirve por stdio (el transporte por defecto de los clientes MCP)."""
    from atlas.memory.embeddings import StubEmbedder
    from atlas.memory.memory_index import SqliteMemoryIndex

    index = SqliteMemoryIndex(db_path, embedder=StubEmbedder(dim=64))
    try:
        server = build_memory_server(MemoryTrunk(index), name=name)
        server.run()
    finally:
        index.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        raise SystemExit("uso: python -m atlas.mcp.memory_server <db_path>")
    serve(Path(sys.argv[1]))
