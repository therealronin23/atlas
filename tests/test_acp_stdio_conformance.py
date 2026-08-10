"""Conformidad ACP sobre el transporte stdio REAL — el hueco de ADC-WO-110.

`tests/test_acp_server.py` instancia `AtlasACPAgent` en proceso con un hub
mockeado y su propio docstring lo dice: "no para el transporte stdio real".
Es honesto, pero deja sin cubrir justo lo que la ficha de ADC-WO-110 pide como
criterio — *"Atlas agent interoperability"* — y hasta el 2026-08-10 **nadie
había lanzado el proceso**. Un `grep -c subprocess` sobre esa suite daba 0.

Es la misma frontera que esta semana escondió un `TypeError` garantizado en el
tronco MCP (cuya suite hacía `tools/list` y no invocaba nada) y un defecto en
la CLI (que se probaba con `--help`): listar prueba el decorador, no el cuerpo,
y construir la clase en proceso no prueba la serialización del protocolo.

Lo que sólo se ve ejecutando: los nombres del schema viajan en camelCase
(`protocolVersion`, `sessionId`), no en el snake_case de la firma Python. Un
cliente real —Zed habla ACP nativamente— rechazaría lo segundo, y ningún test
en proceso lo notaría.

Sin inferencia: el handshake y el rechazo de sesión desconocida son caminos
del protocolo que no llaman al `InferenceHub`. `session/prompt` con una sesión
válida sí llamaría a un proveedor real, y eso no entra en la suite.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time
from importlib.util import find_spec
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    find_spec("acp") is None,
    reason="agent-client-protocol no instalado (dependencia declarada en pyproject)",
)

_REPO = Path(__file__).resolve().parents[1]
_TIMEOUT_S = 30.0


class _AgenteACP:
    """Cliente ACP mínimo por stdio. No usa el SDK a propósito: si el test
    importara el mismo paquete que el servidor, un fallo de serialización
    compartido se cancelaría a sí mismo."""

    def __init__(self) -> None:
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "atlas.acp.server"],
            cwd=_REPO,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env={**os.environ, "PYTHONPATH": str(_REPO / "src"), "PYTHONUNBUFFERED": "1"},
        )

    def call(self, id_: int, method: str, params: dict) -> dict:
        assert self._proc.stdin is not None and self._proc.stdout is not None
        self._proc.stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": id_, "method": method, "params": params})
            + "\n"
        )
        self._proc.stdin.flush()
        limite = time.monotonic() + _TIMEOUT_S
        while time.monotonic() < limite:
            listo, _, _ = select.select([self._proc.stdout], [], [], 0.5)
            if listo:
                linea = self._proc.stdout.readline()
                if linea.strip():
                    return json.loads(linea)
            if self._proc.poll() is not None:
                stderr = self._proc.stderr.read() if self._proc.stderr else ""
                pytest.fail(f"el agente ACP murió durante {method}:\n{stderr[:2000]}")
        pytest.fail(f"sin respuesta a {method} en {_TIMEOUT_S}s")

    def close(self) -> None:
        self._proc.terminate()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()


@pytest.fixture
def agente():
    cliente = _AgenteACP()
    yield cliente
    cliente.close()


def test_el_proceso_real_responde_al_handshake_acp(agente) -> None:
    """`initialize` sobre stdio, sin SDK del lado cliente."""
    respuesta = agente.call(
        1,
        "initialize",
        {
            "protocolVersion": 1,
            "clientCapabilities": {},
            "clientInfo": {"name": "atlas-conformance", "version": "0"},
        },
    )

    assert "error" not in respuesta, respuesta
    result = respuesta["result"]
    assert result["protocolVersion"] == 1
    assert result["agentInfo"]["name"] == "atlas"


def test_las_claves_viajan_en_camelcase_no_en_snake_case(agente) -> None:
    """La firma Python es `protocol_version`; el protocolo exige
    `protocolVersion`. Un test en proceso comparando atributos del dataclass
    pasa con cualquiera de las dos, y un cliente real sólo acepta una."""
    result = agente.call(1, "initialize", {"protocolVersion": 1, "clientCapabilities": {}})["result"]

    assert "protocolVersion" in result and "protocol_version" not in result
    assert "agentCapabilities" in result
    assert "promptCapabilities" in result["agentCapabilities"]


def test_abre_una_sesion_con_identificador_propio(agente) -> None:
    agente.call(1, "initialize", {"protocolVersion": 1, "clientCapabilities": {}})

    result = agente.call(2, "session/new", {"cwd": str(_REPO), "mcpServers": []})["result"]

    assert result["sessionId"]
    assert isinstance(result["sessionId"], str)


def test_dos_sesiones_no_comparten_identificador(agente) -> None:
    agente.call(1, "initialize", {"protocolVersion": 1, "clientCapabilities": {}})

    una = agente.call(2, "session/new", {"cwd": str(_REPO), "mcpServers": []})["result"]
    otra = agente.call(3, "session/new", {"cwd": str(_REPO), "mcpServers": []})["result"]

    assert una["sessionId"] != otra["sessionId"]


def test_una_sesion_desconocida_se_rechaza_sin_llamar_al_modelo(agente) -> None:
    """Camino del protocolo que NO gasta inferencia: `prompt` sale por
    `refusal` antes de tocar el `InferenceHub`. Si algún día deja de salir por
    ahí, este test empezaría a hacer llamadas reales a un proveedor desde la
    suite — y tardaría lo bastante como para que se note."""
    agente.call(1, "initialize", {"protocolVersion": 1, "clientCapabilities": {}})

    respuesta = agente.call(
        2,
        "session/prompt",
        {
            "sessionId": "no-existe-esta-sesion",
            "prompt": [{"type": "text", "text": "hola"}],
        },
    )

    assert respuesta["result"]["stopReason"] == "refusal"
