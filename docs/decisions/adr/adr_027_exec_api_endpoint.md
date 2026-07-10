# ADR-027 — `/api/exec` Endpoint (Hermes-driven capability execution)

- **Status:** Accepted (2026-05-28)
- **Depends on:** ADR-020 (Capability tokens), ADR-026 (Twin architecture)

## Context

ADR-026 deployed the twin pair (Atlas-laptop ↔ Hermes-Agent-VPS). The twin
communicates one-way today: Hermes can call Atlas's read-only dashboard
(`/api/health`), but cannot ask Atlas to execute anything on the laptop.

That gap blocks the headline use case: "I'm out with my phone, the Telegram
bot can chat but it can't actually do anything on my laptop." Users want to
ask Hermes — and have Hermes ask Atlas — to:

- Open a URL in Chrome (e.g. RustDesk login flow)
- Run `git pull` in a known workspace
- Read a file, dump it back via Telegram
- Click a button, type a sequence, screenshot the desktop

All of these are already possible via `AtlasExecutor` + capability tokens
(ADR-020) for any caller that has *in-process* access to the orchestrator.
What's missing is a **secure, audited HTTP path** so Hermes (out-of-process,
remote) can invoke them.

## Decision

Atlas Core exposes a new `/api/exec/*` family of REST endpoints on the
existing dashboard FastAPI app, gated by **HMAC-SHA256 with the shared
`HERMES_API_KEY`** (same secret already established for `HermesAdapter`).

```
POST  /api/exec/shell      execute a shell command (allowlist-bounded)
POST  /api/exec/file       read/write a single file (capability-bounded)
POST  /api/exec/browser    Playwright action (open/click/screenshot)
POST  /api/exec/computer   xdotool-class action (mouse/keyboard) — requires Xvfb/X11
```

### Authentication

Each request must include:

- `X-Hermes-Signature: hex(hmac_sha256(HERMES_API_KEY, request_body))`
- `X-Hermes-Timestamp: ISO-8601` (rejected if drift > 300 s, prevents replay)

The HMAC is verified against `HERMES_API_KEY` from Atlas's environment. If
the key isn't configured, the endpoint returns **503** (not 401, to make the
operational misconfiguration obvious in logs).

### Authorization

After HMAC succeeds, the endpoint goes through the **existing** ADR-020
pipeline:

1. `CapabilityIssuer` mints an ephemeral token for the requested action
   (raises `CapabilityDenied` if PermissionProfile blocks it)
2. `AtlasExecutor.execute_*` runs the action with that token
3. Action + outcome land in MerkleLogger as a forensic entry

This means **nothing changes about Atlas's security model**. Hermes doesn't
gain new privileges — it gains a *transport* to the same capability gate
Atlas uses internally. The PermissionProfile is the single source of truth
for what can run.

### Audit trail

Every `/api/exec` call writes at least one Merkle entry:

```
action:  exec.<verb>.via_hermes
agent:   exec_api
risk:    safe | moderate | high | critical
payload: {command, returncode, duration_ms, hmac_kid}
```

A separate WAL entry goes via the ObservabilityStack so the dashboard's
"Recent activity" panel shows Hermes-driven actions in real time.

## Consequences

### What this enables

- Hermes-side skill (SKILL.md in a tap or local) wraps the endpoints and
  exposes them to the Hermes LLM as native tools. The user prompt
  *"abre github.com en chrome"* now actually opens the browser on the
  laptop.
- The Telegram bot becomes an effective remote-control interface, gated
  by the same governance and Merkle log as direct CLI use.
- Future remote interfaces (web app, mobile companion) reuse the same
  HMAC-protected endpoints.

### Failure modes

| Failure | Behavior |
|---|---|
| Missing `HERMES_API_KEY` | 503 + Merkle `exec.refused.no_key` |
| HMAC mismatch | 401 + Merkle `exec.refused.bad_signature` (with rate-limited counter) |
| Timestamp drift > 300 s | 401 + Merkle `exec.refused.stale_request` |
| `CapabilityDenied` | 403 + Merkle `exec.refused.capability_denied` |
| Action raises | 500 + Merkle `exec.failed.<verb>` with exception text |

All refusals are logged; no information about what was requested leaks back
to the caller beyond the HTTP code.

### Non-decisions

- No JWT, OAuth, or session cookies. HMAC + timestamp is sufficient for
  the symmetric, single-tenant trust model (Atlas and Hermes are the only
  two principals).
- No rate-limiting in the endpoint itself. PermissionProfile already caps
  shell, file, and browser. Add rate limiting later if abuse is observed.
- The endpoint is **not** exposed on the public IP. Listens on `:7331`
  bound to `127.0.0.1` (already default) + reachable from the Tailscale
  interface. To talk to Atlas, Hermes must already be in the Tailscale mesh.

### Migration

No migration needed. `/api/exec/*` is additive. The legacy `HermesAdapter`
REST contract (Atlas → Hermes-stub) is preserved for backward compat in
the code but is no longer used (the stub is retired; see ADR-026).
