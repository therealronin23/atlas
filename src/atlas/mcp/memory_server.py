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
    from atlas.memory.memory_index import SqliteMemoryIndex
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

    @server.tool()
    def recall_multihop(query: str, hops: int = 2) -> list[dict[str, object]]:
        """Encadena recalls semánticos hasta `hops` saltos. Útil para recuperar
        memorias no directamente relacionadas con la query pero sí con sus vecinos.
        Devuelve la cadena ordenada con texto y procedencia."""
        return [
            {
                "record_id": h.record_id,
                "text": h.text,
                "score": h.score,
                "matched": h.matched,
                "merkle_leaf_hash": h.merkle_leaf_hash,
            }
            for h in trunk.recall_multihop(query, hops=hops)
        ]

    @server.tool()
    def shred(record_id: str) -> str:
        """Ejerce el derecho al olvido: destruye irreversiblemente el contenido
        de `record_id`. El vector persiste (para auditoría) pero el texto no.
        Lanza KeyError si el id no existe."""
        trunk.shred(record_id)
        return f"shredded:{record_id}"

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

    @server.tool()
    def recall_multihop(query: str, hops: int = 2) -> list[dict[str, object]]:
        """Encadena recalls semánticos hasta `hops` saltos para el tenant activo.
        Devuelve la cadena ordenada con texto y procedencia."""
        trunk = router.for_tenant(tenant_resolver())
        return [
            {
                "record_id": h.record_id,
                "text": h.text,
                "score": h.score,
                "matched": h.matched,
                "merkle_leaf_hash": h.merkle_leaf_hash,
            }
            for h in trunk.recall_multihop(query, hops=hops)
        ]

    @server.tool()
    def shred(record_id: str) -> str:
        """Ejerce el derecho al olvido del tenant activo: destruye irreversiblemente
        el contenido de `record_id`. Lanza KeyError si el id no existe."""
        trunk = router.for_tenant(tenant_resolver())
        trunk.shred(record_id)
        return f"shredded:{record_id}"

    return server


def build_gated_index(
    db_path: Path, *, require_provenance: bool = False
) -> "SqliteMemoryIndex":
    """Construye un SqliteMemoryIndex con el gate correcto según `require_provenance`.
    Extraído para poder testearlo sin arrancar transporte real."""
    from atlas.memory.embeddings import default_embedder
    from atlas.memory.memory_index import ProvenanceWriteGate, SqliteMemoryIndex

    gate = ProvenanceWriteGate() if require_provenance else None
    # Embedder gobernado por env (ATLAS_EMBEDDER=fastembed → semántico local; default stub).
    return SqliteMemoryIndex(db_path, embedder=default_embedder(), write_gate=gate)


def serve(db_path: Path, *, name: str = "atlas-memory", require_provenance: bool = False) -> None:
    """Punto de entrada stdio: monta la raíz de memoria sobre el índice en
    `db_path` y la sirve por stdio (el transporte por defecto de los clientes MCP).

    Si `require_provenance` es True, el índice exige procedencia en cada escritura
    (anti-envenenamiento en producción). Default False = compat sin gate."""
    index = build_gated_index(db_path, require_provenance=require_provenance)
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
