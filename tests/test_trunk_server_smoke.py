"""F5.5 (plan toasty-hatching-pillow) — smoke end-to-end del PROCESO COMPUESTO.

Lanza ``python -m atlas.mcp.trunk_server <save_dir> <repo_root>`` como
subproceso stdio REAL (no el harness in-memory), hace initialize + tools/list
y cierra limpio. Mismo patrón subprocess-stdio que el roundtrip de
``test_mcp_memory_trunk.py`` (stdio_client del SDK), aplicado a serve().

Las aserciones sobre tools son de SUBCONJUNTO deliberadamente: el manifest
del tronco puede crecer en paralelo (nuevas tools/raíces) sin romper este
smoke — JAMÁS igualdad de set.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Tools nativas de la fachada del tronco (build_trunk_server) que SIEMPRE
# deben estar. Subconjunto mínimo estable; no listar aquí tools de raíces
# (graph_*, recall…) — esas no se exponen directo, van vía trunk_invoke.
_NATIVE_TRUNK_TOOLS = {
    "trunk_sectors",
    "trunk_subsectors",
    "trunk_tools",
    "trunk_invoke",
    "trunk_invoke_readonly",
    "trunk_kinds",
    "trunk_health",
    "trunk_catalog",
    "trunk_find",
    "trunk_recommend_stack",
    "trunk_prepare",
    "list_skills",
    "get_skill",
}


def test_trunk_server_stdio_initialize_tools_list_clean_close(tmp_path: Path) -> None:
    import asyncio

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PYTHONPATH": str(_REPO_ROOT / "src"),
        # Hermético: sin adoptados reales de esta máquina (F5.4 es fail-open
        # con fichero inexistente) y sin hijos extra no deterministas.
        "ATLAS_MCP_SERVERS": str(tmp_path / "no-existe.json"),
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m", "atlas.mcp.trunk_server",
            str(tmp_path / "save"),  # save_dir virgen (memoria/kb en tmp)
            str(_REPO_ROOT),         # repo real: catálogo/skills de verdad
        ],
        env=env,
        cwd=str(tmp_path),  # otro cwd: el tronco no depende del cwd
    )

    async def _smoke() -> tuple[str, set[str]]:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                tools = await session.list_tools()
                return init.serverInfo.name, {t.name for t in tools.tools}
        # Al salir de los context managers el subproceso se termina (cierre
        # limpio); si colgara, el wait_for de abajo lo convierte en fallo.

    server_name, names = asyncio.run(asyncio.wait_for(_smoke(), timeout=120))
    assert server_name == "atlas-trunk"
    missing = _NATIVE_TRUNK_TOOLS - names
    assert not missing, f"tools nativas ausentes del tronco compuesto: {missing}"
