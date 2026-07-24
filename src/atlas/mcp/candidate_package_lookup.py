"""Etapa 2A (parte 1) de ADR-075 — verificación de metadata de paquete real.

Antes de descargar el artefacto binario de un candidato ``stdio`` (parte 2,
no construida aquí), confirma que el paquete declarado por el registro MCP
(``registryType``/``identifier``/``version``, capturado por
``registry_seed.py``) EXISTE de verdad y que la versión sigue publicada --
señal honesta de drift/staleness (una entrada del registro puede apuntar a
una versión retirada o nunca publicada).

Mismo patrón que el resto del proyecto (``HttpApiSource``/``Fetcher``,
SSRFBridge fail-closed): esto es JSON de metadata, cabe en el ``Fetcher`` de
texto ya existente. La descarga del artefacto binario (.whl/.tar.gz/.tgz) NO
cabe ahí (decodificar binario como UTF-8 lo corrompe) -- es trabajo aparte.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from atlas.knowledge.sources import Fetcher, HttpApiSource
from atlas.security.ssrf_bridge import SSRFBridge

_PYPI_HOST = "pypi.org"
_NPM_HOST = "registry.npmjs.org"


@dataclass(frozen=True)
class PackageLookupResult:
    exists: bool
    version_matches: bool
    download_url: str
    sha256: str
    reason: str


def _empty(reason: str) -> PackageLookupResult:
    return PackageLookupResult(exists=False, version_matches=False, download_url="", sha256="", reason=reason)


def lookup_pypi_package(identifier: str, version: str, *, fetcher: Fetcher | None = None) -> PackageLookupResult:
    """``pypi.org`` ya está en la allowlist curada de SSRFBridge (ADR-039) --
    no hace falta ninguna instancia efímera aquí."""
    src = HttpApiSource("pypi-lookup", "mcp/package-lookup", bridge=SSRFBridge(), fetcher=fetcher)
    rec = src.fetch(f"https://{_PYPI_HOST}/pypi/{identifier}/{version}/json")[0]
    if rec.status == 404:
        return _empty(f"paquete/versión no encontrado en PyPI: {identifier}=={version}")
    if rec.status != 200:
        return _empty(f"PyPI respondió {rec.status}")
    try:
        data = json.loads(rec.payload)
    except json.JSONDecodeError:
        return _empty("respuesta de PyPI no es JSON válido")

    real_version = str((data.get("info") or {}).get("version", ""))
    version_matches = real_version == version
    sdist = next(
        (u for u in data.get("urls", []) if u.get("packagetype") == "sdist"),
        next(iter(data.get("urls", [])), None),
    )
    if not version_matches or sdist is None:
        return PackageLookupResult(
            exists=True, version_matches=version_matches, download_url="", sha256="",
            reason=f"versión pedida {version!r} no coincide con la publicada {real_version!r}" if not version_matches
            else "sin ficheros descargables para esta versión",
        )
    return PackageLookupResult(
        exists=True, version_matches=True,
        download_url=str(sdist.get("url", "")),
        sha256=str((sdist.get("digests") or {}).get("sha256", "")),
        reason="ok",
    )


def lookup_npm_package(identifier: str, version: str, *, fetcher: Fetcher | None = None) -> PackageLookupResult:
    """``registry.npmjs.org`` NO está en la allowlist por defecto -- se añade
    aquí como registro público bien conocido de propósito específico (fetch de
    metadata/artefactos, nunca ``npm install``), mismo criterio ya aplicado a
    ``pypi.org``/``files.pythonhosted.org``. Distinto del problema de los 1869
    dominios de candidatos individuales: esto es UN registro global, no un
    tercero arbitrario por candidato."""
    src = HttpApiSource(
        "npm-lookup", "mcp/package-lookup",
        bridge=SSRFBridge(extra_allowed={_NPM_HOST}), fetcher=fetcher,
    )
    rec = src.fetch(f"https://{_NPM_HOST}/{identifier}")[0]
    if rec.status == 404:
        return _empty(f"paquete no encontrado en npm: {identifier}")
    if rec.status != 200:
        return _empty(f"npm respondió {rec.status}")
    try:
        data = json.loads(rec.payload)
    except json.JSONDecodeError:
        return _empty("respuesta de npm no es JSON válido")

    versions = data.get("versions") or {}
    entry = versions.get(version)
    if entry is None:
        return PackageLookupResult(
            exists=True, version_matches=False, download_url="", sha256="",
            reason=f"versión {version!r} no publicada (disponibles: {sorted(versions)[:5]!r})",
        )
    dist = entry.get("dist") or {}
    return PackageLookupResult(
        exists=True, version_matches=True,
        download_url=str(dist.get("tarball", "")),
        sha256=str(dist.get("shasum", "")),
        reason="ok",
    )


_LookupFn = Callable[..., PackageLookupResult]
_DISPATCH: dict[str, _LookupFn] = {"pypi": lookup_pypi_package, "npm": lookup_npm_package}


def lookup_package(registry: str, identifier: str, version: str, *, fetcher: Fetcher | None = None) -> PackageLookupResult:
    """Fail-closed (I6): un ``registryType`` que no sea pypi/npm no se asume
    fetchable -- se rechaza explícito en vez de intentar adivinar."""
    fn = _DISPATCH.get(registry)
    if fn is None:
        return _empty(f"registryType no soportado: {registry!r}")
    return fn(identifier, version, fetcher=fetcher)
