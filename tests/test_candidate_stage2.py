"""
TDD — candidate_stage2: orquestación real de ADR-075 (etapas 2A/2B).

2A (stdio): lookup metadata -> descarga verificada -> extracción segura ->
descubrir entry point -> semgrep. NO incluye ejecución en sandbox (límite
reconocido 2026-07-24: requeriría instalar dependencias del paquete, lo que
ejecutaría código de build no confiable ANTES de terminar de vetarlo --
decisión de nivel ADR, no improvisada aquí).

2B (http): HttpMcpTransport (initialize/tools/list) contra el remote_url real.

Cada paso hace fail-closed en cadena: si un paso falla, los siguientes no se
intentan y el resultado queda 'no completo', nunca se finge éxito parcial
como si fuera completo.
"""

from __future__ import annotations


def _entry_stdio(**overrides) -> dict:
    base = {
        "name": "ai.adeu/adeu", "transport": "stdio",
        "package_registry": "pypi", "package_identifier": "adeu", "version": "1.5.2",
    }
    base.update(overrides)
    return base


def _entry_http(**overrides) -> dict:
    base = {"name": "ac.inference.sh/mcp", "transport": "http", "remote_url": "https://api.inference.sh/mcp"}
    base.update(overrides)
    return base


def test_stage2a_stops_at_lookup_when_package_not_found(tmp_path) -> None:
    from atlas.mcp.candidate_stage2 import run_stage2a_stdio

    def fake_lookup(registry, identifier, version, *, fetcher=None):
        from atlas.mcp.candidate_package_lookup import PackageLookupResult
        return PackageLookupResult(exists=False, version_matches=False, download_url="", sha256="", reason="404")

    result = run_stage2a_stdio(_entry_stdio(), quarantine_root=tmp_path, lookup_fn=fake_lookup)
    assert result.completed is False
    assert result.stage_reached == "lookup"


def test_stage2a_stops_at_fetch_when_hash_mismatch(tmp_path) -> None:
    from atlas.mcp.candidate_stage2 import run_stage2a_stdio
    from atlas.mcp.candidate_package_lookup import PackageLookupResult

    def fake_lookup(registry, identifier, version, *, fetcher=None):
        return PackageLookupResult(exists=True, version_matches=True, download_url="https://pypi.org/x.tar.gz", sha256="a" * 64, reason="ok")

    def fake_binary_fetcher(url):
        return 200, b"contenido que no coincide con el hash esperado"

    result = run_stage2a_stdio(_entry_stdio(), quarantine_root=tmp_path, lookup_fn=fake_lookup, binary_fetcher=fake_binary_fetcher)
    assert result.completed is False
    assert result.stage_reached == "fetch"


def test_stage2a_completes_with_findings_on_full_real_flow(tmp_path) -> None:
    """Fixture completa inyectada (sin red real): lookup ok -> fetch ok
    (tarball real en memoria) -> extract ok -> entrypoint ok -> semgrep
    (runner fake) con hallazgos -> completed=True, worst_severity expuesto."""
    import hashlib
    import io
    import tarfile
    import json as jsonlib
    from atlas.mcp.candidate_stage2 import run_stage2a_stdio
    from atlas.mcp.candidate_package_lookup import PackageLookupResult

    def _tar_bytes(files: dict) -> bytes:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for name, content in files.items():
                info = tarfile.TarInfo(name=name)
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
        return buf.getvalue()

    content = _tar_bytes({
        "pkg/pyproject.toml": b'[project.scripts]\nadeu-server = "adeu.server:main"\n',
        "pkg/adeu/server.py": b"print('hi')",
    })
    real_hash = hashlib.sha256(content).hexdigest()

    def fake_lookup(registry, identifier, version, *, fetcher=None):
        return PackageLookupResult(exists=True, version_matches=True, download_url="https://files.pythonhosted.org/x.tar.gz", sha256=real_hash, reason="ok")

    def fake_binary_fetcher(url):
        return 200, content

    def fake_semgrep_runner(cmd, cwd, timeout):
        return 0, jsonlib.dumps({"results": [
            {"check_id": "x", "path": "adeu/server.py", "start": {"line": 1}, "extra": {"severity": "WARNING", "message": "m"}}
        ], "errors": []}), ""

    result = run_stage2a_stdio(
        _entry_stdio(), quarantine_root=tmp_path, lookup_fn=fake_lookup,
        binary_fetcher=fake_binary_fetcher, semgrep_runner=fake_semgrep_runner,
    )
    assert result.completed is True
    assert result.stage_reached == "static_scan"
    assert result.entrypoint_module == "adeu.server"
    assert len(result.static_findings) == 1


def test_stage2a_npm_tarball_extracts_as_targz_not_zip(tmp_path) -> None:
    """Hallazgo real 2026-07-24: npm SIEMPRE distribuye .tgz (tar.gz), nunca
    .zip -- solo los wheels de Python (.whl) son zip. Asumir zip para
    'cualquier cosa que no sea pypi' rompía TODO el track npm en extract."""
    import hashlib
    import io
    import tarfile
    from atlas.mcp.candidate_stage2 import run_stage2a_stdio
    from atlas.mcp.candidate_package_lookup import PackageLookupResult

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        content = b'{"name": "@foo/files", "bin": "dist/index.js"}'
        info = tarfile.TarInfo(name="package/package.json")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    tgz_bytes = buf.getvalue()
    real_hash = hashlib.sha512(tgz_bytes).hexdigest()

    def fake_lookup(registry, identifier, version, *, fetcher=None):
        return PackageLookupResult(
            exists=True, version_matches=True,
            download_url="https://registry.npmjs.org/@foo/files/-/files-0.2.0.tgz",
            sha256=real_hash, hash_algo="sha512", reason="ok",
        )

    def fake_binary_fetcher(url):
        return 200, tgz_bytes

    result = run_stage2a_stdio(
        {"name": "@foo/files", "transport": "stdio", "package_registry": "npm",
         "package_identifier": "@foo/files", "version": "0.2.0"},
        quarantine_root=tmp_path, lookup_fn=fake_lookup, binary_fetcher=fake_binary_fetcher,
    )
    assert result.stage_reached not in ("fetch", "extract")  # pasó fetch+extract; falla más tarde (semgrep no instalado en runner por defecto aquí) es aceptable


def test_stage2b_probes_real_remote_url() -> None:
    from atlas.mcp.candidate_stage2 import run_stage2b_http

    def fetcher(method, url, data, headers):
        import json as jsonlib
        body = jsonlib.loads(data.decode())
        if "id" not in body:  # notification (notifications/initialized) -- sin respuesta útil
            return 202, ""
        if body["method"] == "initialize":
            return 200, jsonlib.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {"protocolVersion": "2025-06-18"}})
        return 200, jsonlib.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {"tools": [{"name": "a"}, {"name": "b"}]}})

    result = run_stage2b_http(_entry_http(), fetcher=fetcher)
    assert result.completed is True
    assert result.tool_count == 2


def test_stage2b_missing_remote_url_failclosed() -> None:
    from atlas.mcp.candidate_stage2 import run_stage2b_http

    result = run_stage2b_http(_entry_http(remote_url=""), fetcher=lambda *a: (200, "{}"))
    assert result.completed is False
    assert "remote_url" in result.reason.lower() or "url" in result.reason.lower()
