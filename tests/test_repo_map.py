"""
Tests para repo_map — técnica #14 (patrón Aider: firmas + PageRank, sin cuerpo).
"""

from __future__ import annotations

from atlas.core.repo_map import (
    Symbol,
    build_repo_map,
    extract_references,
    extract_symbols,
    _pagerank,
)


# ---------------------------------------------------------------------------
# extract_symbols
# ---------------------------------------------------------------------------

def test_extract_symbols_top_level_function():
    src = "def foo(x, y=1):\n    return x + y\n"
    symbols = extract_symbols(src)
    assert len(symbols) == 1
    assert symbols[0] == Symbol(name="foo", kind="function", signature="def foo(x, y)", lineno=1)


def test_extract_symbols_class_with_methods():
    src = (
        "class Foo:\n"
        "    def bar(self, x):\n"
        "        pass\n"
        "    async def baz(self):\n"
        "        pass\n"
    )
    symbols = extract_symbols(src)
    names = [s.name for s in symbols]
    assert names == ["Foo", "Foo.bar", "Foo.baz"]
    assert symbols[0].kind == "class"
    assert symbols[1].kind == "method"
    assert "async def baz" in symbols[2].signature


def test_extract_symbols_ignores_nested_functions():
    """Solo top-level y métodos de clase — no funciones anidadas dentro de otra."""
    src = "def outer():\n    def inner():\n        pass\n    return inner\n"
    symbols = extract_symbols(src)
    assert [s.name for s in symbols] == ["outer"]


def test_extract_symbols_fail_soft_on_syntax_error():
    """No debe lanzar excepción — el repo-map es ayuda de contexto, no gate."""
    assert extract_symbols("def broken(:\n") == []


def test_extract_symbols_empty_file():
    assert extract_symbols("") == []


# ---------------------------------------------------------------------------
# extract_references
# ---------------------------------------------------------------------------

def test_extract_references_names_and_attributes():
    src = "from foo import Bar\nresult = Bar().method_call()\n"
    refs = extract_references(src)
    assert "Bar" in refs
    assert "method_call" in refs


def test_extract_references_fail_soft_on_syntax_error():
    assert extract_references("def broken(:\n") == set()


# ---------------------------------------------------------------------------
# _pagerank
# ---------------------------------------------------------------------------

def test_pagerank_hub_ranks_highest():
    """A y B apuntan a HUB; HUB no apunta a nadie (sink). HUB debe rankear más alto."""
    graph = {
        "A": {"HUB": 1.0},
        "B": {"HUB": 1.0},
        "HUB": {},
    }
    ranks = _pagerank(graph)
    assert ranks["HUB"] > ranks["A"]
    assert ranks["HUB"] > ranks["B"]


def test_pagerank_symmetric_cycle_gives_equal_ranks():
    graph = {"A": {"B": 1.0}, "B": {"C": 1.0}, "C": {"A": 1.0}}
    ranks = _pagerank(graph)
    values = list(ranks.values())
    assert max(values) - min(values) < 1e-4


def test_pagerank_personalization_biases_toward_focus():
    """Con personalización hacia A, A debe rankear más alto que sin ella."""
    graph = {"A": {}, "B": {}, "C": {}}  # sin edges — solo importa la personalización
    ranks_neutral = _pagerank(graph)
    ranks_biased = _pagerank(graph, personalization={"A": 10.0})
    assert ranks_biased["A"] > ranks_neutral["A"]


def test_pagerank_empty_graph():
    assert _pagerank({}) == {}


# ---------------------------------------------------------------------------
# build_repo_map
# ---------------------------------------------------------------------------

def test_build_repo_map_includes_referenced_file(tmp_path):
    (tmp_path / "utils.py").write_text("def helper(x):\n    return x * 2\n")
    (tmp_path / "main.py").write_text("from utils import helper\nresult = helper(5)\n")

    repo_map = build_repo_map(
        tmp_path, all_files=["utils.py", "main.py"], focus_files=["main.py"],
    )

    assert "utils.py" in repo_map
    assert "def helper(x)" in repo_map
    # main.py está en foco → no se duplica en el mapa
    assert "### main.py" not in repo_map


def test_build_repo_map_excludes_all_when_all_in_focus(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    pass\n")
    repo_map = build_repo_map(tmp_path, all_files=["a.py"], focus_files=["a.py"])
    assert repo_map == ""


def test_build_repo_map_respects_budget(tmp_path):
    for i in range(20):
        (tmp_path / f"mod{i}.py").write_text(f"def func_{i}():\n    pass\n")
    all_files = [f"mod{i}.py" for i in range(20)]

    repo_map = build_repo_map(tmp_path, all_files=all_files, focus_files=[], budget_chars=200)
    assert len(repo_map) < 400  # presupuesto respetado con margen razonable de header


def test_build_repo_map_no_python_files_returns_empty(tmp_path):
    (tmp_path / "readme.md").write_text("# hello\n")
    repo_map = build_repo_map(tmp_path, all_files=["readme.md"], focus_files=[])
    assert repo_map == ""
