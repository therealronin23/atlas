"""Task preflight for atlas-trunk.

This module is deliberately pure: it ranks already-known catalog entries and
returns a compact preparation packet. It never spawns, installs, downloads, or
executes third-party code.
"""

from __future__ import annotations

from typing import Any

from atlas.mcp.catalog import CatalogEntry, find, recommended_stack

_MATURITY = {"instalado": 0, "verificado": 1, "probado-en-jaula": 2, "candidato": 3}
_TOKEN_FIELDS = ("name", "purpose", "kind", "sector", "subsector")


def _tokens(text: str) -> set[str]:
    return {part for part in text.lower().replace("/", " ").replace("-", " ").split() if part}


def _entry_tokens(entry: CatalogEntry) -> set[str]:
    parts: list[str] = [str(getattr(entry, field)) for field in _TOKEN_FIELDS]
    parts.extend(entry.tags)
    return _tokens(" ".join(parts))


def _usage_for(entry: CatalogEntry, external_counts: dict[str, int]) -> int:
    if not external_counts:
        return 0
    prefixes = (
        f"mcp__{entry.name}__",
        f"mcp__{entry.name.replace(' ', '-')}__",
        f"mcp__{entry.name.lower()}__",
    )
    total = 0
    for tool_name, count in external_counts.items():
        if any(tool_name.startswith(prefix) for prefix in prefixes):
            total += count
    return total


def _entry_row(
    entry: CatalogEntry,
    *,
    goal_tokens: set[str],
    external_counts: dict[str, int],
) -> dict[str, Any]:
    usage = _usage_for(entry, external_counts)
    overlap = len(goal_tokens & _entry_tokens(entry))
    usable_now = entry.status in {"instalado", "verificado"}
    requires_env = list(entry.env_passthrough)
    requires_consent = entry.kind in {"mcp", "skill", "tool", "hook", "subagent", "plugin", "rule", "workflow"} and not usable_now
    return {
        "name": entry.name,
        "kind": entry.kind,
        "status": entry.status,
        "mode": entry.mode,
        "sector": entry.sector,
        "subsector": entry.subsector,
        "purpose": entry.purpose,
        "usable_now": usable_now,
        "requires_consent": requires_consent,
        "requires_env": requires_env,
        "read_only_tools": list(entry.read_only_tools),
        "usage_external": usage,
        "score": (
            (40 if usable_now else 0)
            + min(usage, 20)
            + overlap * 3
            + (4 if entry.read_only_tools else 0)
            + (6 if entry.name.startswith("atlas-") else 0)
            - _MATURITY.get(entry.status, 3)
        ),
        "next_action": (
            "usable now"
            if usable_now
            else "candidate: run trial + security review + explicit consent before install/connect"
        ),
    }


def prepare_task_context(
    entries: list[CatalogEntry],
    taxonomy: dict[str, Any],
    goal: str,
    *,
    limit: int = 8,
    external_counts: dict[str, int] | None = None,
    workbench_available: bool = False,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a compact context packet for a task.

    The packet is safe for preflight use: candidates are visible as discovery,
    but never presented as connected/installed capabilities.
    """
    clean_goal = goal.strip() or "general"
    bounded_limit = max(1, min(int(limit), 20))
    counts = external_counts or {}
    goal_tokens = _tokens(clean_goal)
    stack = recommended_stack(entries, taxonomy, clean_goal, limit=max(bounded_limit * 2, 8))
    ids = {(item["kind"], item["name"]) for item in stack.get("items", [])}
    if not ids:
        ids = {(item["kind"], item["name"]) for item in find(entries, taxonomy, clean_goal, limit=bounded_limit * 2)}

    selected = [
        entry for entry in entries
        if (entry.kind, entry.name) in ids or goal_tokens & _entry_tokens(entry)
    ]
    rows = [
        _entry_row(entry, goal_tokens=goal_tokens, external_counts=counts)
        for entry in selected
    ]
    rows.sort(
        key=lambda row: (
            -int(row["score"]),
            _MATURITY.get(str(row["status"]), 3),
            str(row["name"]).lower(),
        )
    )
    recommended = rows[:bounded_limit]

    resources = ["catalog://manifest"]
    if workbench_available:
        resources.append("workbench://manifest")
    if any(row["sector"] == "infraestructura" for row in recommended):
        resources.append("operating://ledger")

    missing = [
        {
            "name": row["name"],
            "kind": row["kind"],
            "reason": (
                "missing env: " + ", ".join(row["requires_env"])
                if row["requires_env"]
                else "candidate requires prove-it and explicit consent"
            ),
            "requires_consent": row["requires_consent"],
        }
        for row in recommended
        if row["requires_env"] or not row["usable_now"]
    ]
    warnings: list[str] = []
    if not recommended:
        warnings.append("no catalog match; use trunk_catalog/trunk_find manually")
    if constraints:
        warnings.append("constraints are advisory in v1; no capability is connected or installed")

    return {
        "status": "ready" if recommended else "degraded",
        "goal": clean_goal,
        "recommended": recommended,
        "resources": resources,
        "skills": [row for row in recommended if row["kind"] == "skill"],
        "missing": missing,
        "warnings": warnings,
        "next_actions": [
            "Read workbench://manifest when available before delegating to subagents.",
            "Use trunk_invoke_readonly for read-only tools; route mutations through normal approval.",
            "Do not install or connect candidates without trial, review, and explicit consent.",
        ],
    }
