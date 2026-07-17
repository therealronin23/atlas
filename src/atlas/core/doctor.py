"""
Atlas doctor — unified operational diagnostics.

Consolidates the manual health audit (service state, Merkle integrity,
governance, environment, twin reachability) into one introspectable report,
mirroring `hermes doctor` on the VPS side.

Pure read-only: it never mutates state. Each check returns a Check with an
``ok`` flag, a short human label, and structured detail. The aggregate
``status`` is "ok" if every non-advisory check passes, else "degraded".
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    advisory: bool = False  # advisory checks never flip the aggregate to degraded
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "detail": self.detail,
            "advisory": self.advisory,
            "data": self.data,
        }


def _check_governance(orch: Any) -> Check:
    try:
        st = orch.status()
        ok = bool(st.governance_ok)
        return Check("governance", ok, "governance.json validated" if ok else "EMERGENCY mode")
    except Exception as exc:  # noqa: BLE001 — diagnostics must not crash
        return Check("governance", False, f"status() failed: {exc}")


def _check_merkle(orch: Any) -> Check:
    try:
        ok, msg = orch._merkle.verify_chain()
        return Check(
            "merkle_chain",
            ok,
            "chain intact" if ok else f"CORRUPT: {msg}",
            data={"records": orch._merkle.record_count},
        )
    except Exception as exc:  # noqa: BLE001
        return Check("merkle_chain", False, f"verify_chain failed: {exc}")


def _check_workspace(orch: Any) -> Check:
    try:
        ws = Path(orch.status().workspace)
        writable = os.access(ws, os.W_OK)
        return Check(
            "workspace",
            ws.exists() and writable,
            str(ws) if writable else f"{ws} not writable",
            data={"path": str(ws)},
        )
    except Exception as exc:  # noqa: BLE001
        return Check("workspace", False, f"workspace check failed: {exc}")


def _check_env() -> Check:
    """Advisory: surface integration settings that are present (never values).

    Integrations are optional and provider-specific, so absence is not reported
    as a fabricated universal requirement. Completeness belongs to the
    selected integration's own readiness check.
    """
    keys = [
        "HERMES_KANBAN_TRANSPORT",
        "HERMES_SSH_HOST",
        # HERMES_API_KEY/HERMES_BASE_URL: the REST channel they configured was
        # retired in ADR-070. Kept here only so the operator can see they are
        # still set in .env (inert; no code path consumes them anymore).
        "HERMES_API_KEY",
        "HERMES_BASE_URL",
        "HERMES_MODEL_PROVIDER",
        "GROQ_API_KEY",
        "OPENROUTER_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALLOWED_USERS",
        "TELEGRAM_CHAT_ID",
        "ATLAS_DASHBOARD_URL",
    ]
    present = {k: bool(os.environ.get(k, "").strip()) for k in keys}
    present_keys = [key for key, is_present in present.items() if is_present]
    return Check(
        "environment",
        ok=bool(present_keys),
        detail=(
            f"integration settings present: {', '.join(present_keys)}"
            if present_keys
            else "no external integration settings in the process environment"
        ),
        advisory=True,
        data=present,
    )


def _check_hermes_twin(orch: Any, kanban: Any | None) -> Check:
    """Advisory: reachability of the configured native Hermes kanban transport.

    Advisory because a laptop offline from the VPS is a normal operating
    state, not an Atlas fault.
    """
    bridge = kanban
    if bridge is None:
        transport = os.environ.get("HERMES_KANBAN_TRANSPORT", "").strip().lower()
        if not transport:
            return Check(
                "hermes_twin",
                False,
                "native kanban transport not configured",
                advisory=True,
                data={"configured": False, "live_verified": False},
            )
        try:
            from atlas.hermes.kanban_bridge import KanbanBridge

            bridge = KanbanBridge(merkle=getattr(orch, "_merkle", None))
        except Exception as exc:  # noqa: BLE001
            return Check(
                "hermes_twin",
                False,
                f"configured transport invalid: {exc}",
                advisory=True,
                data={"configured": True, "live_verified": False},
            )
    try:
        reachable = bridge.reachable()
    except Exception as exc:  # noqa: BLE001
        return Check(
            "hermes_twin",
            False,
            f"unreachable: {exc}",
            advisory=True,
            data={"configured": True, "live_verified": False},
        )
    return Check(
        "hermes_twin",
        reachable,
        "kanban board reachable" if reachable else "kanban board unreachable",
        advisory=True,
        data={"configured": True, "live_verified": reachable},
    )


def _check_tools(orch: Any) -> Check:
    try:
        n = orch.status().tool_count
        return Check("tools", n > 0, f"{n} tools registered", data={"count": n})
    except Exception as exc:  # noqa: BLE001
        return Check("tools", False, f"tool count failed: {exc}")


def run_diagnostics(orch: Any, kanban: Any | None = None) -> dict[str, Any]:
    """Run all checks and return an aggregate report dict."""
    checks = [
        _check_governance(orch),
        _check_merkle(orch),
        _check_workspace(orch),
        _check_tools(orch),
        _check_env(),
        _check_hermes_twin(orch, kanban),
    ]
    blocking_ok = all(c.ok for c in checks if not c.advisory)
    return {
        "status": "ok" if blocking_ok else "degraded",
        "checks": [c.to_dict() for c in checks],
        "summary": {
            "total": len(checks),
            "passed": sum(1 for c in checks if c.ok),
            "failed": sum(1 for c in checks if not c.ok),
        },
    }


__all__ = ["Check", "run_diagnostics"]
