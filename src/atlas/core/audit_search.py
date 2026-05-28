"""
Atlas audit search — full-text search over the Merkle ledger.

Absorbs the full-text search behind `hermes sessions`. Uses the SQLite FTS5
extension shipped with stdlib ``sqlite3`` (no new dependency, coding rule 6).
Read-only: an ephemeral in-memory index is built from the append-only audit
records on each query, so there is no second source of truth to keep in sync.

When the local SQLite build lacks FTS5 (rare, but the VPS and the laptop ship
different builds), it degrades to a substring AND match — same results shape,
no relevance ranking.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any


def _fts5_available() -> bool:
    con = sqlite3.connect(":memory:")
    try:
        con.execute("CREATE VIRTUAL TABLE _probe USING fts5(x)")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        con.close()


def _doc_text(rec: dict[str, Any]) -> str:
    """Flatten a record into the searchable document body."""
    payload = rec.get("payload", {})
    try:
        payload_text = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        payload_text = str(payload)
    parts = (
        rec.get("action", ""),
        rec.get("agent", ""),
        rec.get("result", ""),
        rec.get("risk_level", ""),
        rec.get("task_id") or "",
        payload_text,
    )
    return " ".join(str(p) for p in parts)


def _fts_match_expr(query: str) -> str:
    """Turn free text into a safe FTS5 MATCH expression (AND of quoted terms).

    Quoting each term as a phrase neutralises FTS5 operator syntax in user
    input (e.g. a stray ``"`` or ``*``) that would otherwise raise.
    """
    terms = re.findall(r"\S+", query)
    return " ".join('"' + t.replace('"', '""') + '"' for t in terms)


def _fts_search(records: list[dict[str, Any]], query: str, limit: int) -> list[dict[str, Any]]:
    con = sqlite3.connect(":memory:")
    try:
        con.execute("CREATE VIRTUAL TABLE docs USING fts5(body, idx UNINDEXED)")
        con.executemany(
            "INSERT INTO docs(body, idx) VALUES (?, ?)",
            [(_doc_text(r), i) for i, r in enumerate(records)],
        )
        cur = con.execute(
            "SELECT idx FROM docs WHERE docs MATCH ? ORDER BY bm25(docs) LIMIT ?",
            (_fts_match_expr(query), limit),
        )
        idxs = [row[0] for row in cur.fetchall()]
    finally:
        con.close()
    return [records[i] for i in idxs]


def _like_search(records: list[dict[str, Any]], query: str, limit: int) -> list[dict[str, Any]]:
    terms = [t.lower() for t in re.findall(r"\S+", query)]
    out: list[dict[str, Any]] = []
    for rec in reversed(records):  # newest first when there is no relevance score
        body = _doc_text(rec).lower()
        if all(t in body for t in terms):
            out.append(rec)
            if len(out) >= limit:
                break
    return out


def search_records(
    records: list[dict[str, Any]], query: str, limit: int = 20
) -> list[dict[str, Any]]:
    """Search audit records for ``query``.

    Multi-word queries are an implicit AND. Returns matching records ordered by
    relevance (FTS5/bm25) when available, newest-first otherwise. An empty or
    whitespace-only query returns ``[]``.
    """
    query = (query or "").strip()
    if not query or not records:
        return []
    if _fts5_available():
        return _fts_search(records, query, limit)
    return _like_search(records, query, limit)


__all__ = ["search_records"]
