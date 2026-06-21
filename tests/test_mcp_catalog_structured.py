"""
Tests del catálogo MCP ESTRUCTURADO (línea B/C — tronco-agregador + catálogo).

El catálogo deja de ser solo prosa: pasa a YAML clasificado por SECTOR/necesidad
(el eje de clasificación del tronco-agregador) + estado por entrada. El instalador
y, más adelante, el enrutado del tronco lo consumen.

Honesto: todo entra como `candidato` (sin verificar); el instalador solo instala
`verificado` (wire-before-claim). Las APIs ya construidas (Wikipedia/World Bank)
van como `instalado`.

Diseño: docs/design/mcp_trunk_portable.md + WORK_LEDGER (línea TRONCO-AGREGADOR).
"""

from __future__ import annotations

from pathlib import Path

_CATALOG = Path(__file__).resolve().parent.parent / "docs" / "design" / "mcp_catalog.yaml"

_SAMPLE = """
sectors:
  coding:
    label: Coding y desarrollo
    entries:
      - name: Code Reviewer
        kind: skill
        purpose: review automático
        source: ""
        install: ""
        status: candidato
  memory-knowledge:
    label: Memoria y conocimiento
    entries:
      - name: atlas-memory
        kind: mcp
        purpose: sustrato verificable
        source: atlas.mcp.memory_server
        install: claude mcp add ...
        status: instalado
      - name: Graphiti MCP
        kind: mcp
        purpose: shared memory
        source: ""
        install: ""
        status: verificado
"""


# ---------------------------------------------------------------------------
# Loader estructurado
# ---------------------------------------------------------------------------


def test_load_catalog_parses_sector_kind_and_status(tmp_path: Path) -> None:
    from atlas.mcp.catalog import load_catalog

    p = tmp_path / "c.yaml"
    p.write_text(_SAMPLE, encoding="utf-8")
    entries = load_catalog(p)

    by_name = {e.name: e for e in entries}
    assert by_name["Code Reviewer"].sector == "coding"
    assert by_name["Code Reviewer"].kind == "skill"
    assert by_name["atlas-memory"].sector == "memory-knowledge"
    assert by_name["atlas-memory"].status == "instalado"


def test_sectors_returns_taxonomy(tmp_path: Path) -> None:
    from atlas.mcp.catalog import load_catalog, sectors

    p = tmp_path / "c.yaml"
    p.write_text(_SAMPLE, encoding="utf-8")
    tax = sectors(load_catalog(p))
    assert tax["coding"] == "Coding y desarrollo"
    assert "memory-knowledge" in tax


def test_installable_only_verified(tmp_path: Path) -> None:
    from atlas.mcp.catalog import installable, load_catalog

    p = tmp_path / "c.yaml"
    p.write_text(_SAMPLE, encoding="utf-8")
    names = {e.name for e in installable(load_catalog(p))}
    assert names == {"Graphiti MCP"}  # ni candidato ni instalado


# ---------------------------------------------------------------------------
# El catálogo REAL del repo
# ---------------------------------------------------------------------------


def test_real_catalog_loads_and_is_classified() -> None:
    from atlas.mcp.catalog import load_catalog, sectors

    entries = load_catalog(_CATALOG)
    assert entries, "el catálogo real debe tener entradas"
    tax = sectors(entries)
    # Sectores que pediste explícitamente (coding, frontend/diseño, research, etc.)
    for required in ("coding", "design-frontend", "research", "memory-knowledge", "commodity-infra"):
        assert required in tax, f"falta sector {required}"
    # Toda entrada tiene un sector y un estado válido.
    for e in entries:
        assert e.sector and e.status in {"candidato", "verificado", "instalado"}


def test_real_catalog_installs_nothing_unverified() -> None:
    """Honesto: nada `verificado` aún → el instalador no instala nada."""
    from atlas.mcp.catalog import installable, load_catalog

    assert installable(load_catalog(_CATALOG)) == []
