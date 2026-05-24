# Gate F Plan

**Status:** in progress.
**Current baseline:** F1 BrowserTool, F2 EditorTool and F3 VisionLoop MVP are
implemented, with explicit Orchestrator routing and local suite `509/509`
green.

Gate F is where Atlas gains real computer-use. The risk is also much higher:
browser automation, editor operations, command execution and future visual loops
all touch the host system. The Gate closes only when those actions are safe,
auditable and approval-aware.

## Scope

| Area | Current state | Required before Gate F close |
|---|---|---|
| BrowserTool | Playwright scaffold, SSRFBridge checks, Merkle logging, local/private-network policy, tests, Orchestrator approval routing for explicit commands | real-host smoke |
| EditorTool | open/read/write/apply_diff/run_task scaffold, tests, AtlasExecutor path, Orchestrator approval routing for explicit commands | real-host smoke |
| Code execution | AtlasExecutor exists; EditorTool uses structured command allowlist | no public raw shell path remains in Gate F tools |
| Visual loop | screenshot -> stub description -> typed ProposedAction; mutating actions force approval; `vision propose` routed by Orchestrator | VLM backend and action-execution approval design |
| Orchestrator integration | explicit routes and approval states for `browser`, `editor`, `vision` commands | CLI/Telegram UX and real-host smoke |
| Packaging | Playwright represented as optional `computer-use` extra | docs/smoke coverage |

## F1: Browser Hardening

1. Add optional `merkle: MerkleLogger | None` to BrowserTool. DONE.
2. Log `browser.launch`, `browser.navigate`, `browser.screenshot`,
   `browser.fill`, `browser.click`, `browser.extract`, and failures. DONE.
3. Add explicit policy for localhost/private-network access: DONE.
   - default SSRFBridge blocks it;
   - tests can inject extra allowlist;
   - runtime local access requires approval or config (`allow_private_network=True`).
4. Add tests that assert audit records are emitted. DONE.
5. Add tests for blocked private IPs and extra allowlist behavior. DONE.

## F2: Editor Hardening

1. Inject `AtlasExecutor` or a small `EditorExecutionPolicy` backed by
   CapabilityIssuer. DONE.
2. Read file through `issue_read` + `execute_read`. DONE.
3. Write file through `issue_write` + `execute_write`. DONE.
4. Run commands through `issue_exec` + `execute_exec`. DONE.
5. Replace public `shell=True` usage with structured command + args. DONE.
6. For `apply_diff`, prefer a safe internal patch path or a narrowly allowlisted
   `git apply` execution through AtlasExecutor. DONE.
7. Add negative tests for blocked paths, blocked commands and oversized writes. DONE.

## F3: Visual Loop MVP

Create `src/atlas/tools/computer_use/vision_loop.py` after F1/F2 hardening. DONE.

First version should be deliberately conservative:

1. Take screenshot from BrowserTool. DONE.
2. Ask a VLM-capable backend or deterministic stub to describe the screen. DONE with deterministic stub.
3. Produce a typed `ProposedAction` such as `click`, `fill`, `navigate`, or
   `stop`. DONE.
4. Route proposed actions through approval if they mutate state or leave the
   current domain. PARTIAL: mutating proposals force `requires_approval=True`;
   Orchestrator routes `vision propose`, but autonomous execution remains out of scope.
5. Log every proposal and decision. PARTIAL: proposals are logged; decisions
   wait for Orchestrator integration.

No autonomous clicking loop until tests cover stop conditions, repetition
limits and approval boundaries.

## F4: ColdUpdateManager

Do not implement until editor hardening is complete.

Gate F may include the design and a minimal prototype, but self-improvement
must be cold:

1. create isolated worktree;
2. generate patch;
3. run tests/mypy;
4. show diff and evidence;
5. require HITL;
6. merge/swap only after approval;
7. rollback on failure.

## Acceptance Criteria

- Full suite passes.
- Mypy passes.
- BrowserTool and EditorTool have audit tests.
- No public raw shell execution path remains in Gate F tools.
- Orchestrator has explicit routes and approval states for Browser/Editor/VisionLoop.
- README/ROADMAP/AGENTS agree on Gate F status.
- ADR-013b is updated or a Gate F seal explicitly references this plan.
