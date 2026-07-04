"""Tests del cierre de primitivos MCP del tronco (Completion + Logging/Progress).

Usan el harness in-memory del SDK (`create_connected_server_and_client_session`)
para ejercer los primitivos como un cliente real. Guardados con importorskip(mcp)."""

from __future__ import annotations

from pathlib import Path

import pytest

_CATALOG = Path(__file__).resolve().parent.parent / "docs" / "design" / "mcp_catalog.yaml"


def _agg():
    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.trunk_aggregator import TrunkAggregator
    from atlas.mcp.trunk_manifest import native_roots

    return TrunkAggregator(
        catalog=load_catalog(_CATALOG),
        roots=native_roots(),
        dispatcher=lambda full_name, args: f"called:{full_name}",
    )


def _server():
    from atlas.mcp.catalog import load_catalog
    from atlas.mcp.skills_store import SkillStore
    from atlas.mcp.trunk_server import build_trunk_server

    store = SkillStore(Path(__file__).resolve().parent.parent / "docs" / "skills")
    return build_trunk_server(_agg(), skill_store=store, catalog=load_catalog(_CATALOG))


def test_completion_on_catalog_template_kind() -> None:
    pytest.importorskip("mcp")
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session as connect
    from mcp.types import ResourceTemplateReference

    async def run() -> list[str]:
        async with connect(_server()) as client:
            result = await client.complete(
                ref=ResourceTemplateReference(
                    type="ref/resource", uri="catalog://item/{kind}/{name}"
                ),
                argument={"name": "kind", "value": "mc"},
            )
            return list(result.completion.values)

    values = asyncio.run(run())
    assert "mcp" in values  # "mc" → kind mcp


def test_completion_on_skill_prompt_names() -> None:
    pytest.importorskip("mcp")
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session as connect
    from mcp.types import PromptReference

    from atlas.mcp.skills_store import SkillStore

    skills = SkillStore(Path(__file__).resolve().parent.parent / "docs" / "skills").list_skills()

    async def run() -> list[str]:
        async with connect(_server()) as client:
            result = await client.complete(
                ref=PromptReference(type="ref/prompt", name=skills[0]),
                argument={"name": "x", "value": skills[0][:3]},
            )
            return list(result.completion.values)

    values = asyncio.run(run())
    assert any(skills[0] == v for v in values)


def test_selfcheck_emits_logs_and_returns_counts() -> None:
    pytest.importorskip("mcp")
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session as connect

    logs: list[str] = []

    async def logging_cb(params) -> None:  # type: ignore[no-untyped-def]
        logs.append(str(params.data))

    async def run() -> dict:
        async with connect(_server(), logging_callback=logging_cb) as client:
            res = await client.call_tool("trunk_selfcheck", {})
            return res.structuredContent or {}

    out = asyncio.run(run())
    assert "by_status" in out and "usable" in out
    # Logging primitive: al menos un mensaje estructurado llegó al cliente.
    assert any("selfcheck" in m for m in logs)


def test_elicitation_confirm() -> None:
    pytest.importorskip("mcp")
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session as connect
    from mcp.types import ElicitResult

    async def elicit_cb(context, params):  # type: ignore[no-untyped-def]
        # El "humano" acepta y confirma.
        return ElicitResult(action="accept", content={"confirmed": True})

    async def run() -> dict:
        async with connect(_server(), elicitation_callback=elicit_cb) as client:
            res = await client.call_tool("trunk_confirm", {"question": "¿seguir?"})
            return res.structuredContent or {}

    out = asyncio.run(run())
    assert out["action"] == "accept" and out["confirmed"] is True


def test_sampling_offload() -> None:
    pytest.importorskip("mcp")
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session as connect
    from mcp.types import CreateMessageResult, TextContent

    async def sampling_cb(context, params):  # type: ignore[no-untyped-def]
        # El modelo del CLIENTE responde (el server no integra modelo).
        return CreateMessageResult(
            role="assistant",
            content=TextContent(type="text", text="respuesta-del-cliente"),
            model="stub-client-model",
            stopReason="endTurn",
        )

    async def run() -> str:
        async with connect(_server(), sampling_callback=sampling_cb) as client:
            res = await client.call_tool("trunk_reason", {"prompt": "2+2?"})
            return (res.structuredContent or {}).get("result", "")

    out = asyncio.run(run())
    assert out == "respuesta-del-cliente"


def test_roots_listing() -> None:
    pytest.importorskip("mcp")
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session as connect
    from mcp.types import ListRootsResult, Root

    async def roots_cb(context):  # type: ignore[no-untyped-def]
        return ListRootsResult(roots=[Root(uri="file:///workspace", name="ws")])

    async def run() -> list[str]:
        async with connect(_server(), list_roots_callback=roots_cb) as client:
            res = await client.call_tool("trunk_list_roots", {})
            sc = res.structuredContent or {}
            return sc.get("result", [])

    out = asyncio.run(run())
    assert any("file:///workspace" in r for r in out)


def test_subscription_tracks_and_pushes_update() -> None:
    pytest.importorskip("mcp")
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session as connect
    from mcp.types import ResourceUpdatedNotification, ServerNotification
    from pydantic import AnyUrl

    received: list[str] = []

    async def message_handler(message) -> None:  # type: ignore[no-untyped-def]
        if isinstance(message, ServerNotification) and isinstance(
            message.root, ResourceUpdatedNotification
        ):
            received.append(str(message.root.params.uri))

    async def run() -> None:
        async with connect(_server(), message_handler=message_handler) as client:
            # El cliente se subscribe al índice del catálogo.
            await client.subscribe_resource(AnyUrl("catalog://manifest"))
            # El server publica un cambio (seam que el watcher/sync invocará).
            await client.call_tool("trunk_notify_catalog_changed", {})
            await asyncio.sleep(0.05)

    asyncio.run(run())
    # El cliente subscrito recibió resources/updated del manifest.
    assert any("catalog://manifest" in u for u in received)
