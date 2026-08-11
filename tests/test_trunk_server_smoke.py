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


def test_trunk_server_stdio_INVOCA_tools_no_solo_las_lista(tmp_path: Path) -> None:
    """El hueco que dejaba el smoke de arriba: `initialize` + `tools/list` prueba
    que el decorador registró algo, no que el cuerpo se ejecute.

    Es la misma frontera que esta semana escondió un `TypeError` garantizado en
    `engineering_trunk` (firma al revés detrás de una tool que nadie llamaba), y
    la que en la CLI se probaba con `--help`. Y aquí cubre además lo único que
    no se puede alcanzar en proceso: `serve()`, que son 130 líneas donde el
    servidor se CONSTRUYE —catálogo, taxonomía, raíces perezosas— antes de
    servir. Medido el 2026-08-11: era el bloque 514-643, el mayor sin ejecutar.

    Se invocan sólo tools de LECTURA y sin spawnear terceros: `trunk_sectors`
    (índice nativo), `trunk_kinds` (cuenta del catálogo) y `trunk_health`, que
    su propio docstring promete "sin efectos: no spawnea ni instala".
    """
    import asyncio

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PYTHONPATH": str(_REPO_ROOT / "src"),
        "ATLAS_MCP_SERVERS": str(tmp_path / "no-existe.json"),
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m", "atlas.mcp.trunk_server",
            str(tmp_path / "save"),
            str(_REPO_ROOT),
        ],
        env=env,
        cwd=str(tmp_path),
    )

    async def _invocar() -> dict[str, object]:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                salidas: dict[str, object] = {}
                for nombre in ("trunk_sectors", "trunk_kinds", "trunk_health"):
                    resultado = await session.call_tool(nombre, {})
                    salidas[nombre] = resultado
                return salidas

    salidas = asyncio.run(asyncio.wait_for(_invocar(), timeout=180))

    for nombre, resultado in salidas.items():
        # `isError` es como el protocolo reporta un fallo del cuerpo; sin
        # comprobarlo, una tool que revienta pasaría por invocada.
        assert getattr(resultado, "isError", False) is False, (
            f"{nombre} devolvió error por el transporte real: {resultado}"
        )
        assert resultado.content, f"{nombre} no devolvió contenido"
