"""
Tests del F1 del MCP trunk portable: la raíz de memoria expuesta como tools
neutras (`add` / `recall` / `supersede`) sobre el sustrato verificable.

Capa NEUTRA, transport-agnostic: `MemoryTrunk` no sabe nada de MCP; es Python
puro sobre `SqliteMemoryIndex`. El shell FastMCP se monta encima cuando el SDK
esté disponible (prove-it). Aquí se prueba el contenido, que es el moat.

Diseño: docs/design/mcp_trunk_portable.md (F1).
"""

from __future__ import annotations

from pathlib import Path

from atlas.memory.embeddings import StubEmbedder
from atlas.memory.memory_index import SqliteMemoryIndex


# ---------------------------------------------------------------------------
# Cimiento: el índice debe poder devolver el TEXTO de un id (recall útil)
# ---------------------------------------------------------------------------


def test_index_text_of_returns_stored_text(tmp_path: Path) -> None:
    from atlas.memory.record import GenericRecord

    idx = SqliteMemoryIndex(tmp_path / "g.db", embedder=StubEmbedder(dim=64))
    idx.upsert(GenericRecord("r1", "el cielo es azul"))
    assert idx.text_of("r1") == "el cielo es azul"


def test_index_text_of_missing_id_returns_none(tmp_path: Path) -> None:
    idx = SqliteMemoryIndex(tmp_path / "g.db", embedder=StubEmbedder(dim=64))
    assert idx.text_of("nope") is None


# ---------------------------------------------------------------------------
# MemoryTrunk: las tools neutras (add / recall / supersede)
# ---------------------------------------------------------------------------


def _trunk(tmp_path: Path) -> "MemoryTrunk":
    from atlas.mcp.memory_trunk import MemoryTrunk

    idx = SqliteMemoryIndex(tmp_path / "trunk.db", embedder=StubEmbedder(dim=64), threshold=0.8)
    return MemoryTrunk(idx)


def test_add_returns_id_and_is_recallable(tmp_path: Path) -> None:
    trunk = _trunk(tmp_path)
    rid = trunk.add("tortilla de patata huevo cebolla aceite")
    assert isinstance(rid, str) and rid

    hits = trunk.recall("patata cebolla huevo aceite tortilla")
    assert hits, "recall debería encontrar el record recién añadido"
    top = hits[0]
    assert top.record_id == rid
    assert top.text == "tortilla de patata huevo cebolla aceite"
    assert top.matched is True
    assert 0.0 <= top.score <= 1.0


def test_recall_empty_index_returns_empty_list(tmp_path: Path) -> None:
    trunk = _trunk(tmp_path)
    assert trunk.recall("lo que sea") == []


def test_add_with_explicit_id_is_honored(tmp_path: Path) -> None:
    trunk = _trunk(tmp_path)
    rid = trunk.add("el cielo es azul", record_id="sky-1")
    assert rid == "sky-1"
    assert trunk.recall("azul cielo")[0].record_id == "sky-1"


def test_origin_helpers_classify_factual_and_personal(tmp_path: Path) -> None:
    trunk = _trunk(tmp_path)
    fact = trunk.add_from_knowledge_src("la wikipedia tiene procedencia factual", record_id="fact-1")
    pref = trunk.add_from_user_preference("prefiero respuestas concisas", record_id="pref-1")

    assert fact == "fact-1"
    assert pref == "pref-1"
    assert [h.record_id for h in trunk.recall("wikipedia factual", k=5)] == ["fact-1"]
    assert all(h.record_id != "pref-1" for h in trunk.recall("respuestas concisas", k=5))


def test_supersede_retires_old_and_surfaces_new(tmp_path: Path) -> None:
    trunk = _trunk(tmp_path)
    old = trunk.add("el servidor escucha en el puerto 8080", record_id="cfg-1")
    new = trunk.supersede(old, "el servidor escucha en el puerto 9090", record_id="cfg-2")
    assert new == "cfg-2"

    hits = trunk.recall("en qué puerto escucha el servidor")
    ids = [h.record_id for h in hits]
    # La vieja caducó: no debe surfacear; la nueva sí, como vigente.
    assert "cfg-1" not in ids
    assert "cfg-2" in ids


# ---------------------------------------------------------------------------
# Shell FastMCP: monta las tools neutras como un servidor MCP real.
# Se salta donde el SDK no está instalado (la suite sigue verde sin la dep).
# ---------------------------------------------------------------------------


import pytest  # noqa: E402


def test_build_server_registers_memory_tools(tmp_path: Path) -> None:
    pytest.importorskip("mcp")
    import asyncio

    from atlas.mcp.memory_server import build_memory_server

    server = build_memory_server(_trunk(tmp_path))
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert {"recall", "add", "add_from_knowledge_src", "add_from_user_preference", "supersede"} <= names


def test_cross_play_roundtrip_from_another_cwd(tmp_path: Path) -> None:
    """La prueba real del cross-play (F1): un cliente MCP en OTRO directorio de
    trabajo (otro 'proyecto') conecta por stdio, añade un recuerdo y lo recupera.
    El 'save file' (la db) vive en una capa neutra; el cliente solo habla MCP."""
    pytest.importorskip("mcp")
    import asyncio
    import sys

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    db = tmp_path / "save" / "memory.db"
    other_project = tmp_path / "otro-proyecto"
    other_project.mkdir()

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "atlas.mcp.memory_server", str(db)],
        cwd=str(other_project),  # cliente arrancado desde OTRO proyecto
    )

    async def _roundtrip() -> str:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool("add", {"text": "atlas vive en /home/ronin/proyectos/atlas-core"})
                res = await session.call_tool("recall", {"query": "dónde vive atlas"})
                return res.content[0].text  # type: ignore[union-attr]

    payload = asyncio.run(_roundtrip())
    assert "atlas-core" in payload
