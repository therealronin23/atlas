# ADR-013b — Computer-Use

**Status:** resolved (Gate F)
**Date:** 2026-05-25

## Decision

Atlas supports computer-use through explicit, auditable tools:

- `BrowserTool` uses Playwright for browser automation.
- `EditorTool` handles project file IO, diff application and allowlisted tasks.
- `VisionLoop` observes a screen and proposes a typed next action.
- `Orchestrator` routes explicit `browser`, `editor` and `vision` commands.

Computer-use is allowed only inside Atlas' security model. External-effect
actions must be logged to MerkleLogger. Filesystem and command execution must
go through `PermissionProfile`, capability tokens and `AtlasExecutor`.

## Boundaries

- Browser navigation, click and fill require approval at Orchestrator level.
- Editor write, apply_diff, run_task and open_project require approval.
- Editor read, browser screenshot/extract and vision propose are observational.
- Local/private browser URLs require explicit operator configuration
  (`allow_private_network=True`) in addition to SSRF allowlisting.
- The visual loop may propose actions, but it does not execute an autonomous
  click/fill/navigate loop in Gate F.
- No raw public `shell=True` path is allowed in Gate F tools.
- No runtime dependency on Open Interpreter, Aider, Anthropic, Codex or OpenAI
  APIs is introduced by this ADR.

## Accepted Implementation

- `src/atlas/tools/browser.py`
- `src/atlas/tools/editor.py`
- `src/atlas/tools/computer_use/vision_loop.py`
- `src/atlas/core/orchestrator.py`
- `tests/test_browser.py`
- `tests/test_editor.py`
- `tests/test_vision_loop.py`
- `tests/test_orchestrator_gate_f.py`

## Verification

Gate F closes with:

- full test suite: `509 passed`;
- mypy: `Success: no issues found in 44 source files`;
- real-host Gate F smoke: editor read/write/run, browser navigate/screenshot/extract,
  vision propose, approval flow and Merkle verification;
- local L0 inference smoke through Ollama using `qwen2.5:0.5b`.

## Deferred

- Autonomous multi-step visual action loops.
- VLM backend selection beyond deterministic/stub proposal flow.
- CLI/Telegram UX sugar for approval review beyond the existing pending flow.
- ColdUpdateManager implementation, tracked by ADR-025.
