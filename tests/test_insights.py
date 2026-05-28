"""Tests for atlas insights aggregation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from atlas.core.insights import compute_insights


def _rec(action="x", agent="a", result="success", risk="safe", ts=None):
    return {
        "action": action,
        "agent": agent,
        "result": result,
        "risk_level": risk,
        "timestamp": ts or datetime.now(timezone.utc).isoformat(),
    }


def test_empty_records():
    report = compute_insights([])
    assert report["total_events"] == 0
    assert report["success_rate"] is None


def test_counts_and_success_rate():
    records = [
        _rec(result="success"),
        _rec(result="success"),
        _rec(result="failure"),
        _rec(result="blocked"),
    ]
    report = compute_insights(records)
    assert report["total_events"] == 4
    # 2 success of 4 decided (2 success + 1 failure + 1 blocked)
    assert report["success_rate"] == 0.5
    assert report["by_result"]["success"] == 2


def test_top_agents_and_actions():
    records = [_rec(agent="exec_api", action="exec.shell") for _ in range(3)]
    records += [_rec(agent="kanban_bridge", action="kanban.create")]
    report = compute_insights(records)
    assert report["top_agents"][0] == ("exec_api", 3)
    assert report["top_actions"][0] == ("exec.shell", 3)


def test_risk_distribution():
    records = [_rec(risk="high"), _rec(risk="safe"), _rec(risk="safe")]
    report = compute_insights(records)
    assert report["by_risk"]["safe"] == 2
    assert report["by_risk"]["high"] == 1


def test_window_filters_old_records():
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    recent = datetime.now(timezone.utc).isoformat()
    records = [_rec(ts=old), _rec(ts=recent), _rec(ts=recent)]
    report = compute_insights(records, window_hours=24)
    assert report["total_events"] == 2


def test_window_ignores_unparseable_timestamps():
    records = [_rec(ts="not-a-date"), _rec(ts=datetime.now(timezone.utc).isoformat())]
    report = compute_insights(records, window_hours=24)
    assert report["total_events"] == 1
