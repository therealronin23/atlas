"""La identidad de tailnet, cableada DENTRO del bridge (ADC-WO-111).

`tests/test_tailnet_identity.py` prueba el módulo. Esto prueba la costura: que
el bridge lo llama, que por defecto no cambia nada, y que la relajación del
bind no abre más de lo que dice abrir.

El invariante que más importa está en
`test_atado_a_todas_las_interfaces_sigue_exigiendo_token`: la identidad de
tailnet se deduce de la IP de origen, y eso sólo vale si los paquetes no pueden
entrar por otra interfaz. Con `0.0.0.0` un vecino de la LAN puede asignarse una
IP del rango CGNAT y `whois` confirmará que es el móvil — porque lo es, en el
tailnet. Por eso el bind se comprueba contra la dirección REAL del socket y
nunca contra la cabecera `Host`, que la pone quien llama.
"""

from __future__ import annotations

import pytest

from atlas.api import server

_TAILNET_IP = "100.113.135.34"
_BIND_TAILNET = "100.85.236.58"
_TOKEN_FUERTE = "z" * 40


@pytest.fixture(autouse=True)
def _bind_por_defecto(monkeypatch):
    """Cada test declara su propio bind; el de fábrica es loopback."""
    monkeypatch.setattr(server, "_BIND_HOST", "127.0.0.1")


def _falso_peer(monkeypatch, *, resuelve: bool = True) -> None:
    """Sustituye `tailscaled` sin tocar el socket real."""
    class _Peer:
        node_id = "nTpF7HUZS511CNTRL"

    class _Ident:
        def __init__(self, **_kw) -> None: pass
        def verificar_peer(self, _ip): return _Peer() if resuelve else None

    import atlas.api.tailnet_identity as ti

    monkeypatch.setattr(ti, "TailnetIdentity", _Ident)
    monkeypatch.setattr(ti, "login_local", lambda *_a, **_k: "yo@example.com")


# ---------------------------------------------------------------------------
# Por defecto no cambia nada
# ---------------------------------------------------------------------------


def test_apagado_por_defecto_un_peer_del_tailnet_no_entra(monkeypatch) -> None:
    """Sin la variable, el bridge se comporta exactamente como antes."""
    monkeypatch.delenv(server.TAILNET_IDENTITY_ENV, raising=False)
    _falso_peer(monkeypatch)
    monkeypatch.setattr(server, "_BIND_HOST", _BIND_TAILNET)

    assert server._tailnet_identity(_TAILNET_IP) is None


def test_apagado_por_defecto_el_bind_fuera_de_loopback_sigue_exigiendo_token(
    monkeypatch,
) -> None:
    monkeypatch.delenv(server.TAILNET_IDENTITY_ENV, raising=False)
    monkeypatch.delenv(server.AUTH_TOKEN_ENV, raising=False)

    with pytest.raises(RuntimeError, match=server.AUTH_TOKEN_ENV):
        server._validate_bind_security(_BIND_TAILNET)


def test_loopback_no_se_toca(monkeypatch) -> None:
    monkeypatch.delenv(server.AUTH_TOKEN_ENV, raising=False)

    server._validate_bind_security("127.0.0.1")  # no lanza


# ---------------------------------------------------------------------------
# Encendido: la costura funciona
# ---------------------------------------------------------------------------


def test_encendido_y_atado_al_tailnet_el_peer_se_autentica(monkeypatch) -> None:
    monkeypatch.setenv(server.TAILNET_IDENTITY_ENV, "1")
    monkeypatch.setattr(server, "_BIND_HOST", _BIND_TAILNET)
    _falso_peer(monkeypatch)

    assert server._tailnet_identity(_TAILNET_IP) == "atlas-tailnet:nTpF7HUZS511CNTRL"


def test_la_identidad_auditada_es_el_id_estable_no_la_ip(monkeypatch) -> None:
    """La IP del momento no sirve en el ledger: el nodo puede cambiarla. El
    `StableID` identifica al dispositivo aunque se renombre o se mueva."""
    monkeypatch.setenv(server.TAILNET_IDENTITY_ENV, "1")
    monkeypatch.setattr(server, "_BIND_HOST", _BIND_TAILNET)
    _falso_peer(monkeypatch)

    identidad = server._tailnet_identity(_TAILNET_IP)

    assert identidad is not None
    assert _TAILNET_IP not in identidad
    assert identidad.startswith("atlas-tailnet:")


def test_un_peer_que_tailscaled_no_reconoce_no_entra(monkeypatch) -> None:
    monkeypatch.setenv(server.TAILNET_IDENTITY_ENV, "1")
    monkeypatch.setattr(server, "_BIND_HOST", _BIND_TAILNET)
    _falso_peer(monkeypatch, resuelve=False)

    assert server._tailnet_identity(_TAILNET_IP) is None


def test_encendido_permite_atar_a_una_direccion_del_tailnet_sin_token(
    monkeypatch,
) -> None:
    monkeypatch.setenv(server.TAILNET_IDENTITY_ENV, "1")
    monkeypatch.delenv(server.AUTH_TOKEN_ENV, raising=False)
    _falso_peer(monkeypatch)

    server._validate_bind_security(_BIND_TAILNET)  # no lanza


# ---------------------------------------------------------------------------
# La trampa: encender NO habilita cualquier bind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bind", ["0.0.0.0", "::", "192.168.1.10"])
def test_atado_a_todas_las_interfaces_sigue_exigiendo_token(
    monkeypatch, bind: str
) -> None:
    """El invariante que sostiene todo el método. Con `0.0.0.0` la IP de origen
    deja de ser prueba de nada: un vecino de la LAN puede ponerse una del rango
    CGNAT y `whois` confirmará que es el móvil."""
    monkeypatch.setenv(server.TAILNET_IDENTITY_ENV, "1")
    monkeypatch.delenv(server.AUTH_TOKEN_ENV, raising=False)
    _falso_peer(monkeypatch)

    with pytest.raises(RuntimeError, match=server.AUTH_TOKEN_ENV):
        server._validate_bind_security(bind)


@pytest.mark.parametrize("bind", ["0.0.0.0", "192.168.1.10", "127.0.0.1"])
def test_con_un_bind_que_no_es_del_tailnet_no_se_autentica_por_identidad(
    monkeypatch, bind: str
) -> None:
    """Aunque el proceso arrancara con token y bind abierto, la vía de tailnet
    no se aplica: son dos comprobaciones distintas y ninguna cubre a la otra."""
    monkeypatch.setenv(server.TAILNET_IDENTITY_ENV, "1")
    monkeypatch.setattr(server, "_BIND_HOST", bind)
    _falso_peer(monkeypatch)

    assert server._tailnet_identity(_TAILNET_IP) is None


def test_sin_cuenta_local_legible_el_arranque_falla_en_vez_de_abrir(
    monkeypatch,
) -> None:
    """Si no sabemos quiénes somos no podemos comparar. Fallar al arrancar es
    correcto; arrancar aceptando a cualquiera del rango, no."""
    monkeypatch.setenv(server.TAILNET_IDENTITY_ENV, "1")
    monkeypatch.delenv(server.AUTH_TOKEN_ENV, raising=False)
    import atlas.api.tailnet_identity as ti

    monkeypatch.setattr(ti, "login_local", lambda *_a, **_k: None)

    with pytest.raises(RuntimeError, match="tailscaled"):
        server._validate_bind_security(_BIND_TAILNET)


# ---------------------------------------------------------------------------
# El token sigue mandando donde mandaba
# ---------------------------------------------------------------------------


def test_un_token_valido_sigue_autenticando_sin_tocar_el_tailnet(monkeypatch) -> None:
    monkeypatch.setenv(server.AUTH_TOKEN_ENV, _TOKEN_FUERTE)
    from starlette.datastructures import Headers

    identidad = server._authenticate_client(
        "203.0.113.9", Headers({"authorization": f"Bearer {_TOKEN_FUERTE}"})
    )

    assert identidad.startswith("atlas-token:")


def test_un_token_invalido_no_cae_a_la_via_de_tailnet(monkeypatch) -> None:
    """Presentar una credencial mala es un rechazo, no una invitación a probar
    el siguiente método de autenticación."""
    monkeypatch.setenv(server.AUTH_TOKEN_ENV, _TOKEN_FUERTE)
    monkeypatch.setenv(server.TAILNET_IDENTITY_ENV, "1")
    monkeypatch.setattr(server, "_BIND_HOST", _BIND_TAILNET)
    _falso_peer(monkeypatch)
    from starlette.datastructures import Headers

    with pytest.raises(server._AuthenticationError):
        server._authenticate_client(
            _TAILNET_IP, Headers({"authorization": "Bearer equivocado"})
        )
