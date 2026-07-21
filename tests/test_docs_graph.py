"""Grafo de conocimiento de docs/ (scripts/docs_graph.py) — slice 1.

Contrato: wikilinks resuelven por stem exacto y por PREFIJO (convención
orgánica de membrana/: [[OSM-007]] -> OSM-007_privacy_....md), los mdlinks
relativos y repo-absolutos resuelven contra el árbol, lo no resoluble es un
enlace ROTO (señal), y un doc vigente sin aristas es HUÉRFANO. El drift del
radar excluye fuentes históricas (archive congelado no es accionable).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml


def _load(name: str):
    repo_root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        name, repo_root / "scripts" / f"{name}.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses exigen el módulo registrado
    spec.loader.exec_module(module)
    return module


def _make_docs(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    (docs / "design").mkdir(parents=True)
    (docs / "membrana").mkdir()
    (docs / "archive").mkdir()
    (docs / "design" / "plan.md").write_text(
        "ver [[OSM-007]] y [enlace](../membrana/OSM-007_privacy.md) "
        "y [[no-existe]]",
        encoding="utf-8",
    )
    (docs / "membrana" / "OSM-007_privacy.md").write_text("# OSM-007", encoding="utf-8")
    (docs / "design" / "suelto.md").write_text("sin enlaces", encoding="utf-8")
    (docs / "archive" / "viejo.md").write_text("[[tampoco-existe]]", encoding="utf-8")
    index_module = _load("docs_index_audit")
    index_module.write_index(docs)

    # RC2 contract: new documents begin as `propuesto`. Promote one isolated
    # document explicitly so this fixture still exercises the graph's
    # "vigente without links" orphan rule rather than relying on old defaults.
    index_path = docs / "INDEX.yaml"
    payload = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    entry = next(
        item for item in payload["entries"]
        if item["path"] == "docs/design/suelto.md"
    )
    entry["status"] = "vigente"
    entry["verified"] = "2026-07-21"
    index_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return docs


class TestBuildGraph:
    def test_wikilink_resolves_by_prefix(self, tmp_path: Path) -> None:
        g = _load("docs_graph").build_graph(_make_docs(tmp_path))
        wikis = [e for e in g.outgoing("docs/design/plan.md") if e.kind == "wikilink"]
        resolved = [e for e in wikis if e.resolved]
        assert [e.dst for e in resolved] == ["docs/membrana/OSM-007_privacy.md"]

    def test_relative_mdlink_resolves(self, tmp_path: Path) -> None:
        g = _load("docs_graph").build_graph(_make_docs(tmp_path))
        mds = [e for e in g.outgoing("docs/design/plan.md") if e.kind == "mdlink"]
        assert mds[0].resolved and mds[0].dst == "docs/membrana/OSM-007_privacy.md"

    def test_broken_link_detected(self, tmp_path: Path) -> None:
        g = _load("docs_graph").build_graph(_make_docs(tmp_path))
        broken = {e.dst for e in g.broken() if e.src == "docs/design/plan.md"}
        assert broken == {"no-existe"}

    def test_backlinks(self, tmp_path: Path) -> None:
        g = _load("docs_graph").build_graph(_make_docs(tmp_path))
        srcs = {e.src for e in g.backlinks("docs/membrana/OSM-007_privacy.md")}
        assert srcs == {"docs/design/plan.md"}

    def test_orphan_is_vigente_without_edges(self, tmp_path: Path) -> None:
        g = _load("docs_graph").build_graph(_make_docs(tmp_path))
        # 'suelto.md' no tiene aristas; 'viejo.md' tampoco pero es historico.
        assert g.orphans() == ["docs/design/suelto.md"]


class TestGraphDrift:
    def test_drift_excludes_archive_and_dedupes(self, tmp_path: Path) -> None:
        m = _load("docs_graph")
        docs = _make_docs(tmp_path)
        drift = m.graph_drift(docs)
        joined = "\n".join(drift)
        assert "no-existe" in joined            # roto en doc vigente: señal
        assert "tampoco-existe" not in joined   # roto en archive: filtrado
        assert any("sin ningún enlace" in s for s in drift)  # huérfanos agregados
