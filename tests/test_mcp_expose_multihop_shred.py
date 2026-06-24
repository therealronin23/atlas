"""
Tests TDD: recall_multihop y shred expuestos por MemoryTrunk y el MCP de memoria.

Criterios de aceptación:
  a) MemoryTrunk.recall_multihop: cadena llega a C que recall simple no alcanza.
  b) recall salta shredded: trunk.recall no lanza y no incluye la shredded tras shred.
  c) MemoryTrunk.shred: text_of lanza ShreddedContentError; shred("noexiste") lanza KeyError.
  d) Tools MCP presentes: recall_multihop y shred en list_tools() para ambos builders.
  e) Tool shred e2e: tras invocar la tool shred, recall/text_of no exponen el contenido.
  f) Aislamiento multi-tenant: shred/recall_multihop enrutados por tenant.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from atlas.memory.embeddings import StubEmbedder
from atlas.memory.memory_index import ShreddedContentError, SqliteMemoryIndex
from atlas.mcp.memory_trunk import MemoryTrunk, MemoryTrunkRouter

# ---------------------------------------------------------------------------
# Textos para el grafo A→B→C (idénticos a test_memory_index_multihop.py)
# ---------------------------------------------------------------------------
_TEXT_A = "alpha zeta foxtrot bravo charlie"
_TEXT_B = "bravo charlie delta echo"
_TEXT_C = "delta echo golf hotel india"
_QUERY_A = "alpha zeta foxtrot"


def _trunk(tmp_path: Path, threshold: float = 0.1) -> MemoryTrunk:
    idx = SqliteMemoryIndex(
        tmp_path / "trunk.db",
        embedder=StubEmbedder(dim=64),
        threshold=threshold,
    )
    return MemoryTrunk(idx)


# ---------------------------------------------------------------------------
# (a) recall_multihop encadena hasta C; recall simple no llega
# ---------------------------------------------------------------------------


def test_recall_multihop_reaches_c_that_recall_misses(tmp_path: Path) -> None:
    trunk = _trunk(tmp_path)
    trunk.add(_TEXT_A, record_id="mem_a")
    trunk.add(_TEXT_B, record_id="mem_b")
    trunk.add(_TEXT_C, record_id="mem_c")

    chain = trunk.recall_multihop(_QUERY_A, hops=3)
    chain_ids = [h.record_id for h in chain]
    assert "mem_c" in chain_ids, f"multihop debe alcanzar mem_c; cadena: {chain_ids}"

    # recall simple (k=1) solo devuelve el más cercano, que NO es mem_c
    single_top = trunk.recall(_QUERY_A, k=1)
    assert single_top, "debe haber al menos un resultado"
    assert single_top[0].record_id != "mem_c", (
        f"recall(k=1) no debe devolver mem_c como top; got: {single_top[0].record_id}"
    )


def test_recall_multihop_hits_have_text_score_and_hash(tmp_path: Path) -> None:
    trunk = _trunk(tmp_path)
    trunk.add(_TEXT_A, record_id="mem_a")
    trunk.add(_TEXT_B, record_id="mem_b")
    trunk.add(_TEXT_C, record_id="mem_c")

    chain = trunk.recall_multihop(_QUERY_A, hops=3)
    assert len(chain) >= 1
    for hit in chain:
        assert hit.text
        assert 0.0 <= hit.score <= 1.0
        assert isinstance(hit.matched, bool)


# ---------------------------------------------------------------------------
# (b) recall salta shredded (fix del bug latente)
# ---------------------------------------------------------------------------


def test_recall_skips_shredded_no_exception(tmp_path: Path) -> None:
    trunk = _trunk(tmp_path)
    trunk.add("memoria sana", record_id="sana")
    trunk.add("memoria shredded delta zeta", record_id="shredded")

    trunk.shred("shredded")

    # Antes del fix lanzaría ShreddedContentError
    hits = trunk.recall("memoria")
    ids = [h.record_id for h in hits]
    assert "shredded" not in ids
    assert "sana" in ids


# ---------------------------------------------------------------------------
# (c) MemoryTrunk.shred: semántica correcta
# ---------------------------------------------------------------------------


def test_shred_makes_text_of_raise(tmp_path: Path) -> None:
    idx = SqliteMemoryIndex(
        tmp_path / "s.db", embedder=StubEmbedder(dim=64), threshold=0.1
    )
    trunk = MemoryTrunk(idx)
    trunk.add("datos sensibles", record_id="sec1")

    trunk.shred("sec1")

    with pytest.raises(ShreddedContentError):
        idx.text_of("sec1")


def test_shred_nonexistent_raises_key_error(tmp_path: Path) -> None:
    trunk = _trunk(tmp_path)
    with pytest.raises(KeyError):
        trunk.shred("noexiste")


# ---------------------------------------------------------------------------
# (d) Tools MCP presentes en ambos builders
# ---------------------------------------------------------------------------


def test_build_memory_server_has_recall_multihop_and_shred(tmp_path: Path) -> None:
    pytest.importorskip("mcp")
    from atlas.mcp.memory_server import build_memory_server

    server = build_memory_server(_trunk(tmp_path))
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert "recall_multihop" in names
    assert "shred" in names


def test_build_tenant_memory_server_has_recall_multihop_and_shred(
    tmp_path: Path,
) -> None:
    pytest.importorskip("mcp")
    from atlas.mcp.memory_server import build_tenant_memory_server

    router = MemoryTrunkRouter(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
    server = build_tenant_memory_server(router, lambda: "t1")
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert "recall_multihop" in names
    assert "shred" in names


# ---------------------------------------------------------------------------
# (e) Tool shred e2e: tras invocar la tool, recall y text_of no exponen contenido
# ---------------------------------------------------------------------------


def test_tool_shred_e2e(tmp_path: Path) -> None:
    pytest.importorskip("mcp")
    from atlas.mcp.memory_server import build_memory_server

    idx = SqliteMemoryIndex(
        tmp_path / "e2e.db", embedder=StubEmbedder(dim=64), threshold=0.1
    )
    trunk = MemoryTrunk(idx)
    trunk.add("secreto borrable", record_id="sec_e2e")

    server = build_memory_server(trunk)

    async def _run() -> None:
        # shred via tool
        result = await server.call_tool("shred", {"record_id": "sec_e2e"})
        if isinstance(result, tuple):
            ret = result[1].get("result", "")
        else:
            ret = result
        assert "sec_e2e" in str(ret)

        # recall no expone el contenido
        recall_result = await server.call_tool("recall", {"query": "secreto"})
        if isinstance(recall_result, tuple):
            data = recall_result[1].get("result", [])
        else:
            data = recall_result
        ids = [item["record_id"] for item in data]
        assert "sec_e2e" not in ids

    asyncio.run(_run())

    # text_of también lanza
    with pytest.raises(ShreddedContentError):
        idx.text_of("sec_e2e")


# ---------------------------------------------------------------------------
# (f) Aislamiento multi-tenant: shred/recall_multihop enrutados por tenant
# ---------------------------------------------------------------------------


def test_tenant_shred_isolation(tmp_path: Path) -> None:
    pytest.importorskip("mcp")
    from atlas.mcp.memory_server import build_tenant_memory_server

    class Resolver:
        current: str = "ta"

        def __call__(self) -> str:
            return self.current

    resolver = Resolver()
    router = MemoryTrunkRouter(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
    server = build_tenant_memory_server(router, resolver)

    # Añadir memoria en ambos tenants directamente
    resolver.current = "ta"
    ta = router.for_tenant("ta")
    ta.add("dato privado de A", record_id="a_priv")

    resolver.current = "tb"
    tb = router.for_tenant("tb")
    tb.add("dato de B bravo", record_id="b_pub")

    # Shred como tenant A: no afecta a B
    resolver.current = "ta"

    async def _shred_a() -> None:
        await server.call_tool("shred", {"record_id": "a_priv"})

    asyncio.run(_shred_a())

    # B sigue teniendo su memoria
    hits_b = tb.recall("dato bravo")
    ids_b = [h.record_id for h in hits_b]
    assert "b_pub" in ids_b

    # A ya no ve a_priv en recall
    hits_a = ta.recall("dato privado")
    ids_a = [h.record_id for h in hits_a]
    assert "a_priv" not in ids_a


def test_tenant_recall_multihop_isolation(tmp_path: Path) -> None:
    pytest.importorskip("mcp")
    from atlas.mcp.memory_server import build_tenant_memory_server

    class Resolver:
        current: str = "ta"

        def __call__(self) -> str:
            return self.current

    resolver = Resolver()
    router = MemoryTrunkRouter(
        tmp_path / "m.db", embedder=StubEmbedder(dim=64), threshold=0.1
    )
    server = build_tenant_memory_server(router, resolver)

    # Añadir cadena A→B→C solo en tenant ta
    resolver.current = "ta"
    ta = router.for_tenant("ta")
    ta.add(_TEXT_A, record_id="ta_a")
    ta.add(_TEXT_B, record_id="ta_b")
    ta.add(_TEXT_C, record_id="ta_c")

    # tenant tb no tiene nada con esas palabras
    resolver.current = "tb"
    tb = router.for_tenant("tb")
    tb.add("completamente diferente xyzzy", record_id="tb_x")

    # recall_multihop como ta debe alcanzar ta_c
    resolver.current = "ta"

    async def _multihop_ta() -> list[str]:
        result = await server.call_tool(
            "recall_multihop", {"query": _QUERY_A, "hops": 3}
        )
        if isinstance(result, tuple):
            data = result[1].get("result", [])
        else:
            data = result
        return [item["record_id"] for item in data]

    ids_ta = asyncio.run(_multihop_ta())
    assert "ta_c" in ids_ta

    # recall_multihop como tb no debe ver ta_c
    resolver.current = "tb"

    async def _multihop_tb() -> list[str]:
        result = await server.call_tool(
            "recall_multihop", {"query": _QUERY_A, "hops": 3}
        )
        if isinstance(result, tuple):
            data = result[1].get("result", [])
        else:
            data = result
        return [item["record_id"] for item in data]

    ids_tb = asyncio.run(_multihop_tb())
    assert "ta_c" not in ids_tb
