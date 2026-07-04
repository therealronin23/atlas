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


def test_load_catalog_parses_read_only_tools(tmp_path: Path) -> None:
    from atlas.mcp.catalog import load_catalog

    p = tmp_path / "c.yaml"
    p.write_text(
        """
sectors:
  coding:
    label: Coding
    entries:
      - {name: pw, kind: mcp, status: verificado, read_only_tools: [browser_snapshot, browser_console_messages]}
      - {name: everything, kind: mcp, status: verificado}
""",
        encoding="utf-8",
    )
    by_name = {e.name: e for e in load_catalog(p)}
    assert by_name["pw"].read_only_tools == ("browser_snapshot", "browser_console_messages")
    assert by_name["everything"].read_only_tools == ()


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


def test_real_catalog_verified_are_vetted_and_installable() -> None:
    """Invariante: toda entrada verificada tiene install no vacío y trust==vetted."""
    from atlas.mcp.catalog import installable, load_catalog

    for e in installable(load_catalog(_CATALOG)):
        assert e.install, f"{e.name}: verificado pero install vacío"
        assert e.trust == "vetted", f"{e.name}: verificado pero trust={e.trust!r}, se esperaba 'vetted'"


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
    # fallback por línea (política declarada): sin señal pero kind con default → ese sector
    assert classify("zxqw", "", [], tax, kind="workflow",
                    kind_default={"workflow": "productividad"}) == "productividad"
    # la señal por alias SIEMPRE gana al fallback
    assert classify("redteam", "", [], tax, kind="workflow",
                    kind_default={"workflow": "productividad"}) == "ciberseguridad"


def test_classify_subsector_within_sector(tmp_path: Path) -> None:
    from atlas.mcp.catalog import classify_subsector, load_taxonomy

    p = tmp_path / "v3.yaml"
    p.write_text(_V3, encoding="utf-8")
    tax = load_taxonomy(p)
    # dentro de ciberseguridad, "redteam"/"ofensiva" → subsector pentesting
    assert classify_subsector("x", "ofensiva", [], "ciberseguridad", tax) == "pentesting"
    # sin señal de subsector → "" (vacío, honesto)
    assert classify_subsector("x", "nada", [], "ciberseguridad", tax) == ""
    # sector sin subsectores o desconocido → ""
    assert classify_subsector("x", "y", [], "no-existe", tax) == ""


_TAX_DATOS_VS_PROG = """
sectors:
  datos:
    label: Datos
    desc: Bases de datos y análisis.
    aliases: [data, database, sql, analytics]
    subsectors:
      sql: {label: SQL, aliases: [postgres, mysql, query]}
    entries: []
  programacion:
    label: Programación
    aliases: [coding, dev, python, javascript]
    subsectors:
      testing: {label: Testing, aliases: [tdd, qa]}
    entries: []
"""


def test_classify_subsector_signal_beats_generic_sector_alias(tmp_path: Path) -> None:
    """Un item con señal de subsector de 'datos' (e.g. 'sql') MÁS un alias genérico
    de 'programacion' (e.g. 'dev') debe ir a 'datos' porque el subsector pesa 2x."""
    from atlas.mcp.catalog import classify, load_taxonomy

    p = tmp_path / "tax.yaml"
    p.write_text(_TAX_DATOS_VS_PROG, encoding="utf-8")
    tax = load_taxonomy(p)

    # "sql query builder dev" → sql es subsector de datos (2pts) vs dev = sector alias de programacion (1pt)
    result = classify("sql query builder", "dev tool for postgres", [], tax)
    assert result == "datos", f"expected datos, got {result!r}"


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


# ---------------------------------------------------------------------------
# dedupe_by_kind_name — helper puro de deduplicación (#6 dedup)
# ---------------------------------------------------------------------------

_DEDUP_YAML = """
sectors:
  coding:
    label: Coding
    entries:
      - name: X
        kind: mcp
        purpose: primera aparicion
        status: candidato
      - name: X
        kind: mcp
        purpose: duplicado (debe ignorarse)
        status: candidato
      - name: Y
        kind: mcp
        purpose: distinto nombre
        status: candidato
"""

_DEDUP_YAML_CASE = """
sectors:
  coding:
    label: Coding
    entries:
      - name: MyTool
        kind: skill
        purpose: primera aparicion
        status: candidato
      - name: mytool
        kind: skill
        purpose: duplicado en minuscula (debe ignorarse)
        status: candidato
"""


def test_dedupe_by_kind_name_removes_duplicate_keeps_first(tmp_path: Path) -> None:
    """Lista con 2 entradas (kind=mcp, name=X) + 1 distinta → devuelve 2, con el
    primer 'X' (purpose='primera aparicion')."""
    from atlas.mcp.catalog import dedupe_by_kind_name, load_catalog

    p = tmp_path / "dedup.yaml"
    p.write_text(_DEDUP_YAML, encoding="utf-8")
    entries = load_catalog(p)
    assert len(entries) == 3  # antes del dedup hay 3

    result = dedupe_by_kind_name(entries)
    assert len(result) == 2
    by_name = {e.name: e for e in result}
    assert "X" in by_name and "Y" in by_name
    assert by_name["X"].purpose == "primera aparicion"


def test_dedupe_by_kind_name_is_case_insensitive_on_name(tmp_path: Path) -> None:
    """name.lower() es la clave: 'MyTool' y 'mytool' son el mismo item."""
    from atlas.mcp.catalog import dedupe_by_kind_name, load_catalog

    p = tmp_path / "dedup_case.yaml"
    p.write_text(_DEDUP_YAML_CASE, encoding="utf-8")
    entries = load_catalog(p)
    assert len(entries) == 2  # antes del dedup hay 2

    result = dedupe_by_kind_name(entries)
    assert len(result) == 1
    assert result[0].purpose == "primera aparicion"


def test_dedupe_by_kind_name_same_name_different_kind_not_deduped(tmp_path: Path) -> None:
    """Clave es (kind, name.lower()): mismo nombre, distinto kind → NO es duplicado."""
    from atlas.mcp.catalog import CatalogEntry, dedupe_by_kind_name

    def _e(kind: str, name: str) -> CatalogEntry:
        return CatalogEntry(
            name=name, sector="s", sector_label="S", kind=kind,
            purpose="", source="", install="", status="candidato", tags=[], mode="served",
        )

    entries = [_e("mcp", "Foo"), _e("skill", "Foo")]
    result = dedupe_by_kind_name(entries)
    assert len(result) == 2
