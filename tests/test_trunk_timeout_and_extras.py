"""F5.3 + F5.4 (plan toasty-hatching-pillow) — tronco MCP.

F5.3: ``timeout_seconds`` en CatalogEntry (default 15.0) plumbeado desde el
YAML curado hasta el McpServerConfig del hijo en ``trunk_children``.

F5.4: el tronco LEE también el fichero de ADOPCIÓN AUTÓNOMA
(``$ATLAS_MCP_SERVERS`` o ``<workspace>/mcp_servers.json``): dedupe por nombre
con el YAML curado GANANDO en conflicto, fail-open si el fichero no existe o
está corrupto, y JAMÁS se añade a sí mismo (atlas-trunk) como hijo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from atlas.mcp.catalog import load_catalog
from atlas.mcp.config import McpServerConfig
from atlas.mcp.trunk_server import adopted_servers_path, trunk_children

_CAT = """
sectors:
  memory-knowledge:
    label: Memoria
    entries:
      - {name: atlas-memory, kind: mcp, source: atlas.mcp.memory_server, status: instalado}
      - {name: ctx7, kind: mcp, install: "npx -y @upstash/context7-mcp",
         status: verificado, timeout_seconds: 45}
      - {name: slowpoke, kind: mcp, install: "npx slow", status: verificado}
"""


def _children(
    tmp_path: Path, adopted_path: Path | None = None
) -> dict[str, McpServerConfig]:
    cat = tmp_path / "c.yaml"
    if not cat.exists():
        cat.write_text(_CAT, encoding="utf-8")
    return {
        c.name: c
        for c in trunk_children(
            load_catalog(cat),
            save_dir=tmp_path / "save",
            repo_root=Path("/repo"),
            python="/py",
            adopted_path=adopted_path,
        )
    }


# ---------------------------------------------------------------------------
# F5.3 — timeout_seconds: catálogo → McpServerConfig
# ---------------------------------------------------------------------------


def test_catalog_entry_parses_timeout_seconds(tmp_path: Path) -> None:
    cat = tmp_path / "c.yaml"
    cat.write_text(_CAT, encoding="utf-8")
    by_name = {e.name: e for e in load_catalog(cat)}
    assert by_name["ctx7"].timeout_seconds == 45.0
    assert by_name["slowpoke"].timeout_seconds == 15.0  # default explícito


def test_trunk_children_pass_timeout_from_catalog(tmp_path: Path) -> None:
    ch = _children(tmp_path)
    assert ch["ctx7"].timeout_seconds == 45.0
    assert ch["slowpoke"].timeout_seconds == 15.0


# ---------------------------------------------------------------------------
# F5.4 — el tronco lee también el fichero de adopción autónoma
# ---------------------------------------------------------------------------


def _write_adopted(path: Path, entries: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(entries), encoding="utf-8")


def test_adopted_merge_dedupe_curated_wins(tmp_path: Path) -> None:
    adopted = tmp_path / "mcp_servers.json"
    _write_adopted(adopted, [
        # Conflicto de nombre con el YAML curado → el YAML GANA.
        {"name": "ctx7", "cmd": ["npx", "sombra-maliciosa"]},
        # Adoptado nuevo → entra, con su timeout propio.
        {"name": "adopted-new", "cmd": ["uvx", "cool-mcp"], "timeout_seconds": 20},
        # El tronco JAMÁS se añade a sí mismo (recursión).
        {"name": "atlas-trunk",
         "cmd": ["/py", "-m", "atlas.mcp.trunk_server", "/s", "/r"]},
        # Deshabilitado → fuera.
        {"name": "apagado", "cmd": ["npx", "x"], "enabled": False},
    ])
    ch = _children(tmp_path, adopted_path=adopted)

    assert ch["ctx7"].cmd == ["npx", "-y", "@upstash/context7-mcp"]  # curado gana
    assert "adopted-new" in ch
    assert ch["adopted-new"].timeout_seconds == 20.0
    assert "atlas-trunk" not in ch
    assert "apagado" not in ch


def test_adopted_fail_open_when_file_missing(tmp_path: Path) -> None:
    ch = _children(tmp_path, adopted_path=tmp_path / "no-existe.json")
    assert set(ch) == {"atlas-memory", "ctx7", "slowpoke"}


def test_adopted_fail_open_when_file_malformed(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{esto no es json", encoding="utf-8")
    ch = _children(tmp_path, adopted_path=bad)  # no revienta el arranque
    assert set(ch) == {"atlas-memory", "ctx7", "slowpoke"}


def test_adopted_none_means_no_extra_read(tmp_path: Path) -> None:
    """Sin adopted_path la función es pura (sin lecturas globales ocultas):
    los tests existentes de trunk_children siguen siendo herméticos."""
    ch = _children(tmp_path, adopted_path=None)
    assert set(ch) == {"atlas-memory", "ctx7", "slowpoke"}


def test_adopted_servers_path_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ATLAS_MCP_SERVERS", str(tmp_path / "x.json"))
    assert adopted_servers_path() == tmp_path / "x.json"


def test_adopted_servers_path_default_matches_orchestrator_convention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Misma resolución que el Orchestrator: $ATLAS_MCP_SERVERS →
    <workspace>/mcp_servers.json con workspace = $ATLAS_HOME o ~/atlas."""
    monkeypatch.delenv("ATLAS_MCP_SERVERS", raising=False)
    monkeypatch.setenv("ATLAS_HOME", "/tmp/atlas-home-test")
    assert adopted_servers_path() == Path("/tmp/atlas-home-test/mcp_servers.json")
    monkeypatch.delenv("ATLAS_HOME", raising=False)
    assert adopted_servers_path() == Path.home() / "atlas" / "mcp_servers.json"


def test_serve_wires_adopted_path() -> None:
    """Guard de cableado: serve() debe pasar la ruta de adopción a
    trunk_children (sin esto, F5.4 quedaría muerto en producción)."""
    src = (
        Path(__file__).resolve().parents[1] / "src" / "atlas" / "mcp" / "trunk_server.py"
    ).read_text(encoding="utf-8")
    assert "adopted_path=adopted_servers_path()" in src
