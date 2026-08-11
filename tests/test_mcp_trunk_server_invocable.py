"""`trunk_server` invocado de verdad — cierra t12.

Último shell del tronco. Medido con `coverage` el 2026-08-11:

    trunk_server.py   273 sentencias   87 sin ejecutar   68%
    sin cubrir: 267, 272, 277, 284, 290-291, 310, 317, 329-337, 348,
                368-371, 390, 395, 514-643, 647-649

Dos huecos de naturaleza distinta, y este fichero ataca el primero:

1. **Los cuerpos de las tools dentro de `build_trunk_server`** (~30 sentencias
   sueltas): registrados por el decorador, nunca ejecutados. Es la misma
   frontera que cerró `engineering` (0→72%), `graph` (9→79%), `knowledge`
   (65→82%) y `operating` (67→79%), y donde vivió el defecto real de esta
   semana (`engineering_trunk` llamando a `history_hypothesis` con la firma al
   revés: dos `TypeError` garantizados detrás de una tool que nadie tocaba).
2. `serve()` (514-643, 130 líneas seguidas): la entrada stdio, que además
   CONSTRUYE el servidor entero. Eso no se cubre en proceso — necesita el
   subproceso real, y `test_trunk_server_smoke.py` hoy hace `initialize` +
   `tools/list` sin invocar nada.

Lo que se fija aquí y no estaba fijado en ninguna parte:

- **`trunk_invoke_readonly` es fail-closed.** Rechaza cualquier tool no
  declarada de sólo lectura; para mutar hay que pasar por `trunk_invoke`, que
  atraviesa HITL en el host. Es una propiedad de seguridad y no tenía prueba.
- **La superficie del servidor CAMBIA según cómo se construya.** `taxonomy`,
  `catalog` y sus combinaciones registran tools distintas. Un servidor sin
  catálogo no expone `trunk_find` — y nadie lo comprobaba.
- **Un fallo del aggregator se PROPAGA** en vez de convertirse en contenido.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

pytest.importorskip("mcp")

from atlas.mcp.trunk_server import build_trunk_server  # noqa: E402


def _invocar(server: Any, nombre: str, argumentos: dict[str, Any]) -> Any:
    """El camino REAL de FastMCP ante un `tools/call`: valida los argumentos
    contra el esquema derivado de la firma y ejecuta el cuerpo. Llamar a la
    función de Python a mano se saltaría esa validación."""
    return asyncio.run(server.call_tool(nombre, argumentos))


def _tools(server: Any) -> set[str]:
    return {t.name for t in asyncio.run(server.list_tools())}


class _Agg:
    """Doble del `TrunkAggregator` con las cuatro llamadas que usa el shell."""

    def __init__(self, *, revienta: bool = False) -> None:
        self.revienta = revienta
        self.llamadas: list[tuple[str, tuple[Any, ...]]] = []

    def _anotar(self, nombre: str, *args: Any) -> Any:
        self.llamadas.append((nombre, args))
        if self.revienta:
            raise RuntimeError(f"{nombre} falló a propósito")
        return [{"id": "x"}]

    def sectors(self) -> list[dict[str, Any]]:
        return self._anotar("sectors")

    def tools_in(self, sector: str, subsector: str | None = None) -> list[dict[str, Any]]:
        return self._anotar("tools_in", sector, subsector)

    def invoke(self, tool: str, args: dict[str, Any]) -> Any:
        return self._anotar("invoke", tool, args)

    def invoke_readonly(self, tool: str, args: dict[str, Any]) -> Any:
        return self._anotar("invoke_readonly", tool, args)


def _taxonomia(tmp: Any) -> dict[str, Any]:
    """Se construye con `load_taxonomy`, la MISMA función que usa producción,
    no a mano.

    Escribirla a mano costó tres fallos: `find`, `recommend_stack` y `prepare`
    esperan una clave `aliases` en sector y subsector que el normalizador
    rellena y mi diccionario no tenía. Un fixture hecho a mano puede desviarse
    de la forma real sin que nada avise; pasando por el cargador, no.
    """
    from atlas.mcp.catalog import load_taxonomy

    ruta = tmp / "taxonomy.yaml"
    ruta.write_text(
        """
sectors:
  programacion:
    label: Programación
    desc: Escribir y revisar código
    aliases: [code, dev]
    subsectors:
      edicion:
        label: Edición
        aliases: [editor]
      vcs:
        label: Control de versiones
        aliases: [git]
""".lstrip(),
        encoding="utf-8",
    )
    return load_taxonomy(ruta)


# ---------------------------------------------------------------------------
# 1. Las cuatro tools que existen SIEMPRE
# ---------------------------------------------------------------------------


@pytest.fixture
def basico():
    agg = _Agg()
    return build_trunk_server(agg), agg  # type: ignore[arg-type]


def test_el_nucleo_esta_registrado_sin_catalogo_ni_taxonomia(basico) -> None:
    """Siete, no cuatro. Las tres últimas las registra `trunk_capabilities` y
    son los **client-features** del protocolo, que yo daba por ausentes hasta
    que este test me lo dijo:

        trunk_confirm      ELICITATION — el hook nativo de HITL
        trunk_reason       SAMPLING    — completion contra el modelo del CLIENTE
        trunk_list_roots   ROOTS       — acceso acotado

    O sea, de los seis primitivos MCP el tronco usa bastantes más de los "dos o
    tres" que la nota heredada afirmaba. Están al 90% de cobertura.
    """
    servidor, _ = basico

    assert _tools(servidor) == {
        "trunk_sectors", "trunk_tools", "trunk_invoke", "trunk_invoke_readonly",
        "trunk_confirm", "trunk_reason", "trunk_list_roots",
    }


@pytest.mark.parametrize(
    "tool,argumentos,metodo",
    [
        ("trunk_sectors", {}, "sectors"),
        ("trunk_tools", {"sector": "programacion"}, "tools_in"),
        ("trunk_invoke", {"tool": "algo"}, "invoke"),
        ("trunk_invoke_readonly", {"tool": "algo"}, "invoke_readonly"),
    ],
)
def test_cada_tool_del_nucleo_llega_al_aggregator(
    basico, tool: str, argumentos: dict[str, Any], metodo: str
) -> None:
    servidor, agg = basico

    _invocar(servidor, tool, argumentos)

    assert [n for n, _ in agg.llamadas] == [metodo]


def test_args_ausentes_llegan_como_diccionario_vacio_no_como_None(basico) -> None:
    """El shell hace `args or {}`. Si no lo hiciera, el aggregator recibiría
    `None` y fallaría lejos de aquí, con un traceback que no señala la causa."""
    servidor, agg = basico

    _invocar(servidor, "trunk_invoke", {"tool": "algo"})

    _, args = agg.llamadas[-1]
    assert args == ("algo", {})


def test_el_subsector_opcional_llega_como_None_cuando_no_se_pasa(basico) -> None:
    servidor, agg = basico

    _invocar(servidor, "trunk_tools", {"sector": "programacion"})

    assert agg.llamadas[-1][1] == ("programacion", None)


# ---------------------------------------------------------------------------
# 2. La separación readonly / invoke, que es de SEGURIDAD
# ---------------------------------------------------------------------------


def test_readonly_e_invoke_van_por_caminos_DISTINTOS_del_aggregator(basico) -> None:
    """`invoke_readonly` es fail-closed en el aggregator: rechaza toda tool no
    declarada de sólo lectura, y para mutar hay que pasar por `trunk_invoke`,
    que atraviesa HITL en el host. Si el shell enrutara las dos al mismo sitio,
    esa distinción desaparecería sin que nada lo notase."""
    servidor, agg = basico

    _invocar(servidor, "trunk_invoke", {"tool": "t"})
    _invocar(servidor, "trunk_invoke_readonly", {"tool": "t"})

    assert [n for n, _ in agg.llamadas] == ["invoke", "invoke_readonly"]


def test_un_fallo_del_aggregator_se_propaga_no_se_disfraza(basico) -> None:
    """Devolver lista vacía o un texto de relleno convertiría una avería en
    contenido — la familia de defecto que esta auditoría lleva una semana
    arrancando."""
    servidor = build_trunk_server(_Agg(revienta=True))  # type: ignore[arg-type]

    with pytest.raises(Exception):
        _invocar(servidor, "trunk_sectors", {})


# ---------------------------------------------------------------------------
# 3. La superficie CAMBIA según cómo se construya
# ---------------------------------------------------------------------------


def test_sin_taxonomia_no_hay_trunk_subsectors(basico) -> None:
    servidor, _ = basico

    assert "trunk_subsectors" not in _tools(servidor)


def test_con_taxonomia_aparece_trunk_subsectors_y_devuelve_el_mapa_fino(tmp_path) -> None:
    servidor = build_trunk_server(_Agg(), taxonomy=_taxonomia(tmp_path))  # type: ignore[arg-type]

    assert "trunk_subsectors" in _tools(servidor)
    _invocar(servidor, "trunk_subsectors", {"sector": "programacion"})


def test_un_sector_que_no_existe_devuelve_vacio_sin_reventar(tmp_path) -> None:
    """`(taxonomy.get(sector) or {}).get(...)`: el `or {}` está para esto."""
    servidor = build_trunk_server(_Agg(), taxonomy=_taxonomia(tmp_path))  # type: ignore[arg-type]

    _invocar(servidor, "trunk_subsectors", {"sector": "no_existe"})


def test_sin_catalogo_no_se_exponen_las_tools_de_catalogo(basico) -> None:
    """Un servidor construido sin catálogo NO ofrece `trunk_find` ni
    `trunk_kinds`. Nadie lo comprobaba, y es la diferencia entre una fachada
    completa y una a medias."""
    servidor, _ = basico

    assert _tools(servidor).isdisjoint(
        {"trunk_kinds", "trunk_health", "trunk_catalog", "trunk_find",
         "trunk_recommend_stack", "trunk_prepare"}
    )


# ---------------------------------------------------------------------------
# 4. Las tools que sólo existen con catálogo (y taxonomía)
# ---------------------------------------------------------------------------


def _entrada(name: str, *, kind: str = "mcp", sector: str = "programacion",
             status: str = "instalado", subsector: str = "edicion"):
    from atlas.mcp.catalog import CatalogEntry

    return CatalogEntry(
        name=name, sector=sector, sector_label="Programación", kind=kind,
        purpose=f"para {name}", source="local", install="n/a", status=status,
        tags=[name], mode="stdio", subsector=subsector,
    )


_CATALOGO = [
    _entrada("editor", kind="mcp", status="instalado"),
    _entrada("linter", kind="skill", status="verificado"),
    _entrada("experimento", kind="mcp", status="candidato"),
]


@pytest.fixture
def completo(tmp_path):
    agg = _Agg()
    servidor = build_trunk_server(  # type: ignore[arg-type]
        agg, catalog=_CATALOGO, taxonomy=_taxonomia(tmp_path),
    )
    return servidor, agg


def test_con_catalogo_y_taxonomia_aparece_la_fachada_entera(completo) -> None:
    servidor, _ = completo

    assert {
        "trunk_kinds", "trunk_health", "trunk_catalog",
        "trunk_find", "trunk_recommend_stack", "trunk_prepare",
    } <= _tools(servidor)


@pytest.mark.parametrize(
    "tool,argumentos",
    [
        ("trunk_kinds", {}),
        ("trunk_health", {}),
        ("trunk_catalog", {}),
        ("trunk_catalog", {"kind": "mcp"}),
        ("trunk_catalog", {"sector": "programacion"}),
        ("trunk_find", {"query": "editor"}),
        ("trunk_recommend_stack", {"goal": "editar código"}),
        ("trunk_prepare", {"goal": "editar código"}),
    ],
)
def test_cada_tool_de_catalogo_se_invoca_sin_traceback(
    completo, tool: str, argumentos: dict[str, Any]
) -> None:
    """Responde, no qué responde: con un catálogo de prueba el contenido es
    irrelevante y afirmarlo haría el test frágil."""
    servidor, _ = completo

    _invocar(servidor, tool, argumentos)


def test_trunk_catalog_ordena_por_MADUREZ_no_alfabeticamente(completo) -> None:
    """`instalado` < `verificado` < `candidato`, y el nombre sólo desempata.
    Es la política 'madurez-first' del tronco: si se perdiera, un candidato sin
    verificar podría encabezar la lista que alguien usa para elegir."""
    servidor, _ = completo

    resultado = _invocar(servidor, "trunk_catalog", {})
    texto = str(resultado)

    assert texto.index("editor") < texto.index("linter") < texto.index("experimento")


def test_trunk_kinds_cuenta_por_LINEA_del_catalogo(completo) -> None:
    servidor, _ = completo

    resultado = str(_invocar(servidor, "trunk_kinds", {}))

    assert "mcp" in resultado and "skill" in resultado


def test_trunk_health_no_spawnea_ni_instala(completo) -> None:
    """Su docstring promete 'diagnóstico sin efectos'. Con `health_configs`
    vacío no hay nada que sondear, y aun así debe contestar en vez de fallar."""
    servidor, agg = completo

    _invocar(servidor, "trunk_health", {})

    assert agg.llamadas == [], "trunk_health no debe tocar el aggregator"
