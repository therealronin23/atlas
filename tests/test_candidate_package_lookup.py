"""
TDD — candidate_package_lookup: etapa 2A (parte 1) de ADR-075.

Verifica que el paquete declarado por un candidato stdio (registryType +
identifier + version, capturado por registry_seed.py) EXISTE de verdad en el
registro público (PyPI/npm) -- metadata JSON, mismo patrón HttpApiSource ya
usado en el proyecto (SSRFBridge fail-closed, fetcher inyectable, sin red en
tests). No descarga el artefacto binario todavía (eso es la parte 2, separada
a propósito -- JSON encaja en el Fetcher de texto existente, un .whl/.tar.gz
binario no).
"""

from __future__ import annotations

import json


def _stub_fetcher(status: int, body: str):
    def f(method, url, data, headers):
        return status, body
    return f


def test_pypi_lookup_confirms_real_package_and_version() -> None:
    from atlas.mcp.candidate_package_lookup import lookup_pypi_package

    body = json.dumps({
        "info": {"name": "adeu", "version": "1.5.2"},
        "urls": [{"url": "https://files.pythonhosted.org/packages/.../adeu-1.5.2.tar.gz",
                   "digests": {"sha256": "abc123"}, "packagetype": "sdist"}],
    })
    result = lookup_pypi_package("adeu", "1.5.2", fetcher=_stub_fetcher(200, body))
    assert result.exists is True
    assert result.version_matches is True
    assert result.download_url == "https://files.pythonhosted.org/packages/.../adeu-1.5.2.tar.gz"
    assert result.sha256 == "abc123"


def test_pypi_lookup_flags_missing_package_404() -> None:
    from atlas.mcp.candidate_package_lookup import lookup_pypi_package

    result = lookup_pypi_package("nonexistent-pkg-xyz", "1.0.0", fetcher=_stub_fetcher(404, ""))
    assert result.exists is False
    assert result.download_url == ""


def test_pypi_lookup_flags_version_mismatch() -> None:
    """El registro MCP declaró una versión que YA no está publicada (o nunca
    lo estuvo) -- señal real de drift/staleness, no un rechazo silencioso."""
    from atlas.mcp.candidate_package_lookup import lookup_pypi_package

    body = json.dumps({
        "info": {"name": "adeu", "version": "2.0.0"},  # última real != la pedida
        "urls": [],
    })
    result = lookup_pypi_package("adeu", "1.5.2", fetcher=_stub_fetcher(200, body))
    assert result.exists is True
    assert result.version_matches is False
    assert result.download_url == ""


def test_npm_lookup_confirms_real_package_and_version() -> None:
    from atlas.mcp.candidate_package_lookup import lookup_npm_package

    body = json.dumps({
        "name": "@foo/files",
        "versions": {
            "0.2.0": {
                "dist": {"tarball": "https://registry.npmjs.org/@foo/files/-/files-0.2.0.tgz",
                          "shasum": "deadbeef"}
            }
        },
    })
    result = lookup_npm_package("@foo/files", "0.2.0", fetcher=_stub_fetcher(200, body))
    assert result.exists is True
    assert result.version_matches is True
    assert result.download_url == "https://registry.npmjs.org/@foo/files/-/files-0.2.0.tgz"


def test_npm_lookup_flags_missing_version() -> None:
    from atlas.mcp.candidate_package_lookup import lookup_npm_package

    body = json.dumps({"name": "@foo/files", "versions": {"0.3.0": {"dist": {"tarball": "x", "shasum": "y"}}}})
    result = lookup_npm_package("@foo/files", "0.2.0", fetcher=_stub_fetcher(200, body))
    assert result.exists is True
    assert result.version_matches is False


def test_unknown_registry_type_fails_closed() -> None:
    from atlas.mcp.candidate_package_lookup import lookup_package

    result = lookup_package("cargo", "some-crate", "1.0.0", fetcher=_stub_fetcher(200, "{}"))
    assert result.exists is False
    assert "no soportado" in result.reason.lower()


def test_lookup_package_dispatches_by_registry_type() -> None:
    from atlas.mcp.candidate_package_lookup import lookup_package

    body = json.dumps({"info": {"name": "adeu", "version": "1.5.2"}, "urls": [
        {"url": "https://files.pythonhosted.org/x.tar.gz", "digests": {"sha256": "h"}, "packagetype": "sdist"}
    ]})
    result = lookup_package("pypi", "adeu", "1.5.2", fetcher=_stub_fetcher(200, body))
    assert result.exists is True
    assert result.download_url == "https://files.pythonhosted.org/x.tar.gz"
