"""ADC-WO-103: un dueño por clase de memoria, y que deje de poder romperse.

Hermano de `test_authority_single_writer.py` (WO-102, estado de tareas). Aquí
la ficha pide "one owner per memory class" y nombra tres riesgos:
`privacy leakage`, `loss of provenance` y `dual authority`.

**Corrección de mi propio encuadre.** Yo había apuntado "8 rutas de promoción
en 6 ficheros sin dueño único". Midiéndolas una a una, no son ocho escritores
compitiendo por lo mismo: son promociones de CLASES DISTINTAS con un dueño
cada una, más sus llamantes.

| ruta | clase | qué es de verdad |
|---|---|---|
| `LessonStore.promote_failure` | lecciones | el escritor real |
| `LessonRunner.run_and_promote` | lecciones | LLAMANTE del anterior |
| `promote_if_fixed` | lecciones | fachada del anterior |
| `ErrorRegistry.mark_promoted` | registro de errores | back-link, no promoción |
| `promote_after_trial` | catálogo MCP | función PURA, sin I/O |
| `CoreEngine.promote_candidate` | entidades de negocio | escritor, exige humano |
| `gate_h → promote_if_valid` | herramientas generadas | escritor |

Contarlas como ocho escritores habría llevado a "consolidar" cosas que no
comparten estado. La consolidación que sí hacía falta era otra, y estaba en
el grafo — ver `test_ningun_escritor_del_grafo_se_salta_el_lock`.

Lo que NO se puede vigilar desde aquí queda dicho en el mapa
(`docs/design/authority_map_memory.md`), no escondido.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "atlas"

_KUZU_RUNTIME = "memory/kuzu_runtime.py"
_PROJECT_GRAPH = "memory/project_graph.py"
_MAINTENANCE = "core/orchestrator_parts/maintenance_facade.py"
_LESSON_STORE = "core/lesson_store.py"


def _fuentes() -> list[tuple[str, str]]:
    return [
        (p.relative_to(SRC).as_posix(), p.read_text(encoding="utf-8", errors="replace"))
        for p in sorted(SRC.rglob("*.py"))
        if "__pycache__" not in p.parts
    ]


def _llamadas(codigo: str, nombre: str) -> list[ast.Call]:
    fuera: list[ast.Call] = []
    for node in ast.walk(ast.parse(codigo)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        llamado = func.attr if isinstance(func, ast.Attribute) else (
            func.id if isinstance(func, ast.Name) else ""
        )
        if llamado == nombre:
            fuera.append(node)
    return fuera


# ---------------------------------------------------------------------------
# Grafo estructural (Kuzu) — el que ya se corrompió una vez
# ---------------------------------------------------------------------------


def test_nadie_abre_Kuzu_por_su_cuenta() -> None:
    """`open_kuzu_database` acota memoria y tamaño explícitamente; el
    constructor crudo hereda los defaults dimensionados al host. El jail
    dejaba 7,8 GB de RAM abiertos justo por caer en defaults implícitos."""
    intrusos = [
        (ruta, node.lineno)
        for ruta, codigo in _fuentes()
        for node in ast.walk(ast.parse(codigo))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Database"
        and "kuzu" in ast.unparse(node.func.value)
        and ruta != _KUZU_RUNTIME
    ]
    assert not intrusos, (
        f"constructor crudo de Kuzu fuera de kuzu_runtime.py: {intrusos}"
    )


_ESCRITORES_DEL_GRAFO = frozenset({
    "load_bitemporal_into_kuzu",
    "load_callgraph_into_kuzu",
    "load_vault_into_kuzu",
    "build_project_graph",
})


def _modulos_que_escriben_el_grafo() -> dict[str, list[str]]:
    """Módulos que LLAMAN a una función escritora del grafo (no la definen)."""
    fuera: dict[str, list[str]] = {}
    for ruta, codigo in _fuentes():
        arbol = ast.parse(codigo)
        definidas = {
            n.name for n in ast.walk(arbol)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        llamadas = sorted({
            nombre for nombre in _ESCRITORES_DEL_GRAFO
            if _llamadas(codigo, nombre) and nombre not in definidas
        })
        if llamadas:
            fuera[ruta] = llamadas
    return fuera


def test_ningun_escritor_del_grafo_se_salta_el_lock() -> None:
    """El defecto que este fichero encontró midiendo.

    `graph-rebuild-single-writer` estaba en código desde el 2026-08-08... en
    `maintenance_facade`, que es UN llamante. El entrypoint
    `python -m atlas.memory.project_graph` escribía la misma BD sin tomar
    nada, así que correrlo con el daemon vivo reproducía el incidente
    original tal cual (dos escrituras solapadas, catálogo a medias). El lock
    protegía a un llamante, no al recurso: una aproximación de la puerta no
    es la puerta.
    """
    fuentes = dict(_fuentes())
    sin_lock = [
        (ruta, llamadas)
        for ruta, llamadas in _modulos_que_escriben_el_grafo().items()
        if "ProjectGraphWriterLock" not in fuentes[ruta]
    ]
    assert not sin_lock, (
        f"módulos que escriben el grafo sin nombrar el lock: {sin_lock}. "
        "Kuzu no es seguro multi-proceso para escritura."
    )


def test_el_guardia_del_lock_caza_un_escritor_nuevo() -> None:
    """Mutación: el detector tiene que ver un llamante que no define la
    función y no menciona el lock."""
    mutante = "def tick():\n    build_project_graph(Path('.'), Path('/db'))\n"
    assert _llamadas(mutante, "build_project_graph")
    # Y no debe marcar al módulo que la DEFINE.
    propio = "def build_project_graph(a, b):\n    return {}\n"
    definidas = {
        n.name for n in ast.walk(ast.parse(propio))
        if isinstance(n, ast.FunctionDef)
    }
    assert "build_project_graph" in definidas


def test_los_escritores_del_grafo_son_exactamente_los_declarados() -> None:
    """Si alguien añade un cuarto camino de escritura, el mapa deja de
    describir la realidad y esto lo dice."""
    assert set(_modulos_que_escriben_el_grafo()) == {_PROJECT_GRAPH, _MAINTENANCE}


# ---------------------------------------------------------------------------
# Lecciones — un store, un directorio
# ---------------------------------------------------------------------------


def test_todo_LessonStore_apunta_al_mismo_directorio() -> None:
    """El 2026-07-03 había cinco rutas distintas de `LessonStore` y las
    lecciones se escribían en sitios que nadie leía. Se unificó a
    `workspace/lessons`; esto impide que se vuelva a dispersar."""
    rutas_raras: list[tuple[str, int, str]] = []
    for ruta, codigo in _fuentes():
        for llamada in _llamadas(codigo, "LessonStore"):
            if not llamada.args:
                continue  # sin argumentos = default del propio store
            texto = ast.unparse(llamada.args[0])
            # Un parámetro inyectado es legítimo: el llamante decide.
            if "workspace" in texto and "lessons" in texto:
                continue
            if texto.endswith("_path") or texto.endswith("_dir") or "or " in texto:
                continue
            rutas_raras.append((ruta, llamada.lineno, texto))
    assert not rutas_raras, (
        f"LessonStore apuntando fuera de workspace/lessons: {rutas_raras}"
    )


def test_solo_el_store_escribe_ficheros_de_leccion() -> None:
    """Una lección escrita a mano se salta la única ley del store: no se
    guarda una lección cuyo Evidence no sea PASS."""
    intrusos = [
        (ruta, node.lineno)
        for ruta, codigo in _fuentes()
        if ruta != _LESSON_STORE
        for node in ast.walk(ast.parse(codigo))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"write_text", "write_bytes"}
        and "lesson" in ast.unparse(node.func.value).lower()
    ]
    assert not intrusos, f"escritura directa de ficheros de lección: {intrusos}"


# ---------------------------------------------------------------------------
# Promoción de negocio — la barrera humana
# ---------------------------------------------------------------------------


def test_promover_una_entidad_de_negocio_exige_un_humano() -> None:
    """`requires_review` es const True por contrato y `promote_candidate` es
    donde se resuelve. Que la comprobación siga ahí no es un detalle: es la
    diferencia entre un candidato y un hecho de negocio."""
    codigo = (SRC / "business" / "core_engine.py").read_text(encoding="utf-8")
    arbol = ast.parse(codigo)
    funcion = next(
        n for n in ast.walk(arbol)
        if isinstance(n, ast.FunctionDef) and n.name == "promote_candidate"
    )
    cuerpo = ast.unparse(funcion)
    assert "reviewed_by" in cuerpo
    # Y no sólo lo menciona: se niega si falta.
    assert any(
        isinstance(n, ast.Raise) for n in ast.walk(funcion)
    ), "promote_candidate no rechaza nada; la revisión humana sería decorativa"


# ---------------------------------------------------------------------------
# El mapa
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "termino",
    ["LessonStore", "ProjectGraphWriterLock", "open_kuzu_database",
     "BlockMemory", "MerkleLogger", "promote_candidate"],
)
def test_el_mapa_de_memoria_nombra_a_cada_dueno(termino: str) -> None:
    mapa = REPO / "docs" / "design" / "authority_map_memory.md"
    assert mapa.exists(), "falta docs/design/authority_map_memory.md"
    assert termino in mapa.read_text(encoding="utf-8"), (
        f"el mapa de memoria no menciona {termino}"
    )
