"""Etapa 2A (parte 2) de ADR-075 — descarga binaria verificada + extracción segura.

Dos pasos deliberadamente separados y en este orden:

1. ``download_and_verify``: descarga los bytes crudos (NO el ``Fetcher`` de
   texto del resto del proyecto -- decodificar un .whl/.tar.gz como UTF-8 lo
   corrompe) y verifica el sha256 declarado por PyPI/npm ANTES de escribir el
   fichero a disco. Egress gated por una instancia EFÍMERA de SSRFBridge
   (mismo criterio que ``http_mcp_transport.py``).
2. ``safe_extract``: extrae tar/zip a un directorio de cuarentena rechazando
   cualquier miembro con path-traversal (zip-slip/tar-slip) -- un tarball
   adversarial puede intentar escribir fuera del directorio de cuarentena.

Nunca se invoca ``pip install``/``npm install``/``setup.py`` -- eso ejecutaría
código del propio paquete no confiable antes de haberlo analizado. Solo se
extrae el contenido crudo.
"""

from __future__ import annotations

import hashlib
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from atlas.security.ssrf_bridge import SSRFBridge

BinaryFetcher = Callable[[str], tuple[int, bytes]]


@dataclass(frozen=True)
class FetchResult:
    ok: bool
    reason: str


def download_and_verify(
    url: str,
    expected_hash: str,
    dest_path: Path,
    *,
    fetcher: BinaryFetcher,
    allowed_domain: str,
    hash_algo: str = "sha256",
) -> FetchResult:
    """Fail-closed en dos frentes: egress (SSRFBridge efímero, dominio del
    endpoint DEBE coincidir con lo esperado) e integridad (hash DEBE coincidir
    con lo declarado por el registro -- nunca se escribe con hash inválido).

    ``hash_algo`` importa de verdad: el 'shasum' legado de npm es SHA-1, no
    SHA-256 -- asumir sha256 siempre rechazaba el 100% de los paquetes npm
    legítimos como "posible sustitución" (hallazgo real, 2026-07-24, corrido
    contra el registro real). Ver ``candidate_package_lookup.hash_algo``."""
    domain = urlparse(url).hostname or ""
    bridge = SSRFBridge(extra_allowed={allowed_domain})
    decision = bridge.check(url)
    if not decision.allowed or domain != allowed_domain:
        return FetchResult(ok=False, reason=f"egress bloqueado: {decision.reason}")

    status, content = fetcher(url)
    if status != 200:
        return FetchResult(ok=False, reason=f"HTTP {status}")

    try:
        real_hash = hashlib.new(hash_algo, content).hexdigest()
    except ValueError:
        return FetchResult(ok=False, reason=f"algoritmo de hash no soportado: {hash_algo!r}")
    if real_hash != expected_hash:
        return FetchResult(
            ok=False,
            reason=f"hash {hash_algo} no coincide: esperado {expected_hash[:12]}…, real {real_hash[:12]}… (posible sustitución)",
        )

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(content)
    return FetchResult(ok=True, reason="ok")


def _is_safe_member(name: str, dest_dir: Path) -> bool:
    """Ningún miembro puede resolver fuera de ``dest_dir`` (zip-slip/tar-slip):
    rechaza paths absolutos y cualquier ``..`` que escape del destino."""
    if name.startswith("/") or name.startswith("\\"):
        return False
    resolved = (dest_dir / name).resolve()
    try:
        resolved.relative_to(dest_dir.resolve())
    except ValueError:
        return False
    return True


def safe_extract(archive_path: Path, dest_dir: Path) -> FetchResult:
    """tar.gz: usa el filtro nativo ``filter='data'`` (PEP 706, Python 3.12+)
    -- rechaza path-traversal, dispositivos especiales y permisos peligrosos
    a nivel de la propia stdlib. zip (.whl): sin filtro nativo equivalente,
    se valida cada miembro a mano antes de extraerlo."""
    name = archive_path.name.lower()
    try:
        if name.endswith(".tar.gz") or name.endswith(".tgz") or name.endswith(".tar"):
            with tarfile.open(archive_path, "r:*") as tar:
                tar.extractall(dest_dir, filter="data")
            return FetchResult(ok=True, reason="ok")
        if name.endswith(".zip") or name.endswith(".whl"):
            with zipfile.ZipFile(archive_path) as zf:
                members = zf.namelist()
                unsafe = [m for m in members if not _is_safe_member(m, dest_dir)]
                if unsafe:
                    return FetchResult(ok=False, reason=f"path-traversal rechazado: {unsafe[:3]!r}")
                zf.extractall(dest_dir)
            return FetchResult(ok=True, reason="ok")
        return FetchResult(ok=False, reason=f"formato de archivo no soportado: {archive_path.suffix!r}")
    except (tarfile.TarError, zipfile.BadZipFile) as exc:
        return FetchResult(ok=False, reason=f"archivo corrupto/malicioso: {exc}")
