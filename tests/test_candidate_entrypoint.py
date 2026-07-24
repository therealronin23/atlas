"""
TDD — candidate_entrypoint: descubre el comando de arranque real de un
candidato stdio extraído (sin instalar -- no hay console-script generado).

Fail-closed (I6) si es ambiguo: adivinar el entry point equivocado de un
paquete de terceros podría invocar código no pretendido o dar un falso
"protocolo falló". Mejor "no determinable -> pending_review" que adivinar.
"""

from __future__ import annotations


def test_pypi_entrypoint_picked_by_identifier_server_suffix(tmp_path) -> None:
    """El paquete 'adeu' declara 2 scripts (adeu, adeu-server) -- se prefiere
    el que coincide con '<identifier>-server' (patrón real observado: MCP
    server suele nombrarse así, distinto del CLI de usuario)."""
    from atlas.mcp.candidate_entrypoint import discover_pypi_entrypoint

    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\nadeu = "adeu.cli:main"\nadeu-server = "adeu.server:main"\n'
        '[build-system]\nrequires = ["hatchling"]\n'
    )
    result = discover_pypi_entrypoint(tmp_path, package_identifier="adeu")
    assert result.ok is True
    assert result.module == "adeu.server"
    assert result.function == "main"


def test_pypi_entrypoint_single_script_used_directly(tmp_path) -> None:
    from atlas.mcp.candidate_entrypoint import discover_pypi_entrypoint

    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\nfoo-mcp = "foo_mcp.__main__:run"\n'
    )
    result = discover_pypi_entrypoint(tmp_path, package_identifier="foo-mcp")
    assert result.ok is True
    assert result.module == "foo_mcp.__main__"
    assert result.function == "run"


def test_pypi_entrypoint_ambiguous_multiple_candidates_failclosed(tmp_path) -> None:
    """2+ scripts, ninguno coincide con el patrón '<id>-server' ni es el
    único -- no se adivina, se rechaza explícito."""
    from atlas.mcp.candidate_entrypoint import discover_pypi_entrypoint

    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\nfoo = "foo.cli:main"\nbar = "foo.other:main"\n'
    )
    result = discover_pypi_entrypoint(tmp_path, package_identifier="foo")
    assert result.ok is False
    assert "ambig" in result.reason.lower()


def test_pypi_entrypoint_no_scripts_failclosed(tmp_path) -> None:
    from atlas.mcp.candidate_entrypoint import discover_pypi_entrypoint

    (tmp_path / "pyproject.toml").write_text('[build-system]\nrequires = ["hatchling"]\n')
    result = discover_pypi_entrypoint(tmp_path, package_identifier="foo")
    assert result.ok is False


def test_pypi_entrypoint_missing_pyproject_failclosed(tmp_path) -> None:
    from atlas.mcp.candidate_entrypoint import discover_pypi_entrypoint

    result = discover_pypi_entrypoint(tmp_path, package_identifier="foo")
    assert result.ok is False


def test_npm_entrypoint_from_bin_string(tmp_path) -> None:
    """package.json 'bin' puede ser un string (un solo binario) o un dict
    (varios) -- el caso string es el común para un server MCP simple."""
    import json
    from atlas.mcp.candidate_entrypoint import discover_npm_entrypoint

    (tmp_path / "package.json").write_text(json.dumps({"name": "@foo/files", "bin": "dist/index.js"}))
    result = discover_npm_entrypoint(tmp_path, package_identifier="@foo/files")
    assert result.ok is True
    assert result.script_path == "dist/index.js"


def test_npm_entrypoint_from_bin_dict_matches_identifier(tmp_path) -> None:
    """La clave 'files-mcp' SÍ coincide con el patrón '<short_name>-mcp' --
    resuelve directo, sin ambigüedad."""
    import json
    from atlas.mcp.candidate_entrypoint import discover_npm_entrypoint

    (tmp_path / "package.json").write_text(
        json.dumps({"name": "@foo/files", "bin": {"files-mcp": "dist/cli.js", "files-admin": "dist/admin.js"}})
    )
    result = discover_npm_entrypoint(tmp_path, package_identifier="@foo/files")
    assert result.ok is True
    assert result.script_path == "dist/cli.js"


def test_npm_entrypoint_from_bin_dict_single_entry_used_directly_even_if_name_differs(tmp_path) -> None:
    """Hallazgo real 2026-07-24 (corrido contra un paquete npm real): con UN
    solo binario declarado no hay ambigüedad real, aunque su nombre no
    coincida con ningún patrón heurístico -- mismo principio que el caso
    pypi de un único script. Antes se rechazaba como "ambiguo" un caso que
    no lo era en absoluto."""
    import json
    from atlas.mcp.candidate_entrypoint import discover_npm_entrypoint

    (tmp_path / "package.json").write_text(
        json.dumps({"name": "@aetherwealth/mcp", "bin": {"aether-wealth-mcp": "dist/index.js"}})
    )
    result = discover_npm_entrypoint(tmp_path, package_identifier="@aetherwealth/mcp")
    assert result.ok is True
    assert result.script_path == "dist/index.js"


def test_npm_entrypoint_from_bin_dict_no_pattern_match_failclosed(tmp_path) -> None:
    """2+ binarios, NINGUNO coincide con ningún patrón conocido -- ambiguo de
    verdad, se rechaza en vez de adivinar cuál es el server."""
    import json
    from atlas.mcp.candidate_entrypoint import discover_npm_entrypoint

    (tmp_path / "package.json").write_text(
        json.dumps({"name": "@foo/files", "bin": {"alpha": "dist/a.js", "beta": "dist/b.js"}})
    )
    result = discover_npm_entrypoint(tmp_path, package_identifier="@foo/files")
    assert result.ok is False
    assert "ambig" in result.reason.lower()
