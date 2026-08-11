"""Identidad de tailnet: el emparejamiento que no hace falta hacer (ADC-WO-111).

La ficha pedía "authenticated pairing" para que la Mission Console en Android
alcanzara el bridge. El problema es llevar un token de 32+ bytes al móvil sin
teclearlo, y las salidas habituales cuestan caro: un QR son dos dependencias
nuevas y un codificador Reed-Solomon que este repo no tiene (manía
`stdlib-over-new-deps`), y un endpoint de emparejamiento es superficie pre-auth
nueva justo delante de un servicio que aprueba misiones.

Medido el 2026-08-11: no hace falta ninguna. **Si el dispositivo está en el
tailnet, el emparejamiento ya ocurrió cuando se unió**, y WireGuard ya lo
autenticó. `tailscaled` contesta por su LocalAPI en 0,6 ms quién es el peer:

    GET /localapi/v0/whois?addr=100.113.135.34:0
      Node.Name : redmi-note-13.tail1cc8de.ts.net.
      Node.ID   : nTpF7HUZS511CNTRL
      User      : tomas.asin.gonzalez@gmail.com

Así que no se transfiere ningún secreto ni se inventa uno: se le pregunta al
transporte, que es quien lo sabe. Menos código, menos superficie y una
credencial menos que rotar.

**La trampa que hace peligroso este método**, y por la que
`bind_permite_identidad_de_tailnet` existe: la identidad se deduce de la IP de
origen. Eso sólo es seguro si los paquetes NO pueden llegar por otra interfaz.
Escuchando en `0.0.0.0`, un vecino de la LAN puede asignarse una IP del rango
CGNAT, conectar por la LAN, y `whois` responderá honestamente que esa IP es el
móvil — porque lo es, en el tailnet. Atado a la dirección del tailnet, el
kernel no entrega por otra ruta y la deducción se sostiene.

Este módulo NO cambia por sí solo la postura del bridge: es una biblioteca. La
decisión de escuchar fuera de loopback sigue siendo del operador.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import logging
import socket
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

logger = logging.getLogger(__name__)

#: Sockets donde `tailscaled` publica su LocalAPI, en orden de preferencia.
_SOCKET_PATHS = ("/var/run/tailscale/tailscaled.sock", "/run/tailscale/tailscaled.sock")

#: Tailscale reparte direcciones del rango CGNAT (RFC 6598) y una ULA fija.
_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_TAILSCALE_ULA = ipaddress.ip_network("fd7a:115c:a1e0::/48")

#: La LocalAPI rechaza peticiones sin esta cabecera (defensa CSRF suya).
_LOCALAPI_HEADERS = {"Host": "local-tailscaled.sock", "Sec-Tailscale": "localapi"}

_TIMEOUT_S = 3.0

#: Transporte: recibe la ruta de la LocalAPI y devuelve el cuerpo. Inyectable
#: para que los tests no toquen el socket real.
Transport = Callable[[str], str]


class TailnetUnavailable(RuntimeError):
    """No se pudo preguntar a `tailscaled`.

    Existe como excepción propia para que "el demonio está caído" no se
    confunda con "ese peer no es tuyo": son dos incidencias distintas para
    quien opera, y colapsarlas en un `None` silencioso es justo el defecto
    —error disfrazado de estado normal— que esta auditoría lleva arrancando.
    """


@dataclass(frozen=True)
class TailnetPeer:
    """Un dispositivo del tailnet, tal y como lo identifica `tailscaled`."""

    node_name: str
    node_id: str
    login_name: str


def es_direccion_de_tailnet(ip: str) -> bool:
    """¿Cae la IP en el espacio que reparte Tailscale?

    Condición NECESARIA, no suficiente: una IP de la LAN nunca es un peer, pero
    una IP del rango tampoco lo es hasta que `tailscaled` la reconozca.
    """
    try:
        direccion = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(direccion, ipaddress.IPv4Address):
        return direccion in _CGNAT
    return direccion in _TAILSCALE_ULA


def bind_permite_identidad_de_tailnet(host: str) -> bool:
    """¿Es lícito autenticar por identidad de tailnet escuchando en `host`?

    Sólo si `host` ES una dirección del tailnet. Cualquier otra cosa —y muy en
    particular `0.0.0.0` y `::`— permite que lleguen paquetes por interfaces
    donde la IP de origen no la controla WireGuard, y entonces deducir la
    identidad de esa IP deja de ser válido.

    Loopback devuelve `False` a propósito: no es que sea inseguro, es que por
    ahí no llegan peers del tailnet y el bridge ya tiene su propio camino para
    loopback. Devolver `True` sugeriría que este método aporta algo allí.
    """
    return es_direccion_de_tailnet(host)


def _http_por_socket_unix(path_localapi: str) -> str:
    """Transporte real: HTTP sobre el socket unix de `tailscaled`."""
    ultimo: Exception | None = None
    for socket_path in _SOCKET_PATHS:
        try:
            conexion = _ConexionUnix(socket_path)
            try:
                conexion.request("GET", path_localapi, headers=_LOCALAPI_HEADERS)
                respuesta = conexion.getresponse()
                cuerpo = respuesta.read().decode("utf-8", errors="replace")
                if respuesta.status == 404:
                    # "no match for IP:port" — la IP no pertenece a ningún nodo.
                    # Es una respuesta NEGATIVA NORMAL, no una avería: quien
                    # pregunta por una IP del rango que nadie ocupa merece un
                    # "no" limpio, no un aviso de infraestructura caída. Se
                    # devuelve `null` para que el parseo lo convierta en None
                    # por el mismo camino que cualquier otra no-coincidencia.
                    return "null"
                if respuesta.status != 200:
                    raise TailnetUnavailable(
                        f"localapi devolvió {respuesta.status}: {cuerpo[:200]}"
                    )
                return cuerpo
            finally:
                conexion.close()
        except TailnetUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 — se prueba el siguiente socket
            ultimo = exc
    raise TailnetUnavailable(f"no se pudo hablar con tailscaled: {ultimo}")


class _ConexionUnix(http.client.HTTPConnection):
    """`HTTPConnection` sobre AF_UNIX. La stdlib no lo trae, y son seis líneas."""

    def __init__(self, socket_path: str) -> None:
        super().__init__("localhost", timeout=_TIMEOUT_S)
        self._socket_path = socket_path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(_TIMEOUT_S)
        sock.connect(self._socket_path)
        self.sock = sock


class TailnetIdentity:
    """Resuelve la identidad de un peer preguntando a `tailscaled`.

    `login_propio` es la cuenta de ESTE nodo. Sin ella no se acepta a nadie:
    estar en la misma malla no basta, porque un tailnet puede tener nodos
    compartidos de otras cuentas.
    """

    def __init__(
        self,
        *,
        transport: Transport | None = None,
        login_propio: str | None = None,
    ) -> None:
        self._transport = transport or _http_por_socket_unix
        self._login_propio = (login_propio or "").strip() or None

    def whois(self, ip: str) -> TailnetPeer | None:
        """Identidad del peer, o `None` si `tailscaled` no lo reconoce.

        Lanza `TailnetUnavailable` si no se le pudo preguntar — un fallo de
        infraestructura no es una respuesta negativa.
        """
        # `addr` es host:port. El puerto no se usa para identificar el nodo,
        # pero la LocalAPI exige la forma completa; los corchetes son
        # obligatorios en IPv6 o sus dos puntos rompen el parseo.
        host = f"[{ip}]" if ":" in ip else ip
        ruta = f"/localapi/v0/whois?addr={quote(f'{host}:0', safe='')}"
        try:
            cuerpo = self._transport(ruta)
        except TailnetUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 — cualquier fallo del transporte
            # El contrato es "no poder preguntar SIEMPRE es TailnetUnavailable",
            # no sólo cuando falla el transporte por defecto. Esto corre en el
            # camino de cada petición del bridge: una excepción inesperada que
            # escape convierte un 401 limpio en un 500.
            raise TailnetUnavailable(f"{type(exc).__name__}: {exc}") from exc
        try:
            datos = json.loads(cuerpo)
        except ValueError:
            logger.warning("whois devolvió algo que no es JSON para %s", ip)
            return None
        return _peer_desde_whois(datos)

    def verificar_peer(self, ip: str) -> TailnetPeer | None:
        """El portón completo. `None` = no autenticado, por el motivo que sea.

        Orden deliberado: el rango se comprueba ANTES de preguntar. No es sólo
        ahorrarse la llamada — deja escrito que pertenecer al rango es
        condición necesaria, y no una comprobación redundante que alguien
        pueda quitar por "ya lo valida tailscaled".
        """
        if self._login_propio is None:
            logger.warning(
                "identidad de tailnet pedida sin conocer la cuenta local; "
                "sin con qué comparar no se acepta a nadie"
            )
            return None
        if not es_direccion_de_tailnet(ip):
            return None
        try:
            peer = self.whois(ip)
        except TailnetUnavailable as exc:
            # Fallo cerrado, pero RUIDOSO: si tailscaled se cae, el bridge deja
            # de autenticar a nadie y eso tiene que verse en el log, no
            # parecerse a "no había peers".
            logger.warning("no se pudo verificar %s contra tailscaled: %s", ip, exc)
            return None
        if peer is None:
            return None
        if peer.login_name != self._login_propio:
            logger.warning(
                "peer %s está en el tailnet pero es de otra cuenta (%s)",
                ip,
                peer.login_name,
            )
            return None
        return peer


def _peer_desde_whois(datos: Any) -> TailnetPeer | None:
    """Convierte la respuesta de la LocalAPI, rechazando lo incompleto.

    Un campo que falta NO se rellena con un valor por defecto: autenticar con
    datos a medias es peor que no autenticar.
    """
    if not isinstance(datos, dict):
        return None
    nodo = datos.get("Node")
    perfil = datos.get("UserProfile")
    if not isinstance(nodo, dict) or not isinstance(perfil, dict):
        return None
    if nodo.get("Tags"):
        # Los nodos etiquetados son servicios/CI, no el dispositivo de una
        # persona: su `LoginName` es un `tagged-devices` sintético que podría
        # coincidir con el nuestro. Denegar por defecto; si algún día hace
        # falta un runner, que sea una decisión explícita y no un descuido.
        return None
    nombre = str(nodo.get("Name") or "").rstrip(".")
    node_id = str(nodo.get("StableID") or "")
    login = str(perfil.get("LoginName") or "")
    if not nombre or not node_id or not login:
        return None
    return TailnetPeer(node_name=nombre, node_id=node_id, login_name=login)


def login_local(transport: Transport | None = None) -> str | None:
    """Cuenta de ESTE nodo, según `tailscaled`. `None` si no se puede saber."""
    hablar = transport or _http_por_socket_unix
    try:
        datos = json.loads(hablar("/localapi/v0/status"))
    except (TailnetUnavailable, ValueError, OSError) as exc:
        logger.warning("no se pudo leer la identidad local del tailnet: %s", exc)
        return None
    if not isinstance(datos, dict):
        return None
    propio = datos.get("Self")
    usuarios = datos.get("User")
    if not isinstance(propio, dict) or not isinstance(usuarios, dict):
        return None
    perfil = usuarios.get(str(propio.get("UserID")))
    if not isinstance(perfil, dict):
        return None
    return str(perfil.get("LoginName") or "") or None
