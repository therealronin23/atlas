"""Los shells MCP se INVOCAN, no sólo se listan.

`test_trunk_server_smoke.py` lanza el proceso stdio real y hace `initialize` +
`tools/list`… y no llama a ninguna tool. Es el mismo hueco que `--help` frente a
ejecutar el comando, y hoy ese hueco ya costó un defecto en la CLI.

Aquí no es una hipótesis. Medido el 2026-08-10 con `coverage` sobre los catorce
ficheros de test del tronco:

    engineering_server.py     25 sentencias    0%   <- cero, 3 tools
    graph_server.py          122 sentencias    9%   <- 111 sin ejecutar, 11 tools

Los `EngineeringTrunk`/`project_graph` de debajo SÍ están probados. Lo que no lo
estaba es la **frontera**: el shell que traduce trunk → MCP. Y ahí es justo
donde vivió el defecto real de esta semana — `engineering_trunk.generate_hypotheses`
llamaba a `history_hypothesis(module, repo_root=...)` cuando la firma es
`(repo_root, path)`: dos `TypeError` garantizados detrás de una tool MCP que
ningún test tocaba.

`graph_server` pesa más de lo que dice su porcentaje: `AGENTS.md` ordena a cada
sesión consultar el grafo ANTES de leer ficheros (`graph_importers`,
`graph_blast_radius`, `graph_churn`, `graph_overview`). Si esas tools están
rotas, la primera instrucción del manual apunta a algo que no responde.

Qué se fija y qué NO: que cada tool de lectura se puede invocar y devuelve sin
traceback. **No** que devuelva datos — un grafo de prueba vacío contesta vacío y
eso es correcto. Confundir "responde" con "responde algo" convertiría esto en un
test frágil que se rompe por el contenido de una BD.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

from atlas.mcp.engineering_trunk import EngineeringTrunk  # noqa: E402
from atlas.mcp.engineering_server import build_engineering_server  # noqa: E402

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e.com",
    "PATH": "/usr/bin:/bin",
}


def _invocar(server: Any, nombre: str, argumentos: dict[str, Any]) -> Any:
    """Llama a la tool por el camino REAL de FastMCP.

    `server.call_tool()` es lo que ejecuta el runtime MCP ante un `tools/call`:
    valida los argumentos contra el esquema derivado de la firma y despacha. Ir
    por aquí en vez de llamar a la función Python de dentro es lo que hace que
    este fichero cubra la frontera y no otra vez el trunk.
    """
    return asyncio.run(server.call_tool(nombre, argumentos))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Repo git mínimo con un fichero bajo `src/atlas/` que tiene historia."""
    env = {**_GIT_ENV, "HOME": str(tmp_path)}

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, env=env, check=True,
                       capture_output=True)

    destino = tmp_path / "src" / "atlas" / "core"
    destino.mkdir(parents=True)
    (destino / "widget.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_widget.py").write_text(
        "def test_v():\n    assert True\n", encoding="utf-8"
    )
    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "feat: widget")
    return tmp_path


@pytest.fixture
def engineering(repo: Path, tmp_path: Path) -> Any:
    return build_engineering_server(
        EngineeringTrunk(repo, graph_db_path=tmp_path / "no-existe.kuzu")
    )


# ---------------------------------------------------------------------------
# engineering_server — 0% de cobertura antes de este fichero
# ---------------------------------------------------------------------------


def test_el_shell_de_ingenieria_expone_sus_tres_tools(engineering: Any) -> None:
    nombres = {t.name for t in asyncio.run(engineering.list_tools())}

    assert nombres == {
        "engineering_read_findings",
        "engineering_generate_hypotheses",
        "engineering_impacted_tests",
    }


def test_read_findings_se_puede_invocar(engineering: Any) -> None:
    _invocar(engineering, "engineering_read_findings", {})


def test_generate_hypotheses_se_puede_invocar(engineering: Any) -> None:
    """El defecto real de la semana: `TypeError` garantizado en la primera línea
    útil, detrás de esta tool, invisible porque nadie la llamaba."""
    _invocar(
        engineering,
        "engineering_generate_hypotheses",
        {"path": "src/atlas/core/widget.py"},
    )


def test_impacted_tests_se_puede_invocar(engineering: Any) -> None:
    _invocar(
        engineering,
        "engineering_impacted_tests",
        {"changed_files": ["src/atlas/core/widget.py"]},
    )


def test_el_esquema_rechaza_los_argumentos_equivocados(engineering: Any) -> None:
    """La validación de FastMCP es parte de la frontera: una firma mal declarada
    en el shell se ve AQUÍ, no en el trunk."""
    with pytest.raises(Exception):
        _invocar(engineering, "engineering_generate_hypotheses", {"module": "x"})


def test_una_ruta_inexistente_no_tumba_la_tool(engineering: Any) -> None:
    """Un cliente MCP manda lo que quiere. Que la tool devuelva vacío o un error
    de dominio es aceptable; que reviente el servidor, no."""
    _invocar(
        engineering,
        "engineering_generate_hypotheses",
        {"path": "src/atlas/no/existe.py"},
    )


# ---------------------------------------------------------------------------
# graph_server — 9%, y es la primera herramienta que AGENTS.md manda usar
# ---------------------------------------------------------------------------

kuzu = pytest.importorskip("kuzu", reason="el shell del grafo necesita kuzu")

from atlas.memory.kuzu_runtime import open_kuzu_database  # noqa: E402


def _head(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, env={**_GIT_ENV, "HOME": str(repo)},
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def _construir_grafo(repo: Path, db_path: Path, *, poblado: bool) -> None:
    """Kuzu real con el esquema real (`graphs._SCHEMA` y los de call-graph y
    Obsidian). Copiar el esquema a mano aquí sería inventarse otro grafo."""
    from atlas.core.graphs import _SCHEMA as ESQUEMA_FICHEROS
    from atlas.memory.callgraph_to_kuzu import _SCHEMA as ESQUEMA_SIMBOLOS
    from atlas.memory.obsidian_to_kuzu import _SCHEMA as ESQUEMA_NOTAS

    # Siempre por `open_kuzu_database`: el constructor crudo de Kuzu pide el
    # mmap de 8 TiB por defecto, y `test_kuzu_database_construction_is_centralized`
    # lo prohíbe en todo el árbol. Me pilló al primer intento, y luego otra vez
    # por nombrarlo literalmente en este comentario —el guard escanea el fichero
    # entero, por eso él mismo parte la cadena—. La regla existe porque esta
    # máquina ya se cayó una vez por agotamiento de memoria.
    db = open_kuzu_database(db_path)
    conn = kuzu.Connection(db)
    for ddl in (*ESQUEMA_FICHEROS, *ESQUEMA_SIMBOLOS, *ESQUEMA_NOTAS):
        conn.execute(ddl)
    if poblado:
        sha = _head(repo)
        for ruta in ("src/atlas/core/widget.py", "src/atlas/core/otro.py"):
            conn.execute(
                "CREATE (:FileVersion {id: $id, path: $p, hash: 'h', "
                "commit_sha: $sha, ingested_at: current_timestamp()})",
                parameters={"id": f"{ruta}@{sha}", "p": ruta, "sha": sha},
            )
        conn.execute(
            "MATCH (a:FileVersion), (b:FileVersion) "
            "WHERE a.path = 'src/atlas/core/otro.py' "
            "AND b.path = 'src/atlas/core/widget.py' "
            "CREATE (a)-[:IMPORTS {commit_sha: $sha}]->(b)",
            parameters={"sha": sha},
        )
    conn.close()
    del db


@pytest.fixture
def grafo(repo: Path, tmp_path: Path) -> Any:
    """Servidor sobre un Kuzu real y POBLADO con el HEAD del repo de prueba.

    Poblado, no vacío: con el grafo vacío las tools de dependencias se niegan a
    contestar a propósito (ver el test del fail-closed más abajo), así que un
    grafo vacío dejaría sin ejecutar justo el código que hay que cubrir. Los
    datos son dos ficheros y un IMPORTS — lo mínimo para que las queries tengan
    algo que recorrer, y nada que dependa de la máquina.
    """
    from atlas.mcp.graph_server import build_graph_server

    db_path = tmp_path / "grafo.kuzu"
    _construir_grafo(repo, db_path, poblado=True)
    return build_graph_server(db_path, repo_root=repo)


_TOOLS_DEL_GRAFO: tuple[tuple[str, dict[str, Any]], ...] = (
    ("graph_overview", {}),
    ("graph_importers", {"module": "atlas.core.widget"}),
    ("graph_blast_radius", {"module": "atlas.core.widget"}),
    ("graph_lineage", {"module": "atlas.core.widget"}),
    ("graph_churn", {}),
    ("graph_imports_of", {"module": "atlas.core.widget"}),
    ("graph_note_neighborhood", {"note_stem": "OSM-000_membrana"}),
    ("graph_communities", {}),
    ("graph_semantic_neighbors", {"note_stem": "OSM-000_membrana"}),
    ("graph_callers", {"symbol": "build_graph_server"}),
    ("graph_callees", {"symbol": "build_graph_server"}),
)


def test_el_shell_del_grafo_expone_las_once_tools(grafo: Any) -> None:
    nombres = {t.name for t in asyncio.run(grafo.list_tools())}

    assert nombres == {n for n, _ in _TOOLS_DEL_GRAFO}, sorted(nombres)


@pytest.mark.parametrize("nombre,argumentos", _TOOLS_DEL_GRAFO, ids=lambda x: x if isinstance(x, str) else "")
def test_cada_tool_del_grafo_responde(
    grafo: Any, nombre: str, argumentos: dict[str, Any]
) -> None:
    """Once tools que ningún test invocaba, y son las que `AGENTS.md` manda usar
    antes de leer un solo fichero."""
    _invocar(grafo, nombre, argumentos)


def test_con_el_grafo_vacio_las_tools_de_dependencias_se_NIEGAN(
    repo: Path, tmp_path: Path
) -> None:
    """Descubierto escribiendo este fichero, y es una virtud del diseño que
    conviene dejar fijada: con el grafo vacío, `graph_importers` y compañía no
    devuelven una lista vacía — **lanzan**, diciendo `freshness is EMPTY`.

    Es lo correcto. Contestar "nadie importa este módulo" desde un grafo sin
    filas sería una mentira con formato de respuesta, y quien pregunta radio de
    impacto está a punto de tocar código. Un fallo ruidoso es infinitamente
    mejor que un cero que parece un dato.
    """
    from atlas.mcp.graph_server import build_graph_server

    db_path = tmp_path / "vacio.kuzu"
    _construir_grafo(repo, db_path, poblado=False)
    servidor = build_graph_server(db_path, repo_root=repo)

    for nombre in ("graph_importers", "graph_blast_radius", "graph_imports_of"):
        with pytest.raises(Exception, match="EMPTY"):
            _invocar(servidor, nombre, {"module": "atlas.core.widget"})


def test_el_grafo_no_filtra_la_ruta_de_la_maquina(grafo: Any, tmp_path: Path) -> None:
    """El servidor se construye con `db_path` explícito; heredar
    `DEFAULT_GRAPH_DB` haría que un test tocase el grafo REAL del operador — que
    es exactamente el accidente que corrompió el grafo esta semana."""
    from atlas.memory.project_graph import DEFAULT_GRAPH_DB

    resultado = _invocar(grafo, "graph_overview", {})

    assert str(DEFAULT_GRAPH_DB) not in repr(resultado)
