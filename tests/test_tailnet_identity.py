"""Identidad de tailnet como sustituto del emparejamiento (ADC-WO-111).

El problema que la ficha llama "authenticated pairing" era: llevar un token de
32+ bytes del escritorio al móvil sin teclearlo. Las salidas habituales son un
QR (dos dependencias nuevas y un codificador que este repo no tiene) o un
endpoint de emparejamiento pre-auth (superficie de ataque nueva).

Medido el 2026-08-11, ninguna hace falta: **si el dispositivo está en el
tailnet, el emparejamiento ya ocurrió cuando se unió**. `tailscaled` responde
por su LocalAPI en 0,6 ms quién es el peer, con nombre de nodo, ID estable y
cuenta:

    GET /localapi/v0/whois?addr=100.113.135.34:1234
      Node.Name : redmi-note-13.tail1cc8de.ts.net.
      User      : tomas.asin.gonzalez@gmail.com

Así que no se transfiere ningún secreto: se pregunta al transporte, que ya
autenticó al dispositivo con WireGuard.

Lo que fijan estos tests son las cuatro formas de equivocarse con eso:

1. **Rango antes que consulta.** Una IP fuera del rango del tailnet no se
   pregunta siquiera — ahorra la llamada y, sobre todo, deja explícito que la
   pertenencia al rango es condición necesaria.
2. **Escuchar en `0.0.0.0` invalida el método.** Es la trampa seria: si el
   bridge acepta por cualquier interfaz, un vecino de la LAN puede ponerse una
   IP del rango CGNAT, conectar por la LAN, y `whois` diría que es el móvil.
   La verificación SÓLO vale atada a la dirección del tailnet.
3. **Mismo tailnet no es mismo usuario.** Un tailnet compartido tiene nodos de
   otras cuentas; sólo valen los nuestros.
4. **Fallo cerrado y con motivo.** `tailscaled` caído, respuesta rara o vacía
   ⇒ se rechaza, y se dice por qué. Un "no lo sé" que se lee como "adelante"
   es el defecto que esta auditoría lleva una semana arrancando.
"""

from __future__ import annotations

import json

import pytest

from atlas.api.tailnet_identity import (
    TailnetIdentity,
    TailnetUnavailable,
    bind_permite_identidad_de_tailnet,
    es_direccion_de_tailnet,
)

_YO = "tomas.asin.gonzalez@gmail.com"
_MOVIL = "100.113.135.34"

_WHOIS_MOVIL = {
    "Node": {
        "Name": "redmi-note-13.tail1cc8de.ts.net.",
        "StableID": "nTpF7HUZS511CNTRL",
        "Tags": None,
    },
    "UserProfile": {"LoginName": _YO},
}


def _identidad(respuestas: dict[str, object] | None = None, *, falla: Exception | None = None):
    """`TailnetIdentity` con el transporte inyectado — nunca toca el socket real."""
    llamadas: list[str] = []

    def transporte(path: str) -> str:
        llamadas.append(path)
        if falla is not None:
            raise falla
        for clave, valor in (respuestas or {}).items():
            if clave in path:
                return json.dumps(valor)
        raise AssertionError(f"ruta no prevista en el test: {path}")

    ident = TailnetIdentity(transport=transporte, login_propio=_YO)
    return ident, llamadas


# ---------------------------------------------------------------------------
# 1. El rango se comprueba antes de preguntar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ip",
    [
        "100.113.135.34",  # CGNAT 100.64.0.0/10, que es lo que usa Tailscale
        "100.64.0.1",
        "100.127.255.254",
        "fd7a:115c:a1e0::d234:8724",  # ULA del tailnet
    ],
)
def test_reconoce_las_direcciones_del_tailnet(ip: str) -> None:
    assert es_direccion_de_tailnet(ip) is True


@pytest.mark.parametrize(
    "ip",
    [
        "192.168.1.50",  # LAN
        "10.0.0.5",
        "127.0.0.1",
        "8.8.8.8",
        "100.63.255.255",  # justo por debajo del rango
        "100.128.0.0",  # justo por encima
        "fd00::1",  # ULA que NO es la de Tailscale
        "",
        "no-es-una-ip",
    ],
)
def test_lo_que_no_es_del_tailnet_se_reconoce_como_tal(ip: str) -> None:
    assert es_direccion_de_tailnet(ip) is False


def test_una_ip_de_la_lan_ni_se_consulta() -> None:
    """No es sólo eficiencia: deja escrito que pertenecer al rango es condición
    necesaria, no una comprobación redundante que alguien pueda quitar."""
    ident, llamadas = _identidad()

    assert ident.verificar_peer("192.168.1.50") is None
    assert llamadas == []


# ---------------------------------------------------------------------------
# 2. La trampa seria: escuchar en 0.0.0.0 invalida el método
# ---------------------------------------------------------------------------


def test_escuchar_en_todas_las_interfaces_invalida_la_identidad_de_tailnet() -> None:
    """Si el bridge acepta por cualquier interfaz, un vecino de la LAN puede
    asignarse una IP del rango CGNAT, conectar por la LAN y hacerse pasar por
    el móvil: `whois` responderá que esa IP es el móvil, porque lo es EN EL
    TAILNET. La verificación sólo vale si los paquetes no pueden llegar por
    otra vía."""
    assert bind_permite_identidad_de_tailnet("0.0.0.0") is False
    assert bind_permite_identidad_de_tailnet("::") is False
    assert bind_permite_identidad_de_tailnet("192.168.1.10") is False


def test_atado_a_la_direccion_del_tailnet_si_vale() -> None:
    assert bind_permite_identidad_de_tailnet("100.85.236.58") is True
    assert bind_permite_identidad_de_tailnet("fd7a:115c:a1e0::8334:ec3a") is True


def test_loopback_no_necesita_identidad_de_tailnet_pero_no_la_rompe() -> None:
    """Loopback ya tiene su propio camino en el bridge; aquí sólo se declara
    que no habilita el método (no llegan peers del tailnet por loopback)."""
    assert bind_permite_identidad_de_tailnet("127.0.0.1") is False


# ---------------------------------------------------------------------------
# 3. Mismo tailnet no es mismo usuario
# ---------------------------------------------------------------------------


def test_un_peer_nuestro_se_acepta_con_su_identidad() -> None:
    ident, _ = _identidad({"whois": _WHOIS_MOVIL})

    peer = ident.verificar_peer(_MOVIL)

    assert peer is not None
    assert peer.node_name == "redmi-note-13.tail1cc8de.ts.net"
    assert peer.node_id == "nTpF7HUZS511CNTRL"
    assert peer.login_name == _YO


def test_un_peer_de_OTRA_cuenta_del_mismo_tailnet_se_rechaza() -> None:
    """Un tailnet puede tener nodos compartidos de otras cuentas. Estar en la
    malla no basta: tiene que ser nuestro."""
    ajeno = {**_WHOIS_MOVIL, "UserProfile": {"LoginName": "otra.persona@example.com"}}
    ident, _ = _identidad({"whois": ajeno})

    assert ident.verificar_peer(_MOVIL) is None


def test_un_nodo_etiquetado_se_rechaza_por_defecto() -> None:
    """Los nodos con `tags` son servicios/CI, no el dispositivo de una persona;
    su login es un `tagged-devices` sintético. Denegar por defecto."""
    etiquetado = {
        "Node": {"Name": "ci-runner.ts.net.", "StableID": "X", "Tags": ["tag:ci"]},
        "UserProfile": {"LoginName": _YO},
    }
    ident, _ = _identidad({"whois": etiquetado})

    assert ident.verificar_peer(_MOVIL) is None


# ---------------------------------------------------------------------------
# 4. Fallo cerrado, y con motivo
# ---------------------------------------------------------------------------


def test_si_tailscaled_no_responde_se_rechaza() -> None:
    ident, _ = _identidad(falla=OSError("connection refused"))

    assert ident.verificar_peer(_MOVIL) is None


def test_el_motivo_del_fallo_queda_disponible_no_se_traga() -> None:
    """Rechazar en silencio hace indistinguible 'tailscaled caído' de 'ese peer
    no es tuyo', que son dos incidencias muy distintas para quien opera."""
    ident, _ = _identidad(falla=OSError("connection refused"))

    with pytest.raises(TailnetUnavailable) as exc:
        ident.whois(_MOVIL)

    assert "connection refused" in str(exc.value)


@pytest.mark.parametrize(
    "respuesta",
    [
        {},
        {"Node": {}},
        {"Node": {"Name": "x"}},  # sin StableID
        {"UserProfile": {"LoginName": _YO}},  # sin Node
        {"Node": {"Name": "x", "StableID": "y"}},  # sin UserProfile
        {"Node": {"Name": "x", "StableID": "y"}, "UserProfile": {"LoginName": ""}},
    ],
)
def test_una_respuesta_incompleta_no_autentica_a_nadie(respuesta: dict) -> None:
    ident, _ = _identidad({"whois": respuesta})

    assert ident.verificar_peer(_MOVIL) is None


def test_json_corrupto_no_autentica() -> None:
    def transporte(path: str) -> str:
        return "<html>no soy json</html>"

    ident = TailnetIdentity(transport=transporte, login_propio=_YO)

    assert ident.verificar_peer(_MOVIL) is None


def test_sin_login_propio_conocido_no_se_acepta_a_nadie() -> None:
    """Si no sabemos quiénes somos no podemos comparar, y comparar contra
    `None` aceptaría a cualquiera."""
    ident = TailnetIdentity(
        transport=lambda p: json.dumps(_WHOIS_MOVIL), login_propio=None
    )

    assert ident.verificar_peer(_MOVIL) is None


# ---------------------------------------------------------------------------
# 5. La consulta se hace como manda la LocalAPI
# ---------------------------------------------------------------------------


def test_la_consulta_lleva_puerto_porque_la_localapi_lo_exige() -> None:
    ident, llamadas = _identidad({"whois": _WHOIS_MOVIL})

    ident.verificar_peer(_MOVIL)

    assert llamadas == [f"/localapi/v0/whois?addr={_MOVIL}%3A0"]


def test_una_ip_v6_se_consulta_entre_corchetes() -> None:
    """`addr` es `host:port`; sin corchetes, los dos puntos de una IPv6 hacen
    que la LocalAPI la parsee mal."""
    ident, llamadas = _identidad({"whois": _WHOIS_MOVIL})

    ident.verificar_peer("fd7a:115c:a1e0::d234:8724")

    assert llamadas == ["/localapi/v0/whois?addr=%5Bfd7a%3A115c%3Aa1e0%3A%3Ad234%3A8724%5D%3A0"]


def test_un_404_es_un_no_limpio_no_una_averia() -> None:
    """`no match for IP:port` significa "esa IP no es de nadie" — respuesta
    negativa NORMAL. Tratarla como avería confunde 'tailscaled caído' con 'ese
    peer no existe' y llena el log de avisos cada vez que alguien sondea una IP
    del rango. Detectado ejecutando contra el demonio real, no leyendo código.
    """
    ident, _ = _identidad({"whois": None})  # el transporte real manda "null" en un 404

    assert ident.verificar_peer("100.64.0.99") is None
    assert ident.whois("100.64.0.99") is None  # y NO lanza
