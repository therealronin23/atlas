"""ADC-WO-109: negociación de versión y degradación sin backend.

Dos de los cuatro tests que la ficha de Cut 2 nombra —`bridge version
negotiation` y `offline and backend-loss degradation`— y que no existían.
El coding bridge, que es de lo que depende el Workbench entero, no tenía
NINGÚN test: 0 de 88 sentencias.

Por qué la negociación no es burocracia. `atlasBackendMainService.ts` decidía
"ya hay un bridge vivo, no relanzo" con esto:

    const req = http.get({ …, path: '/health', … }, res =>
        resolve(res.statusCode === 200))

Cualquier cosa que conteste 200 en `127.0.0.1:7342/health` —otro servicio,
un proceso viejo de otro proyecto, un `python -m http.server` con un fichero
`health`— convence al Workbench de que Atlas está vivo. El proveedor no
responde nunca y el log dice que todo está bien: un error disfrazado de
estado normal, la familia de defectos que más veces ha aparecido en este
repo. La negociación existe para que el cliente sepa CON QUIÉN habla y en qué
versión, no sólo que algo hay.

La degradación es lo mismo por el otro lado: sin proveedores utilizables, el
bridge tiene que decir `degraded` y devolver un error que un cliente
OpenAI-compatible sepa distinguir de "petición mal formada".
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from atlas.api import coding_server


class _HubFalso:
    """Sustituye al InferenceHub REAL sólo en lo que el bridge le pide.

    No es un doble del hub: es un doble de su superficie de estado
    (`providers_status`) y de una inferencia. Lo que se prueba aquí es el
    bridge, no el hub — el hub tiene sus propios tests.
    """

    def __init__(
        self,
        proveedores: list[dict[str, Any]] | None = None,
        respuesta: Any = None,
    ) -> None:
        self._proveedores = proveedores if proveedores is not None else []
        self._respuesta = respuesta

    def providers_status(self) -> list[dict[str, Any]]:
        return self._proveedores

    def infer_for_role(self, role: str, req: Any) -> Any:
        if self._respuesta is None:
            raise AssertionError("no debería haberse llamado al hub")
        return self._respuesta


class _Respuesta:
    def __init__(self, *, success: bool, error: str = "", text: str = "") -> None:
        self.success = success
        self.error = error
        self.text = text
        self.tool_calls: list[dict[str, Any]] = []
        self.model = "modelo-x"
        self.provider = "proveedor-x"
        self.mode = "live"
        self.latency_ms = 12
        self.tokens_used = 7
        self.finish_reason = "stop"


def _proveedor(nombre: str, modelo: str, estado: str, *, rl: int = 0) -> dict[str, Any]:
    return {
        "name": nombre, "model": modelo, "status": estado,
        "level": "L1", "error_count": 0, "free_tier": True,
        "last_used": 0.0, "rate_limited_for_s": rl,
    }


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Cada test elige su hub; por defecto, uno con dos proveedores sanos."""
    def _construir(hub: _HubFalso) -> TestClient:
        monkeypatch.setattr(coding_server, "_hub", lambda: hub)
        return TestClient(coding_server.create_app())
    return _construir


_SANOS = [
    _proveedor("groq", "llama-3.3-70b-versatile", "ok"),
    _proveedor("nvidia", "moonshotai/kimi-k2-instruct", "degraded"),
]


# ---------------------------------------------------------------------------
# Negociación de versión
# ---------------------------------------------------------------------------


def test_health_se_identifica_y_declara_su_protocolo(cliente: Any) -> None:
    """Sin esto, el cliente no puede distinguir el bridge de cualquier otro
    servicio que devuelva 200."""
    r = cliente(_HubFalso(_SANOS)).get("/health")

    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["service"] == coding_server.SERVICE_NAME
    assert cuerpo["protocol"]["version"] == coding_server.PROTOCOL_VERSION
    assert cuerpo["protocol"]["min_client"] == coding_server.MIN_CLIENT_PROTOCOL
    assert cuerpo["protocol"]["min_client"] <= cuerpo["protocol"]["version"]


def test_un_cliente_que_no_declara_version_sigue_siendo_compatible(cliente: Any) -> None:
    """Compatibilidad hacia atrás explícita: el cliente que ya está
    desplegado no manda la cabecera. Romperlo aquí sería introducir el fallo
    que este test existe para evitar."""
    cuerpo = cliente(_HubFalso(_SANOS)).get("/health").json()

    assert cuerpo["client"]["declared"] is None
    assert cuerpo["client"]["compatible"] is True


@pytest.mark.parametrize("declarada", ["1", " 1 "])
def test_un_cliente_en_la_misma_version_es_compatible(
    cliente: Any, declarada: str
) -> None:
    cuerpo = cliente(_HubFalso(_SANOS)).get(
        "/health", headers={coding_server.CLIENT_PROTOCOL_HEADER: declarada}
    ).json()

    assert cuerpo["client"]["compatible"] is True, cuerpo["client"]["reason"]


def test_un_cliente_mas_nuevo_que_el_bridge_no_es_compatible(cliente: Any) -> None:
    """El caso de la actualización a medias: el Workbench se actualiza y
    atlas-core no. El bridge no puede fingir que entiende un protocolo que no
    conoce."""
    futura = str(coding_server.PROTOCOL_VERSION + 1)
    cuerpo = cliente(_HubFalso(_SANOS)).get(
        "/health", headers={coding_server.CLIENT_PROTOCOL_HEADER: futura}
    ).json()

    assert cuerpo["client"]["compatible"] is False
    assert futura in cuerpo["client"]["reason"]
    # El motivo tiene que decir la versión del bridge: es lo único con lo que
    # el operador puede saber qué actualizar.
    assert str(coding_server.PROTOCOL_VERSION) in cuerpo["client"]["reason"]


def test_un_cliente_por_debajo_del_minimo_no_es_compatible(
    cliente: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hoy `min_client` es 1 y no hay versión menor, así que el caso sólo se
    puede ejercitar subiendo el mínimo. Se ejercita igual: el día que suba,
    la rama ya está probada en vez de estrenarse en producción."""
    monkeypatch.setattr(coding_server, "MIN_CLIENT_PROTOCOL", 3)
    monkeypatch.setattr(coding_server, "PROTOCOL_VERSION", 4)

    cuerpo = cliente(_HubFalso(_SANOS)).get(
        "/health", headers={coding_server.CLIENT_PROTOCOL_HEADER: "2"}
    ).json()

    assert cuerpo["client"]["compatible"] is False
    assert "antiguo" in cuerpo["client"]["reason"]


@pytest.mark.parametrize("basura", ["", "v1", "1.0", "muchas", "-1"])
def test_una_version_ilegible_no_se_interpreta_como_compatible(
    cliente: Any, basura: str
) -> None:
    """`int("1.0")` revienta y `int("-1")` cuela: una versión que no se
    entiende NO puede caer del lado permisivo."""
    cuerpo = cliente(_HubFalso(_SANOS)).get(
        "/health", headers={coding_server.CLIENT_PROTOCOL_HEADER: basura}
    ).json()

    assert cuerpo["client"]["compatible"] is False, basura


def test_la_negociacion_es_una_funcion_pura_y_se_puede_probar_sola() -> None:
    """El cliente TypeScript replica esta decisión; tenerla aislada es lo que
    permite comparar las dos implementaciones sin levantar nada."""
    assert coding_server.negociar_protocolo(None) == (True, "cliente sin versión declarada")
    compatible, motivo = coding_server.negociar_protocolo("999")
    assert compatible is False and "999" in motivo


# ---------------------------------------------------------------------------
# Degradación: sin backend
# ---------------------------------------------------------------------------


def test_sin_proveedores_utilizables_health_dice_degraded(cliente: Any) -> None:
    r = cliente(_HubFalso([])).get("/health")

    assert r.status_code == 200, "degradado no es caído: el bridge sigue en pie"
    cuerpo = r.json()
    assert cuerpo["status"] == "degraded"
    assert cuerpo["providers"] == {"total": 0, "usable": 0}


def test_todos_los_proveedores_caidos_tambien_es_degraded(cliente: Any) -> None:
    """Tener proveedores configurados no es tenerlos utilizables — la
    distinción que hace que `degraded` signifique algo."""
    caidos = [
        _proveedor("groq", "llama", "down"),
        _proveedor("nvidia", "kimi", "rate_limited", rl=42),
    ]
    cuerpo = cliente(_HubFalso(caidos)).get("/health").json()

    assert cuerpo["status"] == "degraded"
    assert cuerpo["providers"] == {"total": 2, "usable": 0}


def test_un_proveedor_degradado_sigue_contando_como_utilizable(cliente: Any) -> None:
    """`degraded` en un proveedor es "responde peor", no "no responde"."""
    cuerpo = cliente(_HubFalso([_proveedor("nvidia", "kimi", "degraded")])).get(
        "/health"
    ).json()

    assert cuerpo["status"] == "ok"
    assert cuerpo["providers"] == {"total": 1, "usable": 1}


def test_sin_backend_la_completion_devuelve_503_con_forma_openai(cliente: Any) -> None:
    """503, no 502: el cliente distingue "no hay a quién preguntar" de
    "pregunté y falló". Y con la forma de error de OpenAI, porque los
    clientes reales (Continue y compañía) la saben pintar."""
    r = cliente(_HubFalso([])).post(
        "/v1/chat/completions", json={"messages": [{"role": "user", "content": "hola"}]}
    )

    assert r.status_code == 503
    error = r.json()["error"]
    assert error["type"] == "atlas_backend_unavailable"
    assert "Retry-After" in r.headers


def test_un_fallo_del_proveedor_es_502_y_se_distingue_del_anterior(cliente: Any) -> None:
    hub = _HubFalso(_SANOS, respuesta=_Respuesta(success=False, error="429 desde groq"))
    r = cliente(hub).post(
        "/v1/chat/completions", json={"messages": [{"role": "user", "content": "hola"}]}
    )

    assert r.status_code == 502
    error = r.json()["error"]
    assert error["type"] == "atlas_upstream_error"
    assert "429 desde groq" in error["message"]


def test_una_peticion_sin_mensajes_sigue_siendo_400_del_cliente(cliente: Any) -> None:
    """La degradación no puede tragarse los errores de petición: si todo
    fuera 5xx, el cliente reintentaría eternamente algo que nunca va a ir."""
    r = cliente(_HubFalso(_SANOS)).post("/v1/chat/completions", json={})

    assert r.status_code == 400
    assert r.json()["error"]["type"] == "invalid_request_error"


def test_con_backend_la_completion_responde_como_openai(cliente: Any) -> None:
    hub = _HubFalso(_SANOS, respuesta=_Respuesta(success=True, text="hola"))
    r = cliente(hub).post(
        "/v1/chat/completions", json={"messages": [{"role": "user", "content": "hola"}]}
    )

    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["choices"][0]["message"]["content"] == "hola"
    assert cuerpo["object"] == "chat.completion"
    # No es OpenAI y no se disimula: qué proveedor real contestó.
    assert cuerpo["atlas_meta"]["provider"] == "proveedor-x"


@pytest.mark.parametrize(
    "modelo, rol",
    [
        ("atlas-chat", "chat"),
        ("atlas-edit", "edit"),
        ("atlas-apply", "apply"),
        ("ATLAS-EDIT", "edit"),
        ("", "chat"),
        ("cualquier-cosa", "chat"),
    ],
)
def test_el_campo_model_selecciona_ROL_no_proveedor(modelo: str, rol: str) -> None:
    """Patrón validado por Continue/Cline/Cursor: el cliente pide un rol y
    Atlas resuelve el proveedor por su cadena de fallback. Si esto se
    invirtiera, el cliente estaría eligiendo proveedor sin saberlo."""
    assert coding_server._role_for_model(modelo) == rol


def test_las_tool_calls_salen_con_la_forma_de_openai(cliente: Any) -> None:
    respuesta = _Respuesta(success=True, text="")
    respuesta.tool_calls = [{"name": "git_status", "arguments": '{"a":1}'}]
    respuesta.finish_reason = ""
    r = cliente(_HubFalso(_SANOS, respuesta=respuesta)).post(
        "/v1/chat/completions", json={"messages": [{"role": "user", "content": "x"}]}
    )

    tc = r.json()["choices"][0]["message"]["tool_calls"][0]
    assert tc["type"] == "function"
    assert tc["function"] == {"name": "git_status", "arguments": '{"a":1}'}
    # Sin `id` del proveedor se genera uno: un tool_call sin id no se puede
    # correlacionar con su resultado y el loop se rompe.
    assert tc["id"].startswith("call_")
    assert r.json()["choices"][0]["finish_reason"] == "tool_calls"


def test_el_streaming_entrega_SSE_valido_aunque_no_sea_incremental(
    cliente: Any,
) -> None:
    """El módulo declara que el streaming es un único chunk porque el
    InferenceHub es síncrono. Que no sea incremental no lo exime de ser SSE
    bien formado: un cliente que lo parsee tiene que poder terminar."""
    hub = _HubFalso(_SANOS, respuesta=_Respuesta(success=True, text="hola"))
    r = cliente(hub).post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "x"}], "stream": True},
    )

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    lineas = [ln for ln in r.text.split("\n\n") if ln.strip()]
    assert lineas[-1] == "data: [DONE]"
    assert '"content": "hola"' in lineas[0] or '"content":"hola"' in lineas[0]
    assert '"chat.completion.chunk"' in lineas[0]


def test_sin_backend_tampoco_se_abre_un_stream_vacio(cliente: Any) -> None:
    """La degradación tiene que cortar ANTES de decidir el transporte: un
    stream que se abre y no manda nada es peor que un error, porque el
    cliente se queda esperando."""
    r = cliente(_HubFalso([])).post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "x"}], "stream": True},
    )

    assert r.status_code == 503
    assert not r.headers["content-type"].startswith("text/event-stream")


# ---------------------------------------------------------------------------
# /v1/models
# ---------------------------------------------------------------------------


def test_models_lista_los_modelos_reales_no_los_nombres_de_proveedor(
    cliente: Any,
) -> None:
    """Defecto encontrado leyendo, y confirmado ejecutando: el código pedía
    `p.get("model_id")` y `providers_status()` devuelve la clave `model`. El
    `or` de reserva tapaba el fallo, así que `/v1/models` publicaba nombres de
    proveedor como si fueran identificadores de modelo, y la verificación en
    vivo del 2026-08-11 —"devolvió la lista real de proveedores"— describía
    justo eso sin que se notara que era el síntoma."""
    cuerpo = cliente(_HubFalso(_SANOS)).get("/v1/models").json()
    ids = {m["id"] for m in cuerpo["data"]}

    assert "llama-3.3-70b-versatile" in ids
    assert "moonshotai/kimi-k2-instruct" in ids
    assert "groq" not in ids, "eso es el nombre del proveedor, no un modelo"
    # Los roles lógicos sí siguen siendo seleccionables.
    assert {"atlas-chat", "atlas-edit", "atlas-apply"} <= ids


def test_models_no_repite_un_modelo_servido_por_dos_proveedores(cliente: Any) -> None:
    dos = [
        _proveedor("groq", "llama-3.3-70b-versatile", "ok"),
        _proveedor("otro", "llama-3.3-70b-versatile", "ok"),
    ]
    ids = [m["id"] for m in cliente(_HubFalso(dos)).get("/v1/models").json()["data"]]

    assert ids.count("llama-3.3-70b-versatile") == 1
