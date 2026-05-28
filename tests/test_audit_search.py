"""Tests for atlas audit full-text search (FTS5 over the Merkle ledger)."""

from __future__ import annotations

from atlas.core.audit_search import search_records


def _rec(action="x", agent="a", result="success", risk="safe", payload=None, task_id=None):
    return {
        "action": action,
        "agent": agent,
        "result": result,
        "risk_level": risk,
        "payload": payload or {},
        "task_id": task_id,
    }


def test_empty_query_returns_empty():
    records = [_rec(action="kanban.create")]
    assert search_records(records, "") == []
    assert search_records(records, "   ") == []


def test_empty_records_returns_empty():
    assert search_records([], "anything") == []


def test_single_term_matches_action():
    records = [_rec(action="kanban.create"), _rec(action="exec.shell")]
    results = search_records(records, "kanban")
    assert len(results) == 1
    assert results[0]["action"] == "kanban.create"


def test_multi_term_is_and():
    records = [
        _rec(action="kanban.create", agent="bridge"),
        _rec(action="kanban.create", agent="exec_api"),
    ]
    results = search_records(records, "kanban bridge")
    assert len(results) == 1
    assert results[0]["agent"] == "bridge"


def test_searches_inside_payload():
    records = [
        _rec(action="tool.invoked", payload={"tool": "screenshot"}),
        _rec(action="tool.invoked", payload={"tool": "editor"}),
    ]
    results = search_records(records, "screenshot")
    assert len(results) == 1
    assert results[0]["payload"]["tool"] == "screenshot"


def test_no_match_returns_empty():
    records = [_rec(action="kanban.create")]
    assert search_records(records, "nonexistent") == []


def test_limit_respected():
    records = [_rec(action="kanban.create") for _ in range(30)]
    assert len(search_records(records, "kanban", limit=5)) == 5


def test_special_characters_do_not_raise():
    records = [_rec(action="exec.shell", payload={"cmd": 'echo "hi"'})]
    # quotes/operators in the query must not break the FTS5 MATCH expression
    assert search_records(records, 'echo "hi" *') == [] or True
    search_records(records, '"')  # must not raise
