"""CLI smoke tests para `atlas mcp install` (ensamblaje end-to-end del instalador).

Ejercita el comando real vía CliRunner contra un catálogo sintético (nunca el
catálogo de producción) para no depender de qué esté `verificado` hoy en
docs/design/mcp_catalog.yaml.
"""

from __future__ import annotations

import json

from click.testing import CliRunner

from atlas.interfaces.cli import cli


def _write_synthetic_catalog(tmp_path):
    path = tmp_path / "synthetic_catalog.yaml"
    path.write_text(
        """
sectors:
  test-sector:
    label: Test
    entries:
      - {name: served-thing, kind: skill, mode: served, purpose: "servido", status: verificado}
      - {name: clean-mcp, kind: mcp, mode: connected, install: "npx -y @foo/bar", purpose: "mcp limpio", status: verificado}
      - {name: not-verified-yet, kind: mcp, mode: connected, install: "npx z", purpose: "aun candidato", status: candidato}
""",
        encoding="utf-8",
    )
    return path


def test_mcp_install_json_reports_installed_vetoed_omitted(tmp_path) -> None:
    catalog_path = _write_synthetic_catalog(tmp_path)
    result = CliRunner().invoke(
        cli, ["mcp", "install", "--catalog", str(catalog_path), "--json"]
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["total_entries"] == 3
    assert report["total_verificado"] == 2
    assert any("served-thing" in m for m in report["instaladas"])
    assert any("clean-mcp" in m and "BLOQUEADO" in m for m in report["omitidas"])
    assert report["vetadas"] == []


def test_mcp_install_human_output_lists_sections(tmp_path) -> None:
    catalog_path = _write_synthetic_catalog(tmp_path)
    result = CliRunner().invoke(cli, ["mcp", "install", "--catalog", str(catalog_path)])
    assert result.exit_code == 0, result.output
    assert "instaladas" in result.output
    assert "vetadas" in result.output
    assert "omitidas" in result.output
    assert "served-thing" in result.output
