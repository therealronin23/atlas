"""
Atlas insights — usage analytics derived from the Merkle ledger.

Mirrors `hermes insights`: aggregates the append-only audit records Atlas
already writes into counts, success rate, risk distribution and the busiest
agents/actions. Read-only; no new storage, no dependencies.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any


def _parse_ts(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def compute_insights(records: list[dict[str, Any]], window_hours: float | None = None) -> dict[str, Any]:
    """Aggregate audit records into an insights report.

    Parameters
    ----------
    records:
        AuditRecord dicts (action, agent, result, risk_level, timestamp, ...).
    window_hours:
        If given, only records within the last ``window_hours`` are counted.
    """
    if window_hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        kept = []
        for r in records:
            ts = _parse_ts(r.get("timestamp", ""))
            if ts is not None and ts >= cutoff:
                kept.append(r)
        records = kept

    total = len(records)
    by_result: Counter[str] = Counter(r.get("result", "unknown") for r in records)
    by_risk: Counter[str] = Counter(r.get("risk_level", "unknown") for r in records)
    by_agent: Counter[str] = Counter(r.get("agent", "unknown") for r in records)
    by_action: Counter[str] = Counter(r.get("action", "unknown") for r in records)

    success = by_result.get("success", 0)
    failure = by_result.get("failure", 0) + by_result.get("blocked", 0)
    decided = success + failure
    success_rate = round(success / decided, 4) if decided else None

    return {
        "window_hours": window_hours,
        "total_events": total,
        "success_rate": success_rate,
        "by_result": dict(by_result.most_common()),
        "by_risk": dict(by_risk.most_common()),
        "top_agents": by_agent.most_common(10),
        "top_actions": by_action.most_common(10),
    }


__all__ = ["compute_insights"]
