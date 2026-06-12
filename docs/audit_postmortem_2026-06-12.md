# Audit Postmortem 2026-06-12

## Executive Opinion

Atlas is a serious local runtime with unusually strong structure for a personal
agent project: typed capabilities, Merkle audit, approval persistence,
ColdUpdate, self-maintenance seams, untrusted-content handling, and a central
decider are real.

Atlas was not, however, operationally honest enough. The largest risk found in
this audit was not missing ambition; it was stale self-description. Multiple
agent-facing files carried incompatible counts and live-service claims. That is
dangerous because Atlas uses those files as context for future agents.

“Modo dios” must mean maximum verified capability, not unlimited execution. A
system that lies about its readiness is weaker than a system that says
“unknown”.

## Verified Facts

Commands executed locally:

- `PYTHONPATH=src python -m pytest tests/ -q`
  - Result: `965 passed, 25 deselected`
- `MYPYPATH=src python -m mypy src/atlas/`
  - Result: clean on current source tree
- `PYTHONPATH=src python -m pytest tests/ -q -m "computer_use"`
  - Initial result before browser install/cleanup: browser suite failed because
    Chromium was absent and failed launch polluted subsequent Playwright starts.
- Probe against `LayeredIsolationSandbox.execute_command()` before the fix:
  - Result: `nnp=0 session_leader=False`

## False Or Unsafe Beliefs

- `CLAUDE.md`, `AGENTS.md`, and `ROADMAP.md` disagreed on test counts and ADR
  state.
- Some docs still described Hermes as live while the roadmap also stated the VPS
  was paused.
- “Subprocess hardening” was documented too broadly. The generated-code path was
  hardened, but the structured command path used by `AtlasExecutor.execute_exec`
  did not apply `no_new_privs`, rlimits, or session isolation.
- Computer-use was described as closed, but the local browser evidence was not
  green before installing Playwright browsers and fixing partial-launch cleanup.

## Root Causes

- Operational truth was copied into many human/agent docs instead of generated
  from local state.
- CI made browser/computer-use non-blocking, which allowed core health to be
  conflated with full capability health.
- ADR-034 tests covered `execute(code)` but not `execute_command()`, leaving the
  most common command path outside the proof.
- Browser launch did not clean up Playwright if Chromium failed to start.

## Fixes Applied In This Session

- Added `atlas reality` / `atlas.core.reality` as a factual status surface.
- Added docs freshness detection for contradictory test-count claims.
- Rewrote `AGENTS.md`, `CLAUDE.md`, and `ROADMAP.md` to remove hand-maintained
  operational counts and stale live claims.
- Updated `README.md` to point to `atlas reality` instead of stale audit counts.
- Hardened `LayeredIsolationSandbox.execute_command()` with the same
  `apply_in_child(...)` and `start_new_session=True` used by generated-code
  execution.
- Added command-path hardening tests for `no_new_privs`, session isolation, and
  file-size limits.
- Hardened MCP stdio subprocess startup with child hardening and isolated
  process groups.
- Added a browser launch cleanup path and regression test.
- Installed Playwright Chromium in the local environment for real browser
  verification.

## Residual Risks

- MCP servers remain external programs. Sentinel reduces adoption risk, but tool
  output remains untrusted and runtime egress behavior still deserves deeper
  enforcement.
- Full VM/seccomp isolation is not implemented.
- Autonomous codegen is intentionally constrained. High-risk patches must remain
  human-approved or denied.
- Live LLM/Hermes/Telegram status depends on environment secrets and current
  network state; no doc should claim live operation without a fresh smoke.
- Browser CI is still configured as optional until explicitly tightened.

## Next Gates

- Make browser/computer-use CI required once local and GitHub runners are stable.
- Add a strict readiness mode that fails on stale docs, Merkle corruption,
  failed core/mypy checks, or required degraded capabilities.
- Expand the capability plane so each tool advertises readiness,
  trust/provenance, reversibility, and last evidence.
- Add runtime egress checks around MCP tool calls, not only adoption-time vetting.
