"""t17: la frontera de privacidad del grafo compartible, ahora comprobable.

`docs/design/authority_map_memory.md` declaraba este hueco el 2026-08-11: la
garantía de que ningún dato privado llega al grafo era **por construcción**
(se hace de git+AST), más fuerte que un test mientras la fuente no cambie y
más débil en cuanto cambie, porque nada lo detectaba.

Midiendo para cerrarlo salió una frontera **más limpia y más comprobable** que
la que yo había escrito, y también una corrección: el grafo NO se construye
sólo de git+AST. `ObsidianNote` viene del vault, que son notas escritas por
personas. Lo que hace segura esa ingesta no es su origen: es que **guarda
metadatos y no cuerpo** — `path, title, note_type, community, cohesion, tags`.

El invariante real, entonces, no es "de dónde viene" sino "qué columnas
tiene", y ése sí se comprueba:

    grafo del proyecto   ->  ninguna columna de texto libre
    vector store (OTRA BD) ->  Pattern.text, Failure.description/solution,
                               Evidence.text — aquí SÍ, y es su trabajo

`Symbol` lo deja claro: guarda `content_hash`, no `content`. La huella permite
detectar el cambio sin conservar el contenido.

Este fichero fija esa frontera leyendo los esquemas reales. Añadir una columna
`content STRING` al grafo compartible deja de ser una línea que nadie ve.
"""

from __future__ import annotations

import re

import pytest

from atlas.core.graphs import _SCHEMA as ESQUEMA_BITEMPORAL
from atlas.memory.callgraph_to_kuzu import _SCHEMA as ESQUEMA_CALLGRAPH
from atlas.memory.obsidian_to_kuzu import _SCHEMA as ESQUEMA_VAULT

#: Nombres que delatan texto libre: cuerpo de nota, mensaje, prompt, respuesta.
#: `hash` NO está: una huella no conserva el contenido, lo detecta.
_COLUMNAS_DE_TEXTO_LIBRE = frozenset({
    "content", "text", "body", "message", "prompt", "response", "completion",
    "description", "summary", "snippet", "excerpt", "raw", "payload", "notes",
})

#: Lo que cada tabla del grafo compartible puede tener. Cerrado a propósito:
#: una columna nueva obliga a pasar por aquí y a justificarla.
_COLUMNAS_PERMITIDAS = {
    "FileVersion": {"id", "path", "hash", "commit_sha", "ingested_at", "embedding"},
    "Symbol": {
        "id", "name", "kind", "source_file", "source_location", "content_hash",
        "ingested_at",
    },
    "ObsidianNote": {
        "path", "title", "note_type", "community", "cohesion", "tags",
        "ingested_at",
    },
}


def _tablas(esquema: tuple[str, ...]) -> dict[str, set[str]]:
    """`{tabla: {columnas}}` a partir de las sentencias DDL reales."""
    fuera: dict[str, set[str]] = {}
    for ddl in esquema:
        m = re.search(r"CREATE NODE TABLE (?:IF NOT EXISTS )?(\w+)\s*\((.*)\)", ddl, re.S)
        if not m:
            continue
        nombre, cuerpo = m.group(1), m.group(2)
        columnas: set[str] = set()
        for trozo in cuerpo.split(","):
            trozo = trozo.strip()
            if not trozo or trozo.upper().startswith("PRIMARY KEY"):
                continue
            columnas.add(trozo.split()[0])
        fuera[nombre] = columnas
    return fuera


def _todas() -> dict[str, set[str]]:
    completo: dict[str, set[str]] = {}
    for esquema in (ESQUEMA_BITEMPORAL, ESQUEMA_CALLGRAPH, ESQUEMA_VAULT):
        completo.update(_tablas(esquema))
    return completo


# ---------------------------------------------------------------------------
# El invariante
# ---------------------------------------------------------------------------


def test_el_parser_de_esquemas_encuentra_las_tres_tablas() -> None:
    """Sin esto, un parser que devolviera `{}` haría pasar todo lo de abajo."""
    assert set(_todas()) == {"FileVersion", "Symbol", "ObsidianNote"}


def test_ninguna_tabla_del_grafo_compartible_guarda_texto_libre() -> None:
    intrusas = {
        f"{tabla}.{col}"
        for tabla, cols in _todas().items()
        for col in cols
        if col.lower() in _COLUMNAS_DE_TEXTO_LIBRE
    }
    assert not intrusas, (
        f"columnas de texto libre en el grafo compartible: {sorted(intrusas)}. "
        "Ahí no va contenido: el texto vive en el vector store, que es otra "
        "base de datos (ADC-WO-103, riesgo 'privacy leakage')."
    )


@pytest.mark.parametrize("tabla", sorted(_COLUMNAS_PERMITIDAS))
def test_cada_tabla_tiene_exactamente_las_columnas_declaradas(tabla: str) -> None:
    """Lista cerrada, no denylist: una columna con un nombre inocente
    (`meta`, `extra`, `data`) podría llevar cuerpo igual y la denylist no la
    vería."""
    assert _todas()[tabla] == _COLUMNAS_PERMITIDAS[tabla]


def test_Symbol_guarda_la_HUELLA_del_contenido_y_no_el_contenido() -> None:
    """La distinción que hace posible detectar cambios sin conservar nada."""
    columnas = _todas()["Symbol"]
    assert "content_hash" in columnas
    assert "content" not in columnas


def test_ObsidianNote_guarda_metadatos_y_no_el_cuerpo_de_la_nota() -> None:
    """El vault SON notas escritas por personas — la ingesta más sensible del
    grafo. Lo que la hace segura no es su origen sino qué se queda."""
    columnas = _todas()["ObsidianNote"]
    assert {"path", "title", "tags"} <= columnas
    assert not (columnas & _COLUMNAS_DE_TEXTO_LIBRE)


# ---------------------------------------------------------------------------
# Verificación por mutación del detector
# ---------------------------------------------------------------------------


def test_el_detector_caza_una_columna_de_contenido() -> None:
    mutante = (
        "CREATE NODE TABLE IF NOT EXISTS ObsidianNote("
        "path STRING, title STRING, content STRING, PRIMARY KEY(path))",
    )
    columnas = _tablas(mutante)["ObsidianNote"]
    assert columnas & _COLUMNAS_DE_TEXTO_LIBRE == {"content"}


def test_el_detector_no_confunde_una_huella_con_contenido() -> None:
    mutante = (
        "CREATE NODE TABLE IF NOT EXISTS Symbol("
        "id STRING, content_hash STRING, PRIMARY KEY(id))",
    )
    assert not (_tablas(mutante)["Symbol"] & _COLUMNAS_DE_TEXTO_LIBRE)


def test_el_detector_ve_una_columna_nueva_aunque_se_llame_inocente() -> None:
    """La lista cerrada es lo que cubre el hueco de la denylist."""
    mutante = (
        "CREATE NODE TABLE IF NOT EXISTS Symbol("
        "id STRING, name STRING, kind STRING, source_file STRING, "
        "source_location STRING, content_hash STRING, ingested_at TIMESTAMP, "
        "extra STRING, PRIMARY KEY(id))",
    )
    assert _tablas(mutante)["Symbol"] != _COLUMNAS_PERMITIDAS["Symbol"]


# ---------------------------------------------------------------------------
# La otra mitad: dónde SÍ vive el texto
# ---------------------------------------------------------------------------


def test_el_vector_store_sigue_siendo_una_base_de_datos_DISTINTA() -> None:
    """Si el vector store compartiera BD con el grafo, la separación de arriba
    sería contabilidad y no aislamiento. Son dos aperturas distintas y ningún
    módulo del grafo importa el vector store."""
    import atlas.core.graphs as grafos
    import atlas.memory.callgraph_to_kuzu as callgraph
    import atlas.memory.obsidian_to_kuzu as vault

    for modulo in (grafos, callgraph, vault):
        fuente = (modulo.__doc__ or "") + str(sorted(vars(modulo)))
        assert "KuzuVectorStore" not in fuente, (
            f"{modulo.__name__} conoce el vector store: el texto libre podría "
            "acabar en la misma BD que el grafo compartible"
        )
