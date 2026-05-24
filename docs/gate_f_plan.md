# Gate F Plan

**Status:** in progress.
**Current baseline:** F1 BrowserTool and F2 EditorTool scaffolds exist, with
local suite `494/494` green.

Gate F is where Atlas gains real computer-use. The risk is also much higher:
browser automation, editor operations, command execution and future visual loops
all touch the host system. The Gate closes only when those actions are safe,
auditable and approval-aware.

## Scope

| Area | Current state | Required before Gate F close |
|---|---|---|
| BrowserTool | Playwright scaffold, SSRFBridge checks, tests | Merkle logging for every action; approval policy for extra/local allowlists |
| EditorTool | open/read/write/apply_diff/run_task scaffold, tests | PermissionProfile + AtlasExecutor + MerkleLogger for all IO/effects |
| Code execution | AtlasExecutor exists; EditorTool has raw `shell=True` path | no public raw shell path; command allowlist enforced |
| Visual loop | not implemented | screenshot -> VLM/stub -> proposed action; no execution without approval |
| Orchestrator integration | Browser/Editor not routed by Orchestrator | explicit routes and approval states |
| Packaging | Playwright optional in environment, not formalized | optional extras/docs for Gate F dependencies |

## F1: Browser Hardening

1. Add optional `merkle: MerkleLogger | None` to BrowserTool.
2. Log `browser.launch`, `browser.navigate`, `browser.screenshot`,
   `browser.fill`, `browser.click`, `browser.extract`, and failures.
3. Add explicit policy for localhost/private-network access:
   - default SSRFBridge blocks it;
   - tests can inject extra allowlist;
   - runtime local access requires approval or config.
4. Add tests that assert audit records are emitted.
5. Add tests for blocked private IPs and extra allowlist behavior.

## F2: Editor Hardening

1. Inject `AtlasExecutor` or a small `EditorExecutionPolicy` backed by
   CapabilityIssuer.
2. Read file through `issue_read` + `execute_read`.
3. Write file through `issue_write` + `execute_write`.
4. Run commands through `issue_exec` + `execute_exec`.
5. Replace public `shell=True` usage with structured command + args.
6. For `apply_diff`, prefer a safe internal patch path or a narrowly allowlisted
   `git apply` execution through AtlasExecutor.
7. Add negative tests for blocked paths, blocked commands and oversized writes.

## F3: Visual Loop MVP

Create `src/atlas/tools/computer_use/vision_loop.py` after F1/F2 hardening.

First version should be deliberately conservative:

1. Take screenshot from BrowserTool.
2. Ask a VLM-capable backend or deterministic stub to describe the screen.
3. Produce a typed `ProposedAction` such as `click`, `fill`, `navigate`, or
   `stop`.
4. Route proposed actions through approval if they mutate state or leave the
   current domain.
5. Log every proposal and decision.

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
- README/ROADMAP/AGENTS agree on Gate F status.
- ADR-013b is updated or a Gate F seal explicitly references this plan.

