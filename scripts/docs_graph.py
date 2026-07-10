#!/usr/bin/env python3
"""Grafo de conocimiento de docs/ — enlaces, backlinks, huérfanos (slice 1).

Capacidad grafo/vault NATIVA de Atlas (sin Obsidian ni Graphiti como
dependencia, pero compatible con ambos mundos): los docs son markdown y los
enlaces son la convención `[[wikilink]]` — que ya vive orgánicamente en
docs/membrana/ — más los links markdown relativos/repo-absolutos. Este script
construye el grafo real desde el árbol + INDEX.yaml y responde lo que un mapa
estático no puede:

    python3 scripts/docs_graph.py                    # informe: huérfanos + rotos
    python3 scripts/docs_graph.py --links <doc.md>   # salientes + backlinks de un doc

Slice 2 (futuro, ver backlog): fusionar con el sustrato de memoria en Kuzu
(ya dependencia core) con aristas bitemporales, patrón Graphiti/Zep
(arXiv:2501.13956) — entidades y hechos con ventana de validez, recuperación
sin LLM. Este slice fija la convención y los datos; ese fija el motor.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# [[nombre]] · [[nombre#sección]] · [[nombre|alias]]
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
# [texto](ruta.md) — ignora http(s), anclas puras e imágenes externas
_MDLINK_RE = re.compile(r"\]\(([^)#\s]+\.(?:md|yaml|yml))(?:#[^)]*)?\)")


@dataclass
class Edge:
    src: str          # ruta repo-relativa del doc origen
    dst: str          # ruta repo-relativa resuelta (o el texto crudo si rota)
    kind: str         # "wikilink" | "mdlink"
    resolved: bool


@dataclass
class DocsGraph:
    nodes: dict[str, dict] = field(default_factory=dict)   # path -> {type,status}
    edges: list[Edge] = field(default_factory=list)

    # ------------------------------------------------------------------
    # consultas
    # ------------------------------------------------------------------

    def outgoing(self, path: str) -> list[Edge]:
        return [e for e in self.edges if e.src == path]

    def backlinks(self, path: str) -> list[Edge]:
        return [e for e in self.edges if e.dst == path and e.resolved]

    def broken(self) -> list[Edge]:
        return [e for e in self.edges if not e.resolved]

    def orphans(self) -> list[str]:
        """Docs VIGENTES sin ningún enlace entrante ni saliente resuelto —
        conocimiento suelto que ni el humano ni Atlas pueden alcanzar
        navegando. Historia (archive) y no-markdown quedan fuera de la señal."""
        linked: set[str] = set()
        for e in self.edges:
            if e.resolved:
                linked.add(e.src)
                linked.add(e.dst)
        return sorted(
            p for p, meta in self.nodes.items()
            if p not in linked
            and p.endswith(".md")
            and meta.get("status") == "vigente"
        )


def _index_mod():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "docs_index_audit", ROOT / "scripts" / "docs_index_audit.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_graph(docs_dir: Path | None = None) -> DocsGraph:
    m = _index_mod()
    docs_dir = docs_dir or (ROOT / "docs")
    repo_root = docs_dir.parent
    index = m.load_index(docs_dir)

    graph = DocsGraph()
    for rel in m.scan_tree(docs_dir):
        key = str(rel)
        meta = index.get(key, {})
        graph.nodes[key] = {
            "type": meta.get("type"), "status": meta.get("status", "vigente"),
        }

    # Resolución de wikilinks por stem (único gana; ambiguo/desconocido = roto).
    by_stem: dict[str, list[str]] = {}
    for key in graph.nodes:
        by_stem.setdefault(Path(key).stem.lower(), []).append(key)

    for key in graph.nodes:
        if not key.endswith(".md"):
            continue
        src_path = repo_root / key
        try:
            text = src_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for match in _WIKILINK_RE.finditer(text):
            name = match.group(1).strip().lower()
            # Resolución exacta primero; si no, por PREFIJO (la convención
            # orgánica de membrana/: [[OSM-007]] -> OSM-007_privacy_...md).
            candidates = by_stem.get(name, [])
            if not candidates:
                candidates = [
                    key2 for stem, keys in by_stem.items()
                    if stem.startswith((f"{name}_", f"{name}-"))
                    for key2 in keys
                ]
            if len(candidates) == 1:
                graph.edges.append(Edge(key, candidates[0], "wikilink", True))
            else:
                graph.edges.append(Edge(key, match.group(1).strip(), "wikilink", False))

        for match in _MDLINK_RE.finditer(text):
            raw = match.group(1).strip()
            if raw.startswith(("http://", "https://")):
                continue
            if raw.startswith("docs/"):
                target = raw
            else:
                target = str(
                    (src_path.parent / raw).resolve().relative_to(repo_root)
                ) if (src_path.parent / raw).resolve().is_relative_to(repo_root) else raw
            if target in graph.nodes:
                graph.edges.append(Edge(key, target, "mdlink", True))
            else:
                graph.edges.append(Edge(key, raw, "mdlink", False))

    return graph


def graph_drift(docs_dir: Path | None = None) -> list[str]:
    """Señales para el radar: enlaces rotos (siempre) y recuento de huérfanos
    (una línea agregada — cientos de docs entrantes harían ruido uno a uno)."""
    graph = build_graph(docs_dir)
    seen: set[tuple[str, str]] = set()
    out: list[str] = []
    for e in graph.broken():
        # La historia (archive) está congelada: sus enlaces rotos no son
        # accionables y ahogarían la señal de los docs vivos.
        if graph.nodes.get(e.src, {}).get("status") == "historico":
            continue
        if (e.src, e.dst) in seen:
            continue
        seen.add((e.src, e.dst))
        out.append(
            f"enlace roto en {e.src}: [[{e.dst}]]" if e.kind == "wikilink"
            else f"enlace roto en {e.src}: ({e.dst})"
        )
    orphans = graph.orphans()
    if orphans:
        out.append(
            f"{len(orphans)} doc(s) vigentes sin ningún enlace (ver docs_graph.py)"
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--links", metavar="DOC", help="salientes + backlinks de un doc")
    args = parser.parse_args()

    graph = build_graph()
    if args.links:
        key = args.links if args.links.startswith("docs/") else f"docs/{args.links}"
        print(f"# {key}")
        print("\n## Salientes")
        for e in graph.outgoing(key):
            mark = "" if e.resolved else "  [ROTO]"
            print(f"  -> {e.dst} ({e.kind}){mark}")
        print("\n## Backlinks")
        for e in graph.backlinks(key):
            print(f"  <- {e.src} ({e.kind})")
        return 0

    print(f"# Grafo de docs — {len(graph.nodes)} nodos, {len(graph.edges)} aristas")
    broken = graph.broken()
    print(f"\n## Enlaces rotos ({len(broken)})")
    for e in broken[:40]:
        print(f"  - {e.src} -> {e.dst!r} ({e.kind})")
    orphans = graph.orphans()
    print(f"\n## Huérfanos vigentes sin enlaces ({len(orphans)})")
    for p in orphans[:40]:
        print(f"  - {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
