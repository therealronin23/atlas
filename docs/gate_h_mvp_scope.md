# Gate H — MVP Scope (Opción B)

**Status:** active — defines minimum closure for tag `v0.7-gate-h`.

## PoC class

Canonical generated-tool path: **`editor run`** (or `editor run_task`) executing a command
under `projects/.atlas/generated/` with Gate H audit loop.

## Per-pillar MVP

| Pilar | MVP criterion | Evidence |
|-------|---------------|----------|
| H1 Result Auditor | Validate exit_code + stdout shape; shadow compare; promote to ApprovedPatternStore on pass | `test_result_auditor.py`, Merkle `generated_tool.promoted` |
| H2 Reasoning Receipt | Structured receipt on Gate F success + generated run | `atlas gate-h receipts`, action `generated_tool.receipt` |
| H3 Rebuildable Memory | Rebuild patterns + truth snapshots from Merkle; optional Kuzu repopulate | `atlas gate-h rebuild-memory`, `test_gate_h_rebuild.py` |
| H4 Fail-Safe | Pause persists to disk; diagnostic mode; pause@3 | `gate_h/state.json`, CLI diagnostic |
| H5 Meta-Governance | `generated_code_policy` blocks eval/governance/escape | `test_generated_code_policy.py` |
| H6 Environment Sensor | Fingerprint on promote; stale blocks reuse | `test_environment_sensor.py` |

## Post-H (not required for seal)

- ADR-025 ColdUpdateManager full protocol
- ADR-024 MicroLedger / TelemetryBus / WAL
- FU-6 PII SLM wiring
- ADR-019 statistical validation
- Fleet / Atlas Box / production VLM
