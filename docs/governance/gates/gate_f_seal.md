# Gate F — Seal

**Date:** 2026-05-25
**Status:** COMPLETE
**Tests:** 509/509 passing
**mypy:** green on 44 source files
**Tag:** `v0.5-gate-f`

## Summary

Gate F closes the first real computer-use layer for Atlas. Browser automation,
editor operations and visual observation now exist as explicit tools, and the
Orchestrator can route them through approval states.

The security posture remains aligned with the core architecture:

- browser actions are validated by SSRFBridge and logged to MerkleLogger;
- editor read/write/apply_diff/run_task routes through capability tokens and
  AtlasExecutor;
- command execution uses structured command/args, not public raw shell strings;
- mutating browser/editor actions wait in `AWAITING_APPROVAL`;
- visual loop proposes actions only; it does not execute autonomous loops.

## Delivered

| Area | Result |
|---|---|
| F1 BrowserTool | Playwright navigation, fill, click, extract and screenshots with Merkle logging and local/private-network policy. |
| F2 EditorTool | open_project, read_file, write_file, apply_diff and run_task through PermissionProfile + AtlasExecutor. |
| F3 VisionLoop | screenshot -> deterministic description -> typed ProposedAction; mutating proposals require approval. |
| F4 Orchestrator routing | explicit `browser`, `editor` and `vision` commands with approval states for mutating actions. |
| Packaging | optional `computer-use` extra includes Playwright. |
| ADR | ADR-013b resolved by `docs/adr_013b_computer_use.md`. |

## Evidence

```bash
# Full suite
PYTHONPATH=src python -m pytest tests/ -q
# -> 509 passed

# Type check
MYPYPATH=src python -m mypy src/atlas/
# -> Success: no issues found in 44 source files
```

Real-host Gate F smoke passed on 2026-05-25:

- temporary local HTTP page served on `127.0.0.1`;
- `editor read projects/input.txt` completed without approval;
- `editor write projects/output.txt :: ...` waited for approval and wrote via AtlasExecutor;
- `editor run tmp :: echo gate-f-run` waited for approval and executed via AtlasExecutor;
- `browser navigate <local smoke URL>` waited for approval, then loaded with status 200;
- `browser screenshot gate_f_smoke` produced a PNG;
- `browser extract` returned page text;
- `vision propose gate_f_vision` returned a safe `stop` proposal;
- Merkle chain verified after the smoke;
- smoke workspace recorded 37 Merkle entries.

Local inference readiness also passed:

```bash
ollama list
# llama3.2:latest, qwen2.5:0.5b

# InferenceHub live L0 via Ollama qwen2.5:0.5b
# -> success=True, latency_ms=4144, text="Operativo Atlas"
```

## Non-Goals

- No autonomous browser action loop.
- No VLM-backed action executor.
- No cold self-improvement implementation.
- No Kubernetes, distributed fleet or eBPF autonomy in Gate F.
- No new frontier API runtime dependency.

## Follow-Ups

- Gate G: decide whether CLI/Telegram should expose a richer approval UX for
  Gate F commands.
- Gate G/H: ColdUpdateManager MVP from ADR-025.
- Future: VLM-backed `ScreenDescriber` once approval and repetition limits are
  formalized.
