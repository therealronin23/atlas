"""Tests for SSRFBridge — SEC-1 hardening."""

from __future__ import annotations

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


# ---------------------------------------------------------------------------
# SEC-1: blocklist ANTES de allowlist
# ---------------------------------------------------------------------------


class TestBlocklistBeforeAllowlist:
    def test_localhost_blocked_even_if_extra_allowed(self) -> None:
        """BLOCKED_DOMAINS no puede ser anulado via extra_allowed."""
        bridge = SSRFBridge(extra_allowed={"localhost"})
        result = bridge.check("http://localhost:8080/")
        assert not result.allowed

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
