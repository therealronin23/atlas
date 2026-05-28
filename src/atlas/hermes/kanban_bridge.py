"""
ADR-028 — Twin Kanban Bridge.

The bidirectional twin-brain channel Atlas <-> Hermes-Agent.

Hermes-Agent (Nous Research) does not expose a callable REST surface (the
`hermes mcp serve` transport is broken upstream as of v0.15.0). Its durable
SQLite-backed kanban board, however, is shared across profiles and is the
intended substrate for agent-to-agent collaboration: tasks are claimed
atomically, can depend on each other, and are executed by a named profile in
an isolated workspace.

Atlas reaches that board over the Tailscale SSH tunnel by invoking
`hermes kanban <subcommand>` on the VPS. Inbound (Hermes -> Atlas) already
exists via /api/exec/intent (ADR-027); this module is the outbound half.

Design constraints (AGENTS.md coding rules):
  - stdlib only (subprocess + shlex). No new dependencies (rule 6).
  - Every invocation is logged to the Merkle ledger (rule 1).
  - The transport runner is injectable so the bridge is unit-testable without
    a live VPS.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

# Type of a transport runner: (argv, timeout_s) -> (returncode, stdout, stderr)
Runner = Callable[[Sequence[str], float], "tuple[int, str, str]"]

DEFAULT_SSH_HOST = "root@178.105.216.187"
DEFAULT_KANBAN_BIN = "/root/.hermes/venv/bin/hermes"
DEFAULT_TIMEOUT_S = 30.0


@dataclass
class KanbanResult:
    """Outcome of a single kanban invocation."""

    ok: bool
    returncode: int
    stdout: str
    stderr: str
    parsed: Any = None  # decoded JSON when the subcommand emitted JSON

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "parsed": self.parsed,
        }


def _default_runner(argv: Sequence[str], timeout_s: float) -> "tuple[int, str, str]":
    proc = subprocess.run(  # noqa: S603 — argv is a fixed list, never shell=True
        list(argv),
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    return proc.returncode, proc.stdout, proc.stderr


class KanbanBridge:
    """Atlas-side client for the Hermes shared kanban board.

    Parameters
    ----------
    merkle:
        Object exposing ``log(action, agent, result, risk_level, payload)``.
        Optional; when present every invocation is recorded.
    ssh_host:
        SSH destination of the VPS. Defaults to ``HERMES_SSH_HOST`` env var or
        the Tailscale/public IP from runtime config.
    kanban_bin:
        Path to the ``hermes`` binary on the VPS.
    runner:
        Injectable transport. Defaults to a real SSH subprocess call.
    """

    AGENT = "kanban_bridge"

    def __init__(
        self,
        merkle: Any | None = None,
        ssh_host: str | None = None,
        kanban_bin: str | None = None,
        runner: Runner | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._merkle = merkle
        self._host = ssh_host or os.environ.get("HERMES_SSH_HOST", DEFAULT_SSH_HOST)
        self._bin = kanban_bin or os.environ.get("HERMES_KANBAN_BIN", DEFAULT_KANBAN_BIN)
        self._runner = runner or _default_runner
        self._timeout = timeout_s

    # ------------------------------------------------------------------
    # Core invocation
    # ------------------------------------------------------------------

    def run(self, *kanban_args: str, timeout_s: float | None = None) -> KanbanResult:
        """Invoke ``hermes kanban <kanban_args...>`` on the VPS over SSH.

        Returns a KanbanResult. Never raises on a non-zero exit; the caller
        inspects ``.ok``. Raises only on transport-level failure
        (e.g. ssh binary missing, timeout) so the orchestrator can route it
        to the offline path.
        """
        remote_cmd = shlex.join([self._bin, "kanban", *kanban_args])
        argv = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5",
            self._host,
            remote_cmd,
        ]
        action = kanban_args[0] if kanban_args else "noop"
        try:
            rc, out, err = self._runner(argv, timeout_s or self._timeout)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            self._log(action, "failure", "moderate", {"error": str(exc), "args": list(kanban_args)})
            raise

        parsed = _try_json(out)
        ok = rc == 0
        self._log(
            action,
            "success" if ok else "failure",
            "moderate",
            {"args": list(kanban_args), "returncode": rc},
        )
        return KanbanResult(ok=ok, returncode=rc, stdout=out, stderr=err, parsed=parsed)

    # ------------------------------------------------------------------
    # Typed convenience wrappers
    # ------------------------------------------------------------------

    def reachable(self) -> bool:
        """True if the board responds (used by `atlas doctor`)."""
        try:
            return self.run("boards").ok
        except OSError:
            return False

    def create_task(
        self,
        title: str,
        body: str = "",
        assignee: str | None = None,
        board: str | None = None,
    ) -> KanbanResult:
        """Create a task on the board, optionally assigned to a Hermes profile."""
        args = ["create", "--title", title]
        if body:
            args += ["--body", body]
        if assignee:
            args += ["--assignee", assignee]
        if board:
            args = ["--board", board] + args
        return self.run(*args)

    def list_tasks(self, status: str | None = None, board: str | None = None) -> KanbanResult:
        args: list[str] = []
        if board:
            args += ["--board", board]
        args.append("list")
        if status:
            args += ["--status", status]
        return self.run(*args)

    def show_task(self, task_id: str) -> KanbanResult:
        return self.run("show", task_id)

    def comment(self, task_id: str, text: str) -> KanbanResult:
        return self.run("comment", task_id, "--text", text)

    def complete(self, task_id: str) -> KanbanResult:
        return self.run("complete", task_id)

    def stats(self, board: str | None = None) -> KanbanResult:
        args = (["--board", board] if board else []) + ["stats"]
        return self.run(*args)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _log(self, action: str, result: str, risk: str, payload: dict[str, Any]) -> None:
        if self._merkle is None:
            return
        self._merkle.log(
            action=f"kanban.{action}",
            agent=self.AGENT,
            result=result,
            risk_level=risk,
            payload=payload,
        )


def _try_json(text: str) -> Any:
    """Best-effort JSON decode; returns None when stdout is not JSON."""
    stripped = (text or "").strip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


__all__ = ["KanbanBridge", "KanbanResult", "Runner", "DEFAULT_SSH_HOST", "DEFAULT_KANBAN_BIN"]
