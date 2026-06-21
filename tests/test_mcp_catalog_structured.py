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
    # Dominios humanos autoexplicativos (v3).
    for required in ("programacion", "diseno", "ciberseguridad", "conocimiento-memoria", "infraestructura"):
        assert required in tax, f"falta sector {required}"
    # Toda entrada tiene un sector y un estado válido.
    for e in entries:
        assert e.sector and e.status in {"candidato", "verificado", "instalado"}


def test_real_catalog_verified_are_only_proven() -> None:
    """Honesto: solo lo prove-it-eado está `verificado`. Hoy: `everything`
    (server de referencia, prove-it OK). Si crece, es decisión explícita."""
    from atlas.mcp.catalog import installable, load_catalog

    assert {e.name for e in installable(load_catalog(_CATALOG))} == {"everything"}


# ---------------------------------------------------------------------------
# Catálogo v2: tags multi-sector + mode operativo + metadatos
# ---------------------------------------------------------------------------

_V2 = """
sectors:
  coding:
    label: Coding
    entries:
      - name: Karpathy
        kind: skill
        purpose: reglas
        tags: [coding, productivity-meta]
        version: "1.0"
        license: MIT
        trust: unvetted
        status: candidato
      - name: atlas-memory
        kind: mcp
        purpose: sustrato
        source: atlas.mcp.memory_server
        status: instalado
"""


def test_v2_fields_parse_with_defaults(tmp_path: Path) -> None:
    from atlas.mcp.catalog import load_catalog

    p = tmp_path / "v2.yaml"
    p.write_text(_V2, encoding="utf-8")
    by_name = {e.name: e for e in load_catalog(p)}

    k = by_name["Karpathy"]
    assert k.tags == ["coding", "productivity-meta"]   # multi-sector explícito
    assert k.version == "1.0" and k.license == "MIT" and k.trust == "unvetted"
    # skill sin mode explícito → default "served" (lo servimos, sin descarga)
    assert k.mode == "served"

    m = by_name["atlas-memory"]
    # mcp sin tags → tags = [sector]; sin mode → default "connected"
    assert m.tags == ["coding"]
    assert m.mode == "connected"


_V3 = """
sectors:
  ciberseguridad:
    label: Ciberseguridad
    desc: Atacar y defender sistemas.
    aliases: [security, seguridad, infosec]
    subsectors:
      pentesting: {label: Pentesting, aliases: [redteam, ofensiva]}
      defensa: {label: Defensa}
    entries:
      - {name: Trail of Bits, kind: skill, subsector: pentesting, status: candidato}
  programacion:
    label: Programación
    aliases: [coding]
    subsectors:
      testing: {label: Testing}
    entries:
      - {name: atlas-trunk-f, kind: mcp, subsector: testing, phase: 4, status: instalado}
"""


def test_v3_entry_has_subsector_and_phase(tmp_path: Path) -> None:
    from atlas.mcp.catalog import load_catalog

    p = tmp_path / "v3.yaml"
    p.write_text(_V3, encoding="utf-8")
    by_name = {e.name: e for e in load_catalog(p)}
    assert by_name["Trail of Bits"].subsector == "pentesting"
    assert by_name["atlas-trunk-f"].phase == 4
    assert by_name["Trail of Bits"].phase is None  # opcional


def test_load_taxonomy_declares_domains_subsectors_aliases(tmp_path: Path) -> None:
    from atlas.mcp.catalog import load_taxonomy

    p = tmp_path / "v3.yaml"
    p.write_text(_V3, encoding="utf-8")
    tax = load_taxonomy(p)
    assert tax["ciberseguridad"]["label"] == "Ciberseguridad"
    assert "seguridad" in tax["ciberseguridad"]["aliases"]
    assert "pentesting" in tax["ciberseguridad"]["subsectors"]
    assert "redteam" in tax["ciberseguridad"]["subsectors"]["pentesting"]["aliases"]


_KINDS_CAT = """
sectors:
  programacion:
    label: Programación
    entries:
      - {name: a-skill, kind: skill, status: candidato}
      - {name: a-prompt, kind: prompt, status: candidato}
      - {name: a-hook, kind: hook, status: candidato}
      - {name: a-plugin, kind: plugin, status: candidato}
      - {name: a-rule, kind: rule, status: candidato}
      - {name: a-subagent, kind: subagent, status: candidato}
"""


def test_full_kind_taxonomy_accepted(tmp_path: Path) -> None:
    from atlas.mcp.catalog import by_kind, load_catalog

    p = tmp_path / "k.yaml"
    p.write_text(_KINDS_CAT, encoding="utf-8")
    counts = by_kind(load_catalog(p))
    # las "líneas" nuevas se aceptan, no solo skill/mcp/api/tool
    for k in ("skill", "prompt", "hook", "plugin", "rule", "subagent"):
        assert counts.get(k) == 1


def test_of_kind_filters_one_line(tmp_path: Path) -> None:
    from atlas.mcp.catalog import load_catalog, of_kind

    p = tmp_path / "k.yaml"
    p.write_text(_KINDS_CAT, encoding="utf-8")
    prompts = of_kind(load_catalog(p), "prompt")
    assert [e.name for e in prompts] == ["a-prompt"]


def test_find_matches_name_purpose_and_aliases(tmp_path: Path) -> None:
    from atlas.mcp.catalog import find, load_catalog, load_taxonomy

    p = tmp_path / "v3.yaml"
    p.write_text(_V3, encoding="utf-8")
    entries, tax = load_catalog(p), load_taxonomy(p)

    # por alias de sector ("seguridad" → ciberseguridad) encuentra su entrada
    hits = find(entries, tax, "seguridad")
    assert any(h["name"] == "Trail of Bits" for h in hits)
    # por alias de subsector ("redteam" → pentesting)
    assert any(h["subsector"] == "pentesting" for h in find(entries, tax, "redteam"))
    # por nombre directo
    assert find(entries, tax, "trail")[0]["name"] == "Trail of Bits"
    # cada hit trae el camino sector/subsector (accesible sin navegar)
    h = find(entries, tax, "trail")[0]
    assert h["sector"] == "ciberseguridad" and h["subsector"] == "pentesting"


def test_classify_assigns_domain_by_tag_or_alias(tmp_path: Path) -> None:
    from atlas.mcp.catalog import classify, load_taxonomy

    p = tmp_path / "v3.yaml"
    p.write_text(_V3, encoding="utf-8")
    tax = load_taxonomy(p)
    # por tag que casa un alias de sector ("security" → ciberseguridad)
    assert classify("foo", "", ["security"], tax) == "ciberseguridad"
    # por palabra en el nombre/propósito ("pentest" → alias de pentesting → ciberseguridad)
    assert classify("redteam-tool", "ofensiva", [], tax) == "ciberseguridad"
    # sin señal → uncategorized (honesto, no fuerza)
    assert classify("zxqw", "nada", [], tax) == "uncategorized"


def test_find_orders_mature_first(tmp_path: Path) -> None:
    from atlas.mcp.catalog import find, load_catalog, load_taxonomy

    p = tmp_path / "v3.yaml"
    p.write_text(_V3, encoding="utf-8")
    entries, tax = load_catalog(p), load_taxonomy(p)
    # "test" casa con atlas-trunk-f (instalado, subsector testing) y nada más maduro
    hits = find(entries, tax, "test")
    assert hits[0]["status"] == "instalado"


def test_in_sector_matches_any_tag(tmp_path: Path) -> None:
    from atlas.mcp.catalog import in_sector, load_catalog

    p = tmp_path / "v2.yaml"
    p.write_text(_V2, encoding="utf-8")
    entries = load_catalog(p)
    # Karpathy aparece en AMBOS sectores por sus tags (sector = vista, no carpeta).
    coding = {e.name for e in in_sector(entries, "coding")}
    prod = {e.name for e in in_sector(entries, "productivity-meta")}
    assert "Karpathy" in coding and "Karpathy" in prod
