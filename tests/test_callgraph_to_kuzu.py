"""Tests — cargador call-graph (Graphify AST cache) → Kuzu.

Fixture sintético con el MISMO esquema real observado en
``src/graphify-out/cache/ast/v0.9.11/*.json`` (inspeccionado en vivo):
nodes con file_type "code"/"rationale", _callable, source_file,
source_location tipo "L47"; edges con relation/confidence/weight.
"""

from __future__ import annotations

import json
from pathlib import Path

import kuzu
import pytest

from atlas.memory.callgraph_to_kuzu import load_callgraph_into_kuzu

# content-hashes ficticios (64 hex chars, como los reales) — solo hace falta
# que sean nombres de fichero válidos y distintos entre sí.
_HASH_A = "a" * 64
_HASH_B = "b" * 64


def _file_a() -> dict:
    """mod_a.py: define foo() y la clase Bar con método baz(); foo() llama
    a Bar.baz() (relation calls) y contiene un nodo rationale (se ignora)."""
    return {
        "nodes": [
            {
                "id": "mod_a_py",
                "label": "mod_a.py",
                "file_type": "code",
                "source_file": "atlas/mod_a.py",
                "source_location": "L1",
            },
            {
                "id": "mod_a_foo",
                "label": ".foo()",
                "file_type": "code",
                "source_file": "atlas/mod_a.py",
                "source_location": "L5",
                "_callable": True,
            },
            {
                "id": "mod_a_bar",
                "label": "Bar",
                "file_type": "code",
                "source_file": "atlas/mod_a.py",
                "source_location": "L10",
                "_callable": True,
            },
            {
                "id": "mod_a_bar_baz",
                "label": ".baz()",
                "file_type": "code",
                "source_file": "atlas/mod_a.py",
                "source_location": "L12",
                "_callable": True,
            },
            {
                "id": "mod_a_rationale_1",
                "label": "Rationale de mod_a",
                "file_type": "rationale",
                "source_file": "atlas/mod_a.py",
                "source_location": "L1",
            },
            {
                "id": "threading",
                "label": "threading",
                "file_type": "code",
                "source_file": "",
                "source_location": "",
                "origin_file": "/repo/atlas/mod_a.py",
            },
        ],
        "edges": [
            {
                "source": "mod_a_py",
                "target": "mod_a_foo",
                "relation": "contains",
                "confidence": "EXTRACTED",
                "source_file": "atlas/mod_a.py",
                "source_location": "L5",
                "weight": 1.0,
            },
            {
                "source": "mod_a_bar",
                "target": "mod_a_bar_baz",
                "relation": "method",
                "confidence": "EXTRACTED",
                "source_file": "atlas/mod_a.py",
                "source_location": "L12",
                "weight": 1.0,
            },
            {
                "source": "mod_a_foo",
                "target": "mod_a_bar_baz",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "atlas/mod_a.py",
                "source_location": "L6",
                "weight": 1.0,
            },
            {
                "source": "mod_a_py",
                "target": "threading",
                "relation": "imports",
                "confidence": "EXTRACTED",
                "source_file": "atlas/mod_a.py",
                "source_location": "L2",
                "weight": 1.0,
            },
            {
                "source": "mod_a_py",
                "target": "mod_a_rationale_1",
                "relation": "rationale_for",
                "confidence": "EXTRACTED",
                "source_file": "atlas/mod_a.py",
                "source_location": "L1",
                "weight": 1.0,
            },
        ],
        "raw_calls": [
            {
                "caller_nid": "mod_a_foo",
                "callee": "baz",
                "is_member_call": True,
                "source_file": "atlas/mod_a.py",
                "source_location": "L6",
                "receiver": "Bar",
            }
        ],
    }


def _file_b() -> dict:
    """mod_b.py: qux() llama indirectamente (indirect_call/INFERRED) a
    mod_a.foo() — ejercita CALLS con confidence baja y el caso cross-módulo."""
    return {
        "nodes": [
            {
                "id": "mod_b_py",
                "label": "mod_b.py",
                "file_type": "code",
                "source_file": "atlas/mod_b.py",
                "source_location": "L1",
            },
            {
                "id": "mod_b_qux",
                "label": ".qux()",
                "file_type": "code",
                "source_file": "atlas/mod_b.py",
                "source_location": "L3",
                "_callable": True,
            },
            # mod_a_foo se re-declara aquí también (mismo id que en file_a) para
            # que el edge indirect_call tenga su target dentro del MISMO fichero
            # (invariante real verificado: todo edge calls/indirect_call tiene
            # ambos extremos en el `nodes` del mismo JSON).
            {
                "id": "mod_a_foo",
                "label": ".foo()",
                "file_type": "code",
                "source_file": "atlas/mod_a.py",
                "source_location": "L5",
                "_callable": True,
            },
        ],
        "edges": [
            {
                "source": "mod_b_py",
                "target": "mod_b_qux",
                "relation": "contains",
                "confidence": "EXTRACTED",
                "source_file": "atlas/mod_b.py",
                "source_location": "L3",
                "weight": 1.0,
            },
            {
                "source": "mod_b_qux",
                "target": "mod_a_foo",
                "relation": "indirect_call",
                "context": "argument",
                "confidence": "INFERRED",
                "source_file": "atlas/mod_b.py",
                "source_location": "L4",
                "weight": 1.0,
            },
        ],
        "raw_calls": [],
    }


def _write_cache(cache_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{_HASH_A}.json").write_text(json.dumps(_file_a()), encoding="utf-8")
    (cache_dir / f"{_HASH_B}.json").write_text(json.dumps(_file_b()), encoding="utf-8")


def test_load_callgraph_creates_symbols_and_calls(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    _write_cache(cache_dir)
    db_path = tmp_path / "kuzu" / "cg.kuzu"

    result = load_callgraph_into_kuzu(cache_dir, db_path)

    assert result["files"] == 2
    # 5 símbolos de file_a (incl. threading; rationale se excluye) + 2 nuevos de file_b
    # (mod_a_foo se re-declara igual, MERGE no duplica) = 7.
    assert result["symbols"] == 7
    assert result["calls"] == 2  # calls (foo→baz) + indirect_call (qux→foo)

    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)
    try:
        r = conn.execute("MATCH (n:Symbol) RETURN count(n)")
        assert r.get_next()[0] == 7

        # No se cargó el nodo rationale.
        r = conn.execute("MATCH (n:Symbol {id: 'mod_a_rationale_1'}) RETURN count(n)")
        assert r.get_next()[0] == 0

        # kind derivado correctamente.
        r = conn.execute("MATCH (n:Symbol {id: 'mod_a_py'}) RETURN n.kind")
        assert r.get_next()[0] == "file"
        r = conn.execute("MATCH (n:Symbol {id: 'mod_a_bar_baz'}) RETURN n.kind")
        assert r.get_next()[0] == "callable"
        r = conn.execute("MATCH (n:Symbol {id: 'threading'}) RETURN n.kind")
        assert r.get_next()[0] == "external"

        # content_hash queda visible (staleness).
        r = conn.execute("MATCH (n:Symbol {id: 'mod_a_py'}) RETURN n.content_hash")
        assert r.get_next()[0] == _HASH_A

        # CALLS con confidence correcta: EXTRACTED=1.0, INFERRED=0.5.
        r = conn.execute(
            "MATCH (:Symbol {id: 'mod_a_foo'})-[c:CALLS]->(:Symbol {id: 'mod_a_bar_baz'}) "
            "RETURN c.confidence"
        )
        assert r.get_next()[0] == 1.0
        r = conn.execute(
            "MATCH (:Symbol {id: 'mod_b_qux'})-[c:CALLS]->(:Symbol {id: 'mod_a_foo'}) "
            "RETURN c.confidence"
        )
        assert r.get_next()[0] == 0.5

        # CONTAINS: contains + method colapsan a la misma tabla.
        r = conn.execute("MATCH ()-[c:CONTAINS]->() RETURN count(c)")
        assert r.get_next()[0] == 3  # mod_a_py→foo, bar→baz, mod_b_py→qux
    finally:
        conn.close()
        db.close()


def test_load_callgraph_is_idempotent(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    _write_cache(cache_dir)
    db_path = tmp_path / "kuzu" / "cg.kuzu"

    load_callgraph_into_kuzu(cache_dir, db_path)
    result2 = load_callgraph_into_kuzu(cache_dir, db_path)

    assert result2["symbols"] == 7
    assert result2["calls"] == 2

    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)
    try:
        r = conn.execute("MATCH (n:Symbol) RETURN count(n)")
        assert r.get_next()[0] == 7
        r = conn.execute("MATCH ()-[c:CALLS]->() RETURN count(c)")
        assert r.get_next()[0] == 2
        r = conn.execute("MATCH ()-[c:CONTAINS]->() RETURN count(c)")
        assert r.get_next()[0] == 3
    finally:
        conn.close()
        db.close()


def test_load_callgraph_reads_nested_cache_dir(tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache" / "v0.9.11"
        _write_cache(cache_dir)
        db_path = tmp_path / "kuzu" / "cg.kuzu"

        result = load_callgraph_into_kuzu(cache_dir.parent, db_path)

        assert result["files"] == 2
        assert result["symbols"] == 7
        assert result["calls"] == 2

        db = kuzu.Database(str(db_path))
        conn = kuzu.Connection(db)
        try:
            r = conn.execute("MATCH (n:Symbol) RETURN count(n)")
            assert r.get_next()[0] == 7
        finally:
            conn.close()
            db.close()


def test_load_callgraph_filters_and_replaces_with_requested_source_corpus(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    src_data = _file_a()
    for node in src_data["nodes"]:
        if node.get("source_file"):
            node["source_file"] = "src/atlas/mod_a.py"
        if node.get("origin_file"):
            node["origin_file"] = "/repo/src/atlas/mod_a.py"
    test_data = _file_b()
    for node in test_data["nodes"]:
        if node.get("source_file"):
            node["source_file"] = "tests/test_mod_b.py"
        if node.get("origin_file"):
            node["origin_file"] = "/repo/tests/test_mod_b.py"

    (cache_dir / f"{_HASH_A}.json").write_text(json.dumps(src_data), encoding="utf-8")
    (cache_dir / f"{_HASH_B}.json").write_text(json.dumps(test_data), encoding="utf-8")
    db_path = tmp_path / "kuzu" / "cg.kuzu"

    # Primero deja datos ajenos al corpus para demostrar que replace los retira.
    load_callgraph_into_kuzu(cache_dir, db_path)
    result = load_callgraph_into_kuzu(
        cache_dir,
        db_path,
        source_prefix="src/atlas",
        replace=True,
    )

    assert result["files"] == 1
    assert result["symbols"] == 5
    assert result["calls"] == 1

    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)
    try:
        rows = conn.execute("MATCH (n:Symbol) RETURN n.source_file")
        source_files: list[str] = []
        while rows.has_next():
            source_files.append(str(rows.get_next()[0]))
        assert source_files
        assert all(not path.startswith("tests/") for path in source_files)
    finally:
        conn.close()
        db.close()


def test_empty_cache_dir(tmp_path: Path) -> None:
    cache_dir = tmp_path / "empty"
    cache_dir.mkdir()
    result = load_callgraph_into_kuzu(cache_dir, tmp_path / "kuzu" / "e.kuzu")
    assert result == {"symbols": 0, "calls": 0, "files": 0}


def test_strict_mode_rejects_corrupt_cache_instead_of_loading_partial_graph(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "cache"
    _write_cache(cache_dir)
    (cache_dir / "corrupt.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid Graphify AST cache file"):
        load_callgraph_into_kuzu(
            cache_dir,
            tmp_path / "kuzu" / "cg.kuzu",
            strict=True,
        )


# ---------------------------------------------------------------------------
# graph_callers / graph_callees vía build_graph_server sobre la BD tmp
# ---------------------------------------------------------------------------


def test_graph_callers_and_callees(tmp_path: Path) -> None:
    pytest.importorskip("mcp.server.fastmcp")
    from atlas.mcp.graph_server import build_graph_server

    cache_dir = tmp_path / "cache"
    _write_cache(cache_dir)
    db_path = tmp_path / "kuzu" / "cg.kuzu"
    load_callgraph_into_kuzu(cache_dir, db_path)

    server = build_graph_server(db_path)
    tools = {t.name: t for t in server._tool_manager.list_tools()}
    assert {"graph_callers", "graph_callees"} <= set(tools)

    callers = tools["graph_callers"].fn(symbol="baz()")
    names = {c["name"] for c in callers["callers"]}
    assert ".foo()" in names

    callees = tools["graph_callees"].fn(symbol="foo()")
    names = {c["name"] for c in callees["callees"]}
    assert ".baz()" in names


def test_graph_callers_before_ingestion_returns_clean_message(tmp_path: Path) -> None:
    """Sin call-graph ingerido (tabla Symbol ausente): mensaje limpio, no traceback."""
    pytest.importorskip("mcp.server.fastmcp")
    from atlas.mcp.graph_server import build_graph_server

    db_path = tmp_path / "kuzu" / "empty.kuzu"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # BD existente pero sin la tabla Symbol (nunca se corrió load_callgraph_into_kuzu) —
    # read_only=True en build_graph_server no puede *crear* una BD vacía, así que hay
    # que dejarla creada de antemano para reproducir el caso "tabla ausente" real.
    db = kuzu.Database(str(db_path))
    kuzu.Connection(db).close()
    db.close()

    server = build_graph_server(db_path)
    tools = {t.name: t for t in server._tool_manager.list_tools()}

    result = tools["graph_callers"].fn(symbol="foo()")
    assert result == {"error": "call-graph no ingerido aún"}

    result = tools["graph_callees"].fn(symbol="foo()")
    assert result == {"error": "call-graph no ingerido aún"}
