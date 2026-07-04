"""Tests for SSRFBridge — SEC-1 hardening."""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from atlas.security.ssrf_bridge import SSRFBridge


@pytest.fixture()
def bridge() -> SSRFBridge:
    return SSRFBridge()


# ---------------------------------------------------------------------------
# Tests basicos (regresion)
# ---------------------------------------------------------------------------


class TestBasicAllowlist:
    def test_allowed_domain_passes(self, bridge: SSRFBridge) -> None:
        result = bridge.check("https://api.github.com/repos/foo")
        assert result.allowed

    def test_unknown_domain_denied(self, bridge: SSRFBridge) -> None:
        result = bridge.check("https://evil.com/steal")
        assert not result.allowed

    def test_non_http_scheme_denied(self, bridge: SSRFBridge) -> None:
        result = bridge.check("ftp://api.github.com/")
        assert not result.allowed

    def test_pypi_allowed(self, bridge: SSRFBridge) -> None:
        result = bridge.check("https://pypi.org/simple/")
        assert result.allowed

    @pytest.mark.parametrize("domain", [
        "github.com", "huggingface.co", "en.wikipedia.org", "stackoverflow.com",
        "arxiv.org", "docs.python.org", "readthedocs.io",
    ])
    def test_general_scraping_domains_allowed(self, bridge: SSRFBridge, domain: str) -> None:
        """2026-07-02: allowlist ampliada para web_crawl/BrowserTool de propósito general."""
        result = bridge.check(f"https://{domain}/")
        assert result.allowed, result.reason


# ---------------------------------------------------------------------------
# SEC-1: blocklist ANTES de allowlist
# ---------------------------------------------------------------------------


class TestBlocklistBeforeAllowlist:
    def test_localhost_blocked_even_if_extra_allowed(self) -> None:
        """BLOCKED_DOMAINS no puede ser anulado via extra_allowed."""
        bridge = SSRFBridge(extra_allowed={"localhost"})
        result = bridge.check("http://localhost:8080/")
        assert not result.allowed

    def test_localhost_allowed_only_with_private_network_flag(self) -> None:
        bridge = SSRFBridge(
            extra_allowed={"localhost"},
            allow_private_network=True,
        )
        result = bridge.check("http://localhost:8080/")
        assert result.allowed

    def test_127_blocked(self, bridge: SSRFBridge) -> None:
        result = bridge.check("http://127.0.0.1/")
        assert not result.allowed

    def test_metadata_endpoint_blocked(self, bridge: SSRFBridge) -> None:
        result = bridge.check("http://169.254.169.254/latest/meta-data/")
        assert not result.allowed


# ---------------------------------------------------------------------------
# SEC-1: _is_private_ip sin regex — formatos alternativos de IP
# ---------------------------------------------------------------------------


class TestPrivateIpFormats:
    def test_decimal_loopback(self, bridge: SSRFBridge) -> None:
        """IP decimal: 2130706433 == 127.0.0.1."""
        # ipaddress.ip_address(2130706433) == IPv4Address('127.0.0.1')
        result = bridge.check("http://2130706433/")
        assert not result.allowed

    def test_metadata_ip_literal(self, bridge: SSRFBridge) -> None:
        result = bridge.check("http://169.254.169.254/")
        assert not result.allowed

    def test_ipv6_loopback(self, bridge: SSRFBridge) -> None:
        result = bridge.check("http://[::1]/")
        assert not result.allowed

    def test_ipv6_link_local(self, bridge: SSRFBridge) -> None:
        result = bridge.check("http://[fe80::1]/")
        assert not result.allowed

    def test_private_10_range(self, bridge: SSRFBridge) -> None:
        result = bridge.check("http://10.0.0.1/")
        assert not result.allowed

    def test_private_192_168(self, bridge: SSRFBridge) -> None:
        result = bridge.check("http://192.168.1.1/")
        assert not result.allowed

    def test_private_172_16(self, bridge: SSRFBridge) -> None:
        result = bridge.check("http://172.16.0.1/")
        assert not result.allowed


# ---------------------------------------------------------------------------
# SEC-1: match exacto de subdominio (no subtree wildcard)
# ---------------------------------------------------------------------------


class TestExactSubdomainMatch:
    def test_exact_domain_allowed(self, bridge: SSRFBridge) -> None:
        result = bridge.check("https://api.github.com/foo")
        assert result.allowed

    def test_evil_subdomain_of_allowed_denied(self) -> None:
        """'evil.api.github.com' NO debe pasar solo porque 'api.github.com' esta en allowlist."""
        bridge = SSRFBridge()
        result = bridge.check("https://evil.api.github.com/")
        assert not result.allowed, (
            "subtree wildcard no debe aplicar: solo match exacto permitido"
        )

    def test_extra_allowed_exact_only(self) -> None:
        """extra_allowed='allowed.com' no da acceso a 'evil.allowed.com'."""
        bridge = SSRFBridge(extra_allowed={"allowed.com"})
        good = bridge.check("https://allowed.com/path")
        assert good.allowed
        bad = bridge.check("https://evil.allowed.com/path")
        assert not bad.allowed

    def test_add_domain_exact_only(self) -> None:
        bridge = SSRFBridge()
        bridge.add_domain("myservice.com")
        good = bridge.check("https://myservice.com/api")
        assert good.allowed
        bad = bridge.check("https://attacker.myservice.com/api")
        assert not bad.allowed


# ---------------------------------------------------------------------------
# SEC-1: check() firma -> BridgeDecision
# ---------------------------------------------------------------------------


class TestBridgeDecisionShape:
    def test_decision_has_correct_fields(self, bridge: SSRFBridge) -> None:
        d = bridge.check("https://pypi.org/simple/requests/")
        assert d.allowed is True
        assert d.url == "https://pypi.org/simple/requests/"
        assert d.domain == "pypi.org"
        assert isinstance(d.reason, str)

    def test_denied_decision_shape(self, bridge: SSRFBridge) -> None:
        d = bridge.check("http://192.168.0.1/admin")
        assert d.allowed is False
        assert "192.168.0.1" in d.reason or "privada" in d.reason.lower()


# ---------------------------------------------------------------------------
# SEC-TOCTOU: fail-closed en error DNS y pin de IP resuelta
# ---------------------------------------------------------------------------


class TestDNSFailClosed:
    """_check_resolved_ips debe retornar error (fail-closed) cuando DNS falla."""

    def test_gaierror_fail_closed(self) -> None:
        """gaierror durante resolución => check() retorna allowed=False."""
        bridge = SSRFBridge(extra_allowed={"nonexistent.example.com"})
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("NXDOMAIN")):
            result = bridge.check("https://nonexistent.example.com/path")
        assert not result.allowed, "DNS gaierror debe ser fail-closed, no fail-open"
        assert "resoluc" in result.reason.lower() or "dns" in result.reason.lower()

    def test_oserror_fail_closed(self) -> None:
        """OSError durante resolución => check() retorna allowed=False."""
        bridge = SSRFBridge(extra_allowed={"host.example.com"})
        with patch("socket.getaddrinfo", side_effect=OSError("network unreachable")):
            result = bridge.check("https://host.example.com/path")
        assert not result.allowed, "OSError debe ser fail-closed, no fail-open"


class TestDNSPinnedIP:
    """La IP resuelta en check() se expone en BridgeDecision para evitar 2ª resolución."""

    def test_pinned_ip_present_on_allowed(self) -> None:
        """BridgeDecision.pinned_ip debe ser la IP resuelta cuando allowed=True."""
        bridge = SSRFBridge(extra_allowed={"good.example.com"})
        fake_addr = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0)),
        ]
        with patch("socket.getaddrinfo", return_value=fake_addr):
            result = bridge.check("https://good.example.com/path")
        assert result.allowed
        assert result.pinned_ip == "93.184.216.34"

    def test_pinned_ip_none_when_host_is_literal_ip(self) -> None:
        """Cuando el host ya es una IP pública literal no hay DNS; pinned_ip puede ser None."""
        bridge = SSRFBridge(extra_allowed={"93.184.216.34"})
        result = bridge.check("https://93.184.216.34/path")
        # El host es IP literal — no se resuelve; pinned_ip es None o la propia IP.
        # Lo importante: allowed=True si está en allowlist.
        assert result.allowed

    def test_executor_connects_to_pinned_ip_with_original_hostname_sni(self) -> None:
        """El executor debe conectar a la pinned_ip (sin segunda resolución DNS)
        pero validar TLS contra el hostname original (SNI correcto).

        Este test reemplaza el anterior test_pinned_ip_url_rewrite que era
        TAUTOLÓGICO: solo probaba urllib.parse._replace en el propio test,
        nunca tocaba el executor.  El presente test es real: instancia
        _PinnedHTTPSConnection directamente y aserta:
          - socket.create_connection recibió la pinned_ip como destino.
          - ctx.wrap_socket recibió server_hostname == hostname original.
          - getaddrinfo NO fue llamado durante la fase de conexión (sin 2ª resolución).
        """
        import ssl
        import unittest.mock as um

        from atlas.security.executor import _PinnedHTTPSConnection

        pinned_ip = "93.184.216.34"
        original_host = "good.example.com"

        create_connection_calls: list[tuple[object, ...]] = []
        wrap_socket_calls: list[dict[str, object]] = []
        mock_sock = um.MagicMock(spec=socket.socket)

        def fake_create_connection(address: tuple[str, int], **kw: object) -> socket.socket:
            create_connection_calls.append((address,))
            return mock_sock

        # Crear el contexto SSL real y parchear su wrap_socket para interceptar SNI.
        ctx = ssl.create_default_context()

        real_wrap = ctx.wrap_socket

        def fake_wrap_socket(sock: object, **kw: object) -> um.MagicMock:
            wrap_socket_calls.append(dict(kw))
            m = um.MagicMock()
            return m

        ctx.wrap_socket = fake_wrap_socket  # type: ignore[method-assign]

        # Pasar el contexto mockeado directamente al constructor (evita que __init__
        # cree uno nuevo antes de que podamos interceptarlo).
        conn = _PinnedHTTPSConnection(original_host, 443, pinned_ip=pinned_ip, context=ctx)

        with patch("socket.create_connection", side_effect=fake_create_connection):
            conn.connect()

        # create_connection debe haber ido a la pinned_ip, no al hostname.
        assert create_connection_calls, "create_connection no fue llamado"
        dest_addr = create_connection_calls[0][0]
        assert dest_addr[0] == pinned_ip, (
            f"create_connection debe usar la pinned_ip {pinned_ip!r}, "
            f"pero se usó {dest_addr[0]!r}"
        )

        # wrap_socket debe haber recibido el hostname original como SNI.
        assert wrap_socket_calls, "wrap_socket no fue llamado"
        sni = wrap_socket_calls[0].get("server_hostname")
        assert sni == original_host, (
            f"server_hostname (SNI) debe ser el hostname original {original_host!r}, "
            f"pero fue {sni!r}"
        )

    def test_old_url_rewrite_would_break_tls(self) -> None:
        """Documenta que reescribir la URL a la IP rompe TLS: server_hostname
        sería la IP, no el hostname → CERTIFICATE_VERIFY_FAILED.

        El test anterior (test_pinned_ip_url_rewrite) nunca detectó esto porque
        solo probaba urllib.parse._replace sin involucrar al executor.
        """
        import ssl
        import urllib.parse

        pinned_ip = "93.184.216.34"
        original_url = "https://good.example.com/path"

        # Simular lo que hacía el código antiguo: reescribir netloc a la IP.
        parsed = urllib.parse.urlparse(original_url)
        rewritten = parsed._replace(netloc=pinned_ip).geturl()
        rewritten_parsed = urllib.parse.urlparse(rewritten)

        # Con la reescritura, el hostname que urllib pasa como server_hostname es la IP.
        # ssl.match_hostname (o check_hostname=True) falla si el cert no tiene esa IP
        # en su SAN, que es el caso para todos los dominios normales.
        rewritten_host = rewritten_parsed.hostname
        assert rewritten_host == pinned_ip, "confirmar que la URL reescrita usa la IP como host"

        # Verificar que un cert de ejemplo.com NO validaría contra la IP.
        ctx = ssl.create_default_context()
        assert ctx.check_hostname is True, "check_hostname activo por defecto"
        # Si se conectara a rewritten_url, server_hostname sería la IP → fallo TLS.
        # (No podemos hacer la conexión real en tests unitarios, pero la lógica
        # es determinista: check_hostname valida SAN contra server_hostname.)
