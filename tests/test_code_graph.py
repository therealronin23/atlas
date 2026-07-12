"""Tests para scripts/code_graph.py usando importlib para importar el módulo."""

import importlib.util
import sys
from pathlib import Path

import pytest


# Importar code_graph desde scripts/code_graph.py usando importlib
_code_graph_path = Path(__file__).resolve().parent.parent / "scripts" / "code_graph.py"
_spec = importlib.util.spec_from_file_location("code_graph", _code_graph_path)
_code_graph = importlib.util.module_from_spec(_spec)
sys.modules["code_graph"] = _code_graph
_spec.loader.exec_module(_code_graph)

build_import_graph = _code_graph.build_import_graph
fan_in = _code_graph.fan_in
find_cycles = _code_graph.find_cycles


@pytest.fixture
def tmp_src(tmp_path: Path) -> Path:
    """Monta un mini árbol src/atlas con 3 módulos cíclicos."""
    atlas_dir = tmp_path / "src" / "atlas"
    atlas_dir.mkdir(parents=True)

    # a.py importa atlas.b
    (atlas_dir / "a.py").write_text("from atlas import b\n")

    # b.py importa atlas.c
    (atlas_dir / "b.py").write_text("from atlas import c\n")

    # c.py importa atlas.a
    (atlas_dir / "c.py").write_text("from atlas import a\n")

    return atlas_dir


def test_build_import_graph(tmp_src: Path):
    """Verifica el grafo exacto de imports cíclicos."""
    graph = build_import_graph(tmp_src)

    expected = {
        "atlas.a": {"atlas.b"},
        "atlas.b": {"atlas.c"},
        "atlas.c": {"atlas.a"},
    }

    assert graph == expected


def test_fan_in(tmp_src: Path):
    """Verifica que fan_in sea 1 para cada módulo en el ciclo."""
    graph = build_import_graph(tmp_src)
    fi = fan_in(graph)

    assert fi["atlas.a"] == 1
    assert fi["atlas.b"] == 1
    assert fi["atlas.c"] == 1


def test_find_cycles(tmp_src: Path):
    """Verifica que find_cycles devuelve un ciclo con atlas.a, atlas.b y atlas.c."""
    graph = build_import_graph(tmp_src)
    cycles = find_cycles(graph)

    assert len(cycles) >= 1

    # Al menos un ciclo debe contener los tres módulos
    found_cycle = False
    for cycle in cycles:
        cycle_set = set(cycle)
        if {"atlas.a", "atlas.b", "atlas.c"}.issubset(cycle_set):
            found_cycle = True
            break

    assert found_cycle, f"Ningún ciclo contiene los tres módulos. Ciclos encontrados: {cycles}"