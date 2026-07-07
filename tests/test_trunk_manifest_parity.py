"""Guard: native_roots() tool lists must match each root server's exposed tools."""

from __future__ import annotations

import importlib
import inspect
import re

import pytest

from atlas.mcp.trunk_manifest import native_roots


def _tool_names_from_source(module_name: str) -> set[str]:
    mod = importlib.import_module(module_name)
    source = inspect.getsource(mod)
    return {m.group(1) for m in re.finditer(r"@server\.tool\(\)\s*\n\s*def\s+(\w+)\s*\(", source)}


@pytest.mark.parametrize(
    ("root_name", "module"),
    [
        ("atlas-memory", "atlas.mcp.memory_server"),
        ("atlas-operating", "atlas.mcp.operating_server"),
        ("atlas-knowledge", "atlas.mcp.knowledge_server"),
    ],
)
def test_native_roots_tools_match_server_module(root_name: str, module: str) -> None:
    manifest_tools = next(r.tools for r in native_roots() if r.name == root_name)
    server_tools = _tool_names_from_source(module)
    assert set(manifest_tools) == server_tools, (
        f"{root_name}: manifest={set(manifest_tools)} server={server_tools}"
    )


def test_memory_manifest_includes_multihop_and_shred() -> None:
    mem = next(r for r in native_roots() if r.name == "atlas-memory")
    assert "recall_multihop" in mem.tools
    assert "shred" in mem.tools
