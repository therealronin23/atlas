"""
ADR-028 — Twin Kanban Bridge.

The bidirectional twin-brain channel Atlas <-> Hermes-Agent.

Hermes-Agent's durable kanban board is the explicit outbound collaboration
surface used here. Historical observations about other Hermes transports do
not establish their current upstream state.

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

import hashlib
import ipaddress
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Callable, Sequence, cast

# Type of a transport runner: (argv, timeout_s) -> (returncode, stdout, stderr)
Runner = Callable[[Sequence[str], float], "tuple[int, str, str]"]

DEFAULT_SSH_HOST = ""
DEFAULT_KANBAN_BIN = "/opt/hermes-agent/.venv/bin/hermes"
DEFAULT_LOCAL_KANBAN_BIN = "hermes"
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_TRANSPORT = "ssh"
DEFAULT_SERVICE_USER = "hermes"
DEFAULT_SERVICE_HOME = "/var/lib/hermes"
MAX_TRANSPORT_OUTPUT_BYTES = 1_048_576
ALLOWED_KANBAN_ACTIONS = frozenset(
    {"boards", "create", "list", "show", "comment", "complete", "stats", "archive"}
)
_SSH_DESTINATION_RE = re.compile(
    r"^[a-z_][a-z0-9_-]{0,31}@(?:[A-Za-z0-9][A-Za-z0-9.-]{0,252}|\[[0-9A-Fa-f:]+\])$"
)
_SERVICE_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_REMOTE_BINARY_RE = re.compile(r"^/[A-Za-z0-9_./+~-]+$")
_ALLOWED_SSH_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "fc00::/7",
    )
)


def ssh_destination_is_allowed(value: str) -> bool:
    """Accept only a syntactically safe private/Tailscale SSH destination."""
    if not _SSH_DESTINATION_RE.fullmatch(value):
        return False
    host = value.rsplit("@", 1)[1]
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    normalized = host.casefold().rstrip(".")
    if normalized.endswith(".ts.net"):
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return any(address in network for network in _ALLOWED_SSH_NETWORKS)


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
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        proc = subprocess.run(  # noqa: S603 — argv list, never shell=True
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=stdout_file,
            stderr=stderr_file,
            timeout=timeout_s,
            check=False,
            start_new_session=True,
        )
        stdout = _read_bounded_output(stdout_file)
        stderr = _read_bounded_output(stderr_file)
    return proc.returncode, stdout, stderr


def _read_bounded_output(handle: BinaryIO) -> str:
    handle.seek(0)
    raw: bytes = handle.read(MAX_TRANSPORT_OUTPUT_BYTES + 1)
    if len(raw) > MAX_TRANSPORT_OUTPUT_BYTES:
        raw = raw[:MAX_TRANSPORT_OUTPUT_BYTES] + b"\n[output truncated]\n"
    return raw.decode("utf-8", "replace")


def _argument_metadata(arguments: Sequence[str]) -> dict[str, Any]:
    encoded = json.dumps(
        list(arguments), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return {
        "argument_count": len(arguments),
        "arguments_sha256": hashlib.sha256(encoded).hexdigest(),
    }


class KanbanBridge:
    """Atlas-side client for the Hermes shared kanban board.

    Parameters
    ----------
    merkle:
        Object exposing ``log(action, agent, result, risk_level, payload)``.
        Optional; when present every invocation is recorded.
    ssh_host:
        Private/Tailscale SSH destination of the VPS. Defaults to the explicit
        ``HERMES_SSH_HOST`` environment variable.
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
        service_user: str | None = None,
        transport: str | None = None,
        runner: Runner | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._merkle = merkle
        self._host = ssh_host or os.environ.get("HERMES_SSH_HOST", DEFAULT_SSH_HOST)
        self._bin = kanban_bin or os.environ.get("HERMES_KANBAN_BIN", DEFAULT_KANBAN_BIN)
        self._transport = transport or _resolve_transport()
        self._service_user = service_user or os.environ.get(
            "HERMES_SERVICE_USER", DEFAULT_SERVICE_USER,
        )
        if self._transport not in {"ssh", "local"}:
            raise ValueError("kanban transport must be ssh or local")
        if self._transport == "ssh":
            if not self._host:
                raise ValueError("HERMES_SSH_HOST is required for ssh transport")
            if not ssh_destination_is_allowed(self._host):
                raise ValueError("unsafe or non-private SSH destination")
            if not _REMOTE_BINARY_RE.fullmatch(self._bin):
                raise ValueError("unsafe remote Hermes binary path")
            if not _SERVICE_USER_RE.fullmatch(self._service_user):
                raise ValueError("unsafe Hermes service user")
        self._runner = runner or _default_runner
        self._timeout = timeout_s
        self._board_path = _default_board_path()

    @property
    def transport(self) -> str:
        return self._transport

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
        action = kanban_args[0] if kanban_args else "noop"
        if action not in ALLOWED_KANBAN_ACTIONS:
            raise ValueError(f"unsupported kanban action: {action}")
        if any("\x00" in argument for argument in kanban_args):
            raise ValueError("kanban arguments must not contain NUL bytes")
        argument_metadata = _argument_metadata(kanban_args[1:])
        if self._transport == "local":
            try:
                return self._run_local(action, *kanban_args[1:])
            except OSError as exc:
                self._log(
                    action,
                    "failure",
                    "moderate",
                    {**argument_metadata, "error_type": type(exc).__name__},
                )
                raise

        remote_cmd = shlex.join([
            "runuser",
            "-u",
            self._service_user,
            "--",
            "env",
            f"HOME={DEFAULT_SERVICE_HOME}",
            f"HERMES_HOME={DEFAULT_SERVICE_HOME}/.hermes",
            self._bin,
            "kanban",
            *kanban_args,
        ])
        argv = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=yes",
            "-o", "IdentitiesOnly=yes",
            "-o", "PasswordAuthentication=no",
            "-o", "KbdInteractiveAuthentication=no",
            "-o", "LogLevel=ERROR",
            self._host,
            remote_cmd,
        ]
        try:
            rc, out, err = self._runner(argv, timeout_s or self._timeout)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            self._log(
                action,
                "failure",
                "moderate",
                {**argument_metadata, "error_type": type(exc).__name__},
            )
            raise

        parsed = _try_json(out)
        ok = rc == 0
        self._log(
            action,
            "success" if ok else "failure",
            "moderate",
            {
                **argument_metadata,
                "returncode": rc,
                "transport": self._transport,
            },
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
        triage: bool = False,
    ) -> KanbanResult:
        """Create a task on the current board, optionally assigned to a profile.

        ``title`` is positional. ``--triage`` parks the task so a Hermes
        specifier fleshes out the spec before promoting it to ``todo``.
        Emits ``--json`` so the created task id lands in ``.parsed``.
        """
        args = ["create", title, "--json"]
        if body:
            args += ["--body", body]
        if assignee:
            args += ["--assignee", assignee]
        if triage:
            args.append("--triage")
        return self.run(*args)

    def list_tasks(self, status: str | None = None) -> KanbanResult:
        args = ["list"]
        if status:
            args += ["--status", status]
        return self.run(*args)

    def show_task(self, task_id: str) -> KanbanResult:
        return self.run("show", task_id)

    def comment(self, task_id: str, text: str, author: str | None = None) -> KanbanResult:
        """Append a comment. ``task_id`` and ``text`` are positional."""
        args = ["comment", task_id, text]
        if author:
            args += ["--author", author]
        return self.run(*args)

    def complete(self, task_id: str, result: str | None = None) -> KanbanResult:
        """Close a task. ``task_id`` is positional; ``--result`` is optional."""
        args = ["complete", task_id]
        if result:
            args += ["--result", result]
        return self.run(*args)

    def stats(self) -> KanbanResult:
        return self.run("stats")

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

    def _run_local(self, action: str, *args: str) -> KanbanResult:
        local_cli = os.environ.get("HERMES_KANBAN_LOCAL_BIN", DEFAULT_LOCAL_KANBAN_BIN)
        if shutil.which(local_cli):
            argv = [local_cli, "kanban", action, *args]
            returncode, stdout, stderr = _default_runner(argv, self._timeout)
            parsed = _try_json(stdout)
            ok = returncode == 0
            self._log(
                action,
                "success" if ok else "failure",
                "moderate",
                {
                    **_argument_metadata(args),
                    "transport": "local",
                    "cli": Path(local_cli).name,
                    "returncode": returncode,
                },
            )
            return KanbanResult(
                ok=ok,
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                parsed=parsed,
            )

        board = _load_board(self._board_path)
        result: Any
        if action == "boards":
            result = [{"id": "local", "name": "local-hermes", "transport": "local"}]
        elif action == "stats":
            tasks = board["tasks"]
            result = {
                "total": len(tasks),
                "open": sum(1 for task in tasks if task.get("status") != "done"),
                "done": sum(1 for task in tasks if task.get("status") == "done"),
            }
        elif action == "create":
            result = _local_create(board, args)
            _save_board(self._board_path, board)
        elif action == "list":
            result = _local_list(board, args)
        elif action == "show":
            result = _local_show(board, args)
            if result is None:
                return KanbanResult(ok=False, returncode=1, stdout="", stderr="task not found", parsed=None)
        elif action == "comment":
            result = _local_comment(board, args)
            if result is None:
                return KanbanResult(ok=False, returncode=1, stdout="", stderr="task not found", parsed=None)
            _save_board(self._board_path, board)
        elif action == "complete":
            result = _local_complete(board, args)
            if result is None:
                return KanbanResult(ok=False, returncode=1, stdout="", stderr="task not found", parsed=None)
            _save_board(self._board_path, board)
        else:
            return KanbanResult(ok=False, returncode=2, stdout="", stderr=f"unsupported action: {action}", parsed=None)

        out = json.dumps(result, ensure_ascii=False)
        self._log(
            action,
            "success",
            "moderate",
            {
                **_argument_metadata(args),
                "transport": "local",
                "board_path": str(self._board_path),
            },
        )
        return KanbanResult(ok=True, returncode=0, stdout=out, stderr="", parsed=result)


def _try_json(text: str) -> Any:
    """Best-effort JSON decode; returns None when stdout is not JSON."""
    stripped = (text or "").strip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def _resolve_transport() -> str:
    raw = os.environ.get("HERMES_KANBAN_TRANSPORT", "").strip().lower()
    if raw:
        return raw
    if os.environ.get("HERMES_KANBAN_LOCAL", "").strip().lower() in {"1", "true", "yes"}:
        return "local"
    return DEFAULT_TRANSPORT


def _default_board_path() -> Path:
    raw = os.environ.get("HERMES_KANBAN_BOARD_PATH", "").strip()
    if raw:
        return Path(raw)
    atlas_home = os.environ.get("ATLAS_HOME", "").strip()
    if atlas_home:
        return Path(atlas_home) / "hermes_local" / "kanban_board.json"
    return Path.home() / ".local" / "state" / "atlas-hermes-local" / "kanban_board.json"


def _load_board(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"next_seq": 1, "tasks": []}
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise OSError(f"invalid local board format: {path}")
    data.setdefault("next_seq", 1)
    data.setdefault("tasks", [])
    return data


def _save_board(path: Path, board: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(board, fh, ensure_ascii=False, indent=2, sort_keys=True)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _local_create(board: dict[str, Any], args: Sequence[str]) -> dict[str, Any]:
    if not args:
        raise OSError("create requires title")
    title = args[0]
    body = ""
    assignee = None
    triage = False
    i = 1
    while i < len(args):
        token = args[i]
        if token == "--json":
            i += 1
            continue
        if token == "--body" and i + 1 < len(args):
            body = args[i + 1]
            i += 2
            continue
        if token == "--assignee" and i + 1 < len(args):
            assignee = args[i + 1]
            i += 2
            continue
        if token == "--triage":
            triage = True
            i += 1
            continue
        i += 1
    task_id = f"T-{int(board['next_seq'])}"
    board["next_seq"] = int(board["next_seq"]) + 1
    task: dict[str, Any] = {
        "id": task_id,
        "title": title,
        "body": body,
        "assignee": assignee,
        "status": "triage" if triage else "todo",
        "comments": [],
        "created_at": _utcnow(),
        "completed_at": None,
        "result": None,
    }
    board["tasks"].append(task)
    return task


def _local_list(board: dict[str, Any], args: Sequence[str]) -> list[dict[str, Any]]:
    status = None
    if len(args) >= 2 and args[0] == "--status":
        status = args[1]
    tasks = list(board["tasks"])
    if status:
        tasks = [task for task in tasks if task.get("status") == status]
    return tasks


def _local_show(board: dict[str, Any], args: Sequence[str]) -> dict[str, Any] | None:
    if not args:
        raise OSError("show requires task id")
    task_id = args[0]
    tasks = cast(list[dict[str, Any]], board["tasks"])
    for task in tasks:
        if task.get("id") == task_id:
            return task
    return None


def _local_comment(board: dict[str, Any], args: Sequence[str]) -> dict[str, Any] | None:
    if len(args) < 2:
        raise OSError("comment requires task id and text")
    task_id, text = args[0], args[1]
    author = None
    if len(args) >= 4 and args[2] == "--author":
        author = args[3]
    task = _local_show(board, [task_id])
    if task is None:
        return None
    task.setdefault("comments", []).append({"text": text, "author": author, "created_at": _utcnow()})
    return task


def _local_complete(board: dict[str, Any], args: Sequence[str]) -> dict[str, Any] | None:
    if not args:
        raise OSError("complete requires task id")
    task_id = args[0]
    result = None
    if len(args) >= 3 and args[1] == "--result":
        result = args[2]
    task = _local_show(board, [task_id])
    if task is None:
        return None
    task["status"] = "done"
    task["completed_at"] = _utcnow()
    task["result"] = result
    return task


__all__ = [
    "KanbanBridge", "KanbanResult", "Runner",
    "DEFAULT_SSH_HOST", "DEFAULT_KANBAN_BIN", "DEFAULT_TRANSPORT",
]
