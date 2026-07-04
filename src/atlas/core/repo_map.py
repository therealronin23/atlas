"""
Atlas Core — Repo Map (técnica #14, patrón Aider)

Da al modelo una vista de "quién es quién" del repo sin mandar archivos
completos ni reindexar todo: extrae firmas (no cuerpos) de símbolos Python
vía `ast` (stdlib, sin tree-sitter — Atlas es un proyecto Python puro,
manía `stdlib-over-new-deps`), construye un grafo de referencias entre
archivos, y aplica PageRank (implementación propia, sin networkx) para
rankear qué archivos son más relevantes respecto a los ya en foco.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Symbol", "extract_symbols", "extract_references", "build_repo_map"]


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str  # "function" | "class" | "method"
    signature: str
    lineno: int


def _format_args(args: ast.arguments) -> str:
    parts = [a.arg for a in args.posonlyargs] if hasattr(args, "posonlyargs") else []
    parts += [a.arg for a in args.args]
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    parts += [a.arg for a in args.kwonlyargs]
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")
    return ", ".join(parts)


def extract_symbols(content: str) -> list[Symbol]:
    """Símbolos top-level y de clase (métodos), solo firma — no cuerpo.

    Devuelve lista vacía si *content* no parsea (fail-soft: el repo-map es
    una ayuda de contexto, no un gate de corrección; no debe romper el
    llamador por un archivo con syntax error).
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    symbols: list[Symbol] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            symbols.append(Symbol(
                name=node.name, kind="function",
                signature=f"{prefix} {node.name}({_format_args(node.args)})",
                lineno=node.lineno,
            ))
        elif isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in node.bases) if node.bases else ""
            symbols.append(Symbol(
                name=node.name, kind="class",
                signature=f"class {node.name}({bases})" if bases else f"class {node.name}",
                lineno=node.lineno,
            ))
            for sub in ast.iter_child_nodes(node):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    prefix = "async def" if isinstance(sub, ast.AsyncFunctionDef) else "def"
                    symbols.append(Symbol(
                        name=f"{node.name}.{sub.name}", kind="method",
                        signature=f"    {prefix} {sub.name}({_format_args(sub.args)})",
                        lineno=sub.lineno,
                    ))
    return symbols


def extract_references(content: str) -> set[str]:
    """Nombres referenciados (ast.Name / ast.Attribute) — usado para detectar
    qué símbolos de OTROS archivos usa este archivo. Fail-soft: set vacío
    si no parsea."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return set()

    refs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            refs.add(node.id)
        elif isinstance(node, ast.Attribute):
            refs.add(node.attr)
    return refs


def _pagerank(
    graph: dict[str, dict[str, float]],
    *,
    personalization: dict[str, float] | None = None,
    damping: float = 0.85,
    iterations: int = 50,
    tol: float = 1e-6,
) -> dict[str, float]:
    """PageRank por iteración de potencias (sin networkx).

    *graph*: adyacencia dirigida {origen: {destino: peso}}. Nodos sin salida
    (sink) reparten su masa uniformemente (evita fuga de rank). Con
    *personalization*, el "salto aleatorio" no es uniforme sino sesgado hacia
    los nodos dados (mismo patrón que Aider: sesgar hacia archivos ya en foco).
    """
    nodes = set(graph.keys())
    for targets in graph.values():
        nodes.update(targets.keys())
    if not nodes:
        return {}
    n = len(nodes)

    if personalization:
        total = sum(personalization.values()) or 1.0
        pers = {node: personalization.get(node, 0.0) / total for node in nodes}
    else:
        pers = {node: 1.0 / n for node in nodes}

    rank = {node: 1.0 / n for node in nodes}

    for _ in range(iterations):
        new_rank = {node: (1.0 - damping) * pers[node] for node in nodes}
        for src in nodes:
            out_edges = graph.get(src, {})
            out_weight = sum(out_edges.values())
            if out_weight <= 0:
                # Nodo sink: reparte su masa según la personalización (evita fuga).
                for node in nodes:
                    new_rank[node] += damping * rank[src] * pers[node]
                continue
            for dst, weight in out_edges.items():
                new_rank[dst] += damping * rank[src] * (weight / out_weight)

        delta = sum(abs(new_rank[node] - rank[node]) for node in nodes)
        rank = new_rank
        if delta < tol:
            break

    return rank


def build_repo_map(
    repo_root: Path,
    all_files: list[str],
    focus_files: list[str],
    *,
    budget_chars: int = 4000,
) -> str:
    """Construye el repo-map: firmas de los archivos más relevantes respecto
    a *focus_files* (los ya en contexto), sin exceder *budget_chars*.

    Archivos en *focus_files* se excluyen del mapa (el modelo ya los ve
    completos en la sección de archivos de contexto — no duplicar).
    """
    candidates = [f for f in all_files if f not in focus_files and f.endswith(".py")]
    if not candidates:
        return ""

    contents: dict[str, str] = {}
    symbol_index: dict[str, list[Symbol]] = {}
    for rel_path in candidates + [f for f in focus_files if f.endswith(".py")]:
        try:
            contents[rel_path] = (repo_root / rel_path).read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            contents[rel_path] = ""
        symbol_index[rel_path] = extract_symbols(contents[rel_path])

    # Símbolo -> archivo que lo define (para resolver referencias a archivos).
    defined_in: dict[str, str] = {}
    for rel_path, symbols in symbol_index.items():
        for sym in symbols:
            top_name = sym.name.split(".", 1)[0]
            defined_in.setdefault(top_name, rel_path)

    # Grafo de referencias: archivo -> {archivo_referenciado: nº de símbolos usados}.
    graph: dict[str, dict[str, float]] = {}
    for rel_path in contents:
        refs = extract_references(contents[rel_path])
        edges: dict[str, float] = {}
        for name in refs:
            target = defined_in.get(name)
            if target and target != rel_path:
                edges[target] = edges.get(target, 0.0) + 1.0
        graph[rel_path] = edges

    personalization = {f: 1.0 for f in focus_files if f in contents} or None
    ranks = _pagerank(graph, personalization=personalization)

    ranked_candidates = sorted(candidates, key=lambda f: ranks.get(f, 0.0), reverse=True)

    lines: list[str] = []
    used = 0
    for rel_path in ranked_candidates:
        symbols = symbol_index.get(rel_path, [])
        if not symbols:
            continue
        block = f"### {rel_path}\n" + "\n".join(s.signature for s in symbols) + "\n"
        if used + len(block) > budget_chars:
            break
        lines.append(block)
        used += len(block)

    if not lines:
        return ""
    return "## Mapa del repo (firmas, sin cuerpo)\n\n" + "\n".join(lines)
