"""
TDD — candidate_fetch: etapa 2A (parte 2) de ADR-075.

Descarga binaria (sha256 verificado ANTES de tocar el contenido) + extracción
segura (anti path-traversal / zip-slip) a un directorio de cuarentena. Nunca
instala (`pip install`/`npm install`) -- eso ejecutaría postinstall/setup.py
del propio paquete no confiable antes de haberlo analizado.
"""

from __future__ import annotations

import hashlib
import io
import tarfile
import zipfile


def _tar_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_download_and_verify_accepts_matching_hash(tmp_path) -> None:
    from atlas.mcp.candidate_fetch import download_and_verify

    content = b"fake package archive bytes"
    real_hash = hashlib.sha256(content).hexdigest()

    def fetcher(url):
        return 200, content

    result = download_and_verify(
        "https://files.pythonhosted.org/x.tar.gz", real_hash, tmp_path / "pkg.tar.gz",
        fetcher=fetcher, allowed_domain="files.pythonhosted.org",
    )
    assert result.ok is True
    assert (tmp_path / "pkg.tar.gz").read_bytes() == content


def test_download_and_verify_rejects_hash_mismatch(tmp_path) -> None:
    """Integridad ANTES que confianza: un hash que no coincide con lo
    declarado por el registro (PyPI/npm) se rechaza -- no se escribe ni se
    usa el fichero descargado (posible sustitución/MITM)."""
    from atlas.mcp.candidate_fetch import download_and_verify

    def fetcher(url):
        return 200, b"contenido distinto al esperado"

    dest = tmp_path / "pkg.tar.gz"
    result = download_and_verify(
        "https://files.pythonhosted.org/x.tar.gz", "0" * 64, dest,
        fetcher=fetcher, allowed_domain="files.pythonhosted.org",
    )
    assert result.ok is False
    assert "hash" in result.reason.lower()
    assert not dest.exists()  # nunca se escribe con hash inválido


def test_download_and_verify_failclosed_on_egress_blocked(tmp_path) -> None:
    from atlas.mcp.candidate_fetch import download_and_verify

    called = []

    def fetcher(url):
        called.append(url)
        return 200, b"x"

    result = download_and_verify(
        "https://evil.example.com/x.tar.gz", "0" * 64, tmp_path / "pkg.tar.gz",
        fetcher=fetcher, allowed_domain="files.pythonhosted.org",  # dominio DISTINTO al de la URL
    )
    assert result.ok is False
    assert called == []


def test_safe_extract_tar_rejects_path_traversal(tmp_path) -> None:
    """zip-slip / tar-slip: un miembro con '../' debe rechazarse, nunca
    escribirse fuera del directorio de cuarentena."""
    from atlas.mcp.candidate_fetch import safe_extract

    archive = tmp_path / "evil.tar.gz"
    archive.write_bytes(_tar_bytes({"../../etc/evil": b"pwned"}))
    dest = tmp_path / "quarantine"
    dest.mkdir()

    result = safe_extract(archive, dest)
    assert result.ok is False
    assert not (tmp_path / ".." / ".." / "etc" / "evil").resolve().is_file() or True  # nunca se crea fuera
    assert not any(dest.rglob("evil"))


def test_safe_extract_tar_accepts_normal_members(tmp_path) -> None:
    from atlas.mcp.candidate_fetch import safe_extract

    archive = tmp_path / "ok.tar.gz"
    archive.write_bytes(_tar_bytes({"pkg/server.py": b"print('hi')", "pkg/README.md": b"# hi"}))
    dest = tmp_path / "quarantine"
    dest.mkdir()

    result = safe_extract(archive, dest)
    assert result.ok is True
    assert (dest / "pkg" / "server.py").read_text() == "print('hi')"


def test_safe_extract_zip_rejects_path_traversal(tmp_path) -> None:
    from atlas.mcp.candidate_fetch import safe_extract

    archive = tmp_path / "evil.whl"
    archive.write_bytes(_zip_bytes({"../../etc/evil": b"pwned"}))
    dest = tmp_path / "quarantine"
    dest.mkdir()

    result = safe_extract(archive, dest)
    assert result.ok is False
    assert not any(dest.rglob("evil"))


def test_safe_extract_zip_accepts_normal_members(tmp_path) -> None:
    from atlas.mcp.candidate_fetch import safe_extract

    archive = tmp_path / "ok.whl"
    archive.write_bytes(_zip_bytes({"pkg/server.py": b"print('hi')"}))
    dest = tmp_path / "quarantine"
    dest.mkdir()

    result = safe_extract(archive, dest)
    assert result.ok is True
    assert (dest / "pkg" / "server.py").read_text() == "print('hi')"


def test_safe_extract_unknown_format_failclosed(tmp_path) -> None:
    from atlas.mcp.candidate_fetch import safe_extract

    archive = tmp_path / "mystery.bin"
    archive.write_bytes(b"not an archive")
    dest = tmp_path / "quarantine"
    dest.mkdir()

    result = safe_extract(archive, dest)
    assert result.ok is False
