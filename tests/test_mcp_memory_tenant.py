"""
Tests del wiring multi-tenant del MCP de memoria.

Verifica que `MemoryTrunkRouter` aísla correctamente los tenants (cada uno ve
solo sus propias memorias) y que `build_tenant_memory_server` deriva el tenant
por sesión sin que el cliente lo pase como argumento.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.memory.embeddings import StubEmbedder
from atlas.mcp.memory_trunk import MemoryTrunkRouter


# ---------------------------------------------------------------------------
# a) Router aísla e2e a nivel trunk
# ---------------------------------------------------------------------------


def test_router_isolates_tenants(tmp_path: Path) -> None:
    router = MemoryTrunkRouter(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
    ta = router.for_tenant("tenant-a")
    tb = router.for_tenant("tenant-b")

    ta.add("alpha secret de A", record_id="a1")
    tb.add("beta secret de B", record_id="b1")

    hits_a = ta.recall("secret")
    ids_a = [h.record_id for h in hits_a]
    assert "a1" in ids_a
    assert "b1" not in ids_a

    hits_b = tb.recall("secret")
    ids_b = [h.record_id for h in hits_b]
    assert "b1" in ids_b
    assert "a1" not in ids_b

    # Re-obtener el mismo tenant no rompe el aislamiento
    hits_a2 = router.for_tenant("tenant-a").recall("secret")
    ids_a2 = [h.record_id for h in hits_a2]
    assert "a1" in ids_a2
    assert "b1" not in ids_a2


# ---------------------------------------------------------------------------
# b) for_tenant cachea la instancia
# ---------------------------------------------------------------------------


def test_for_tenant_caches_instance(tmp_path: Path) -> None:
    router = MemoryTrunkRouter(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
    assert router.for_tenant("x") is router.for_tenant("x")


# ---------------------------------------------------------------------------
# c) tenant vacío o whitespace → ValueError
# ---------------------------------------------------------------------------


def test_for_tenant_empty_raises(tmp_path: Path) -> None:
    router = MemoryTrunkRouter(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
    with pytest.raises(ValueError):
        router.for_tenant("")


def test_for_tenant_whitespace_raises(tmp_path: Path) -> None:
    router = MemoryTrunkRouter(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
    with pytest.raises(ValueError):
        router.for_tenant("   ")


# ---------------------------------------------------------------------------
# d) Servidor deriva tenant por sesión (requiere SDK mcp)
# ---------------------------------------------------------------------------


def test_tenant_server_isolates_by_resolver(tmp_path: Path) -> None:
    pytest.importorskip("mcp")
    import asyncio

    from atlas.mcp.memory_server import build_tenant_memory_server

    # Resolver mutable: simula distintas sesiones/clientes
    class Resolver:
        current: str = "client-a"

        def __call__(self) -> str:
            return self.current

    resolver = Resolver()
    router = MemoryTrunkRouter(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
    server = build_tenant_memory_server(router, resolver)

    # Obtener las tools registradas en el servidor
    tools_list = asyncio.run(server.list_tools())
    tool_map = {t.name: t for t in tools_list}
    assert {"recall", "add", "supersede"} <= tool_map.keys()

    # Simular llamada a tool "add" como client-a
    async def _invoke_add(text: str, record_id: str) -> str:
        # call_tool devuelve (content_list, meta_dict); meta_dict["result"] tiene el valor
        result = await server.call_tool("add", {"text": text, "record_id": record_id})
        if isinstance(result, tuple):
            return str(result[1].get("result", ""))
        return str(result)

    async def _invoke_recall(query: str) -> list[str]:
        result = await server.call_tool("recall", {"query": query})
        if isinstance(result, tuple):
            data = result[1].get("result", [])
        else:
            data = result
        return [item["record_id"] for item in data]

    resolver.current = "client-a"
    asyncio.run(_invoke_add("memoria de A", "ma1"))

    resolver.current = "client-b"
    asyncio.run(_invoke_add("memoria de B", "mb1"))

    resolver.current = "client-a"
    ids = asyncio.run(_invoke_recall("memoria"))
    assert "ma1" in ids
    assert "mb1" not in ids


# ---------------------------------------------------------------------------
# e) close() no lanza y cierra los índices
# ---------------------------------------------------------------------------


def test_router_close(tmp_path: Path) -> None:
    router = MemoryTrunkRouter(tmp_path / "m.db", embedder=StubEmbedder(dim=64))
    router.for_tenant("t1").add("algo")
    router.for_tenant("t2").add("algo más")
    router.close()  # no debe lanzar
