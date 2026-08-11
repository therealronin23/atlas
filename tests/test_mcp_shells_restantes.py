"""Los otros dos shells MCP, invocados de verdad (t12).

Continúa `test_mcp_shells_invocables.py`, que cerró `engineering_server`
(0% → 72%) y `graph_server` (9% → 79%). Medido con `coverage` el 2026-08-11:

    knowledge_server.py   34 sentencias   65%   faltan 32,37,42,49,54,59,66-75
    operating_server.py   24 sentencias   67%   faltan 34,39,44,51-59

Las líneas que faltan son EXACTAMENTE los cuerpos de las tools y `serve()`:
registradas por el decorador, nunca ejecutadas. La misma frontera que ya costó
un defecto real esta semana (`engineering_trunk` llamando a
`history_hypothesis(module, repo_root=...)` con la firma al revés).

**Dos cosas que sólo se supieron ejecutando**, y que un test escrito leyendo el
código habría dado por otras:

1. `operating_server` no expone tres tools. Expone **dos resources**
   (`operating://agents`, `operating://ledger`) **y una tool**
   (`sanitation_audit`). Los resources se leen por otro camino del protocolo,
   y confundirlos deja sin cubrir justo lo que se creía cubierto. Encaja con
   la nota del catálogo: de los seis primitivos MCP el tronco usa dos o tres.
2. El shell traduce nombres. La tool `wikipedia_lookup` llama a
   `trunk.wikipedia(title)` —posicional— y `ingest_wikipedia` reenvía `domain`
   y `goal` como kwargs. Ese renombrado es precisamente la frontera que se
   quiere fijar: si alguien cambia el trunk, aquí se rompe.

El trunk va doblado. No es sólo evitar red — `knowledge_server` llama a
Wikipedia, el Banco Mundial, Open-Meteo y Frankfurter, y una suite que sale a
internet mide la conectividad, no el código.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

pytest.importorskip("mcp")

from atlas.mcp.knowledge_server import build_knowledge_server  # noqa: E402
from atlas.mcp.operating_server import build_operating_server  # noqa: E402


def _invocar(server: Any, nombre: str, argumentos: dict[str, Any]) -> Any:
    """El camino REAL de FastMCP ante un `tools/call`: valida los argumentos
    contra el esquema derivado de la firma y ejecuta el cuerpo. Llamar a la
    función de Python a mano se saltaría esa validación, que es donde vive la
    clase de defecto que esto persigue."""
    return asyncio.run(server.call_tool(nombre, argumentos))


def _leer_recurso(server: Any, uri: str) -> Any:
    """Los resources tienen su propio camino en el protocolo (`resources/read`),
    distinto del de las tools."""
    return asyncio.run(server.read_resource(uri))


class _TrunkConocimiento:
    """Doble del `KnowledgeTrunk`, con las firmas REALES que usa el shell."""

    def __init__(self) -> None:
        self.llamadas: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _anotar(self, nombre: str, args: tuple[Any, ...], kw: dict[str, Any]) -> None:
        self.llamadas.append((nombre, args, kw))

    def wikipedia(self, title: str) -> list[dict[str, Any]]:
        self._anotar("wikipedia", (title,), {})
        return [{"ok": True}]

    def ingest_wikipedia(self, title: str, *, domain: str, goal: str) -> dict[str, Any]:
        self._anotar("ingest_wikipedia", (title,), {"domain": domain, "goal": goal})
        return {"ingested": 1}

    def worldbank(self, country: str, indicator: str) -> list[dict[str, Any]]:
        self._anotar("worldbank", (country, indicator), {})
        return [{"ok": True}]

    def ingest_worldbank(
        self, country: str, indicator: str, *, domain: str, goal: str
    ) -> dict[str, Any]:
        self._anotar(
            "ingest_worldbank", (country, indicator), {"domain": domain, "goal": goal}
        )
        return {"ingested": 1}

    def ingest_open_meteo(
        self, latitude: float, longitude: float, *, goal: str
    ) -> dict[str, Any]:
        self._anotar("ingest_open_meteo", (latitude, longitude), {"goal": goal})
        return {"ingested": 1}

    def ingest_frankfurter(self, frm: str, to: str, *, goal: str) -> dict[str, Any]:
        self._anotar("ingest_frankfurter", (frm, to), {"goal": goal})
        return {"ingested": 1}


class _TrunkOperacion:
    def __init__(self, *, revienta: bool = False) -> None:
        self.revienta = revienta
        self.llamadas: list[str] = []

    def _texto(self, nombre: str) -> str:
        self.llamadas.append(nombre)
        if self.revienta:
            raise RuntimeError(f"{nombre} falló a propósito")
        return f"contenido de {nombre}"

    def agents_md(self) -> str:
        return self._texto("agents_md")

    def work_ledger(self) -> str:
        return self._texto("work_ledger")

    def sanitation_audit(self) -> str:
        return self._texto("sanitation_audit")


# ---------------------------------------------------------------------------
# knowledge_server — seis tools
# ---------------------------------------------------------------------------


@pytest.fixture
def conocimiento():
    trunk = _TrunkConocimiento()
    return build_knowledge_server(trunk), trunk  # type: ignore[arg-type]


def test_las_seis_tools_de_conocimiento_estan_registradas(conocimiento) -> None:
    servidor, _ = conocimiento

    nombres = {t.name for t in asyncio.run(servidor.list_tools())}

    assert nombres == {
        "wikipedia_lookup", "ingest_wikipedia", "worldbank_lookup",
        "ingest_worldbank", "ingest_open_meteo", "ingest_frankfurter",
    }


@pytest.mark.parametrize(
    "tool,argumentos,metodo_trunk",
    [
        ("wikipedia_lookup", {"title": "Kuzu"}, "wikipedia"),
        ("ingest_wikipedia", {"title": "Kuzu"}, "ingest_wikipedia"),
        (
            "worldbank_lookup",
            {"country": "ESP", "indicator": "NY.GDP.MKTP.CD"},
            "worldbank",
        ),
        (
            "ingest_worldbank",
            {"country": "ESP", "indicator": "NY.GDP.MKTP.CD"},
            "ingest_worldbank",
        ),
        ("ingest_open_meteo", {"latitude": 40.4, "longitude": -3.7}, "ingest_open_meteo"),
        ("ingest_frankfurter", {"frm": "EUR", "to": "USD"}, "ingest_frankfurter"),
    ],
)
def test_cada_tool_llama_al_metodo_del_trunk_que_le_toca(
    conocimiento, tool: str, argumentos: dict[str, Any], metodo_trunk: str
) -> None:
    """El shell RENOMBRA: `wikipedia_lookup` -> `trunk.wikipedia`. Fijar ese
    mapeo es el objeto del test — si el trunk cambia, aquí se rompe."""
    servidor, trunk = conocimiento

    _invocar(servidor, tool, argumentos)

    assert [n for n, _, _ in trunk.llamadas] == [metodo_trunk]


def test_los_valores_por_defecto_del_shell_llegan_al_trunk(conocimiento) -> None:
    """`domain` y `goal` tienen default en la firma del shell. Si no se
    reenvían, el trunk recibe algo distinto de lo documentado y nadie lo nota."""
    servidor, trunk = conocimiento

    _invocar(servidor, "ingest_wikipedia", {"title": "Kuzu"})

    _, _, kwargs = trunk.llamadas[-1]
    assert kwargs == {"domain": "knowledge/wikipedia", "goal": ""}


def test_un_domain_explicito_gana_al_default(conocimiento) -> None:
    servidor, trunk = conocimiento

    _invocar(servidor, "ingest_wikipedia", {"title": "Kuzu", "domain": "otro/sitio"})

    assert trunk.llamadas[-1][2]["domain"] == "otro/sitio"


def test_los_numeros_llegan_como_numeros_no_como_texto(conocimiento) -> None:
    """El esquema los declara `float`; si el shell los pasara sin convertir, el
    trunk recibiría cadenas y fallaría lejos de aquí."""
    servidor, trunk = conocimiento

    _invocar(servidor, "ingest_open_meteo", {"latitude": 40.4, "longitude": -3.7})

    _, args, _ = trunk.llamadas[-1]
    assert args == (40.4, -3.7)
    assert all(isinstance(v, float) for v in args)


def test_un_parametro_que_no_existe_lo_rechaza_el_esquema(conocimiento) -> None:
    """La validación la hace FastMCP desde la firma. Que ocurra es lo que
    distingue invocar por el camino real de llamar a la función a mano."""
    servidor, _ = conocimiento

    with pytest.raises(Exception):
        _invocar(servidor, "wikipedia_lookup", {"titulo_mal_escrito": "Kuzu"})


def test_falta_un_parametro_obligatorio(conocimiento) -> None:
    servidor, _ = conocimiento

    with pytest.raises(Exception):
        _invocar(servidor, "worldbank_lookup", {"country": "ESP"})


# ---------------------------------------------------------------------------
# operating_server — DOS resources y UNA tool, no tres tools
# ---------------------------------------------------------------------------


def test_operating_expone_una_tool_y_dos_resources() -> None:
    """Lo que se creía tres tools. Los resources son otro primitivo del
    protocolo y se leen por otro camino."""
    servidor = build_operating_server(_TrunkOperacion())  # type: ignore[arg-type]

    tools = {t.name for t in asyncio.run(servidor.list_tools())}
    recursos = {str(r.uri) for r in asyncio.run(servidor.list_resources())}

    assert tools == {"sanitation_audit"}
    assert recursos == {"operating://agents", "operating://ledger"}


def test_la_tool_de_saneamiento_se_invoca() -> None:
    trunk = _TrunkOperacion()
    servidor = build_operating_server(trunk)  # type: ignore[arg-type]

    _invocar(servidor, "sanitation_audit", {})

    assert trunk.llamadas == ["sanitation_audit"]


@pytest.mark.parametrize(
    "uri,metodo",
    [("operating://agents", "agents_md"), ("operating://ledger", "work_ledger")],
)
def test_cada_resource_se_lee_y_llama_a_su_metodo(uri: str, metodo: str) -> None:
    """`operating://agents` -> `trunk.agents_md()`: otro renombrado en la
    frontera, y el que sirve `AGENTS.md` a cada sesión."""
    trunk = _TrunkOperacion()
    servidor = build_operating_server(trunk)  # type: ignore[arg-type]

    _leer_recurso(servidor, uri)

    assert trunk.llamadas == [metodo]


def test_si_el_trunk_revienta_la_tool_no_lo_disfraza() -> None:
    """Un fallo del trunk tiene que propagarse. Devolver cadena vacía o texto
    de relleno convertiría una avería en contenido — la familia de defecto que
    esta auditoría lleva una semana arrancando."""
    servidor = build_operating_server(_TrunkOperacion(revienta=True))  # type: ignore[arg-type]

    with pytest.raises(Exception):
        _invocar(servidor, "sanitation_audit", {})


@pytest.mark.parametrize("uri", ["operating://agents", "operating://ledger"])
def test_si_el_trunk_revienta_el_resource_tampoco(uri: str) -> None:
    servidor = build_operating_server(_TrunkOperacion(revienta=True))  # type: ignore[arg-type]

    with pytest.raises(Exception):
        _leer_recurso(servidor, uri)
