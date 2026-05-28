# ADR-028 — Twin Kanban Bridge (Atlas → Hermes outbound channel)

- **Status:** Accepted (2026-05-29)
- **Depends on:** ADR-026 (Twin architecture), ADR-027 (`/api/exec` inbound)
- **Resolves part of:** ADR-012 (Memory/state sync Hermes ↔ Atlas)

## Context

ADR-027 gave Hermes-Agent (VPS) an authenticated inbound path to Atlas
(`/api/exec/*`). The reverse direction — Atlas asking Hermes to do something —
had no transport.

The obvious candidate, `hermes mcp serve` (expose Hermes conversations over
the Model Context Protocol), is **broken upstream**: both v0.14.0 and v0.15.0
raise `ModuleNotFoundError: No module named 'mcp_serve'` at
`hermes_cli/mcp_config.py:748`. `hermes acp` is editor-oriented (stdio for
VS Code/Zed). Neither offers a usable agent-to-agent surface today.

Hermes-Agent does ship a **durable SQLite-backed kanban board**
(`hermes kanban`) explicitly designed for "tasks claimed atomically, depending
on other tasks, executed by a named profile in an isolated workspace" — i.e.
the intended substrate for multi-agent collaboration. The gateway hosts an
embedded dispatcher that promotes `ready` tasks every 60s.

## Decision

Atlas reaches the Hermes kanban over the existing Tailscale SSH tunnel by
invoking `hermes kanban <subcommand>` on the VPS. This is the outbound twin
channel until/unless a native RPC surface ships.

- **Module:** `src/atlas/hermes/kanban_bridge.py` — `KanbanBridge`.
- **Transport:** stdlib `subprocess` running `ssh <host> hermes kanban ...`.
  No new dependencies (coding rule 6). Runner is injectable for tests.
- **Audit:** every invocation logs `kanban.<action>` to the Merkle ledger
  (coding rule 1), success and failure alike.
- **Direction of authority (ADR-000):** Atlas decides, Hermes executes. Atlas
  *creates and assigns* tasks; Hermes workers *claim and run* them. Atlas
  never cedes control of its own pipeline.

## Non-Negotiables

- Read paths (`boards`, `list`, `show`, `stats`) are safe and unrestricted.
- Write paths (`create`, `comment`, `complete`) are real production mutations
  on a shared board; they must be intentional and audited.
- The bridge never runs `shell=True`; argv is a fixed list and remote args are
  `shlex`-quoted before crossing the SSH boundary.
- Transport failure (ssh missing, timeout) raises so the orchestrator can route
  to the offline path; a non-zero *exit* does not raise (caller inspects `.ok`).

## Flag verification status

The typed wrappers (`create_task`, `list_tasks`, `comment`, `complete`) encode
the best-known `hermes kanban` flags. The read path is verified live
(`reachable()` / `boards` returns rc=0 against the VPS). The write flags
(`--title`, `--body`, `--assignee`, `--status`, `--text`) are pending a live
write confirmation; adjust the wrappers if `hermes kanban create --help`
diverges. The generic `run(*args)` is flag-agnostic and always correct.

## Diagnostics

`atlas doctor` includes an advisory `hermes_twin` check that calls
`KanbanBridge.reachable()`. Advisory because a laptop offline from the VPS is a
normal operating state, not an Atlas fault.

## Future

When Hermes ships a working `mcp serve` (or an HTTP RPC), revisit: MCP would
give synchronous request/response, complementing the kanban's durable async
model. Track upstream: `NousResearch/hermes-agent`.
