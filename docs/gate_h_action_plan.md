# Gate H — Action Plan

## Status

- `Gate G` is complete: the project is operationally ready and the main repo is stabilized.
- `Gate H` is the next major milestone. It is focused on resilience, audited software synthesis, and safe self-improvement.

## Objective

Gate H must prove that Atlas can generate or adapt host-side tools and code safely, with auditability, validation, rollback, and explicit governance.

## High-level pillars

1. H1: Result Auditor
2. H2: Reasoning Receipt
3. H3: Rebuildable Memory
4. H4: Adaptive Fail-Safe
5. H5: Meta-Governance
6. H6: Environment Sensor

## Immediate Gate H deliverables

- [ ] Define Gate H acceptance criteria and closure evidence in a `docs/gate_h_seal.md` file.
- [ ] Create an initial `Gate H` implementation roadmap with measurable milestones.
- [ ] Implement the first audit/validation loop for generated tools.
- [ ] Add structured reasoning receipt metadata to generated tool execution.
- [ ] Build a reproducible memory rebuild command from Merkle logs.
- [ ] Add failure-detection and pause logic for repeated generated-tool failures.
- [ ] Harden generated-code governance invariants and enforcement.
- [ ] Track generated artifact environment fingerprints and stale-tool signals.

## Gate H task breakdown

### H1: Result Auditor

Goal: generated tools must be judged by output validity, not only by exit code.

Tasks:
- [ ] Define a `TruthSnapshot` data model for generated tool inputs/outputs/invariants.
- [ ] Add support in `ErrorRegistry` and `ApprovedPatternStore` to store validation history.
- [ ] Implement a shadow-run harness that re-runs old and new generated tool versions against the same snapshot.
- [ ] Promote generated artifacts only when validation passes.
- [ ] Add tests for tool revalidation, regression detection, and promotion logic.

### H2: Reasoning Receipt

Goal: record structured decision receipts for generated tools.

Tasks:
- [ ] Extend `MerkleLogger` payload schema to include reasoning receipt fields.
- [ ] Define receipts with:
  - why the tool was needed
  - data touched
  - permissions required
  - safety checks applied
  - approval path taken
- [ ] Ensure receipts are compact and structured, not raw chain-of-thought.
- [ ] Add tooling to export receipts for audit.

### H3: Rebuildable Memory

Goal: KuzuDB is an index, not the single source of truth.

Tasks:
- [ ] Add a `tools/rebuild_memory.py` or CLI command that reconstructs derived memory from Merkle logs.
- [ ] Ensure `KuzuVectorStore` can be rebuilt from approved evidence and `MemoryDistiller` inputs.
- [ ] Log rebuild operations and results in Merkle.
- [ ] Add tests for deterministically rebuilding memory indexes.

### H4: Adaptive Fail-Safe

Goal: degrade synthesis when generated tools fail repeatedly.

Tasks:
- [ ] Add failure counters and health states for generated tools.
- [ ] Pause synthesis after repeated equivalent failures.
- [ ] Add a diagnostic mode that only allows known-good tools.
- [ ] Require human review for retrying risky generated actions.
- [ ] Use TimeTravel checkpoints for rollback candidate selection.

### H5: Meta-Governance

Goal: generated code cannot bypass core safety controls.

Tasks:
- [ ] Enforce that generated code cannot disable `MerkleLogger`.
- [ ] Prevent generated code from bypassing `CapabilityIssuer` / `AtlasExecutor` controls.
- [ ] Disallow generated code from modifying `governance.json`.
- [ ] Ensure generated tools cannot exfiltrate unredacted PII.
- [ ] Add tests for governance invariants and AST Guard enforcement.

### H6: Environment Sensor

Goal: generated tools must be aware of environmental drift.

Tasks:
- [ ] Add dependency fingerprint tracking for generated artifacts.
- [ ] Monitor environment changes, CVEs, and provider behavior shifts.
- [ ] Mark generated patterns stale after material environment changes.
- [ ] Revalidate stale artifacts before reuse.
- [ ] Add tests for stale-tool detection and revalidation gating.

## Known pending follow-ups outside Gate H

These are non-blocking but should be addressed in parallel or before Gate H closure:

- [ ] ADR-012: memory sync between Hermes and Atlas Core.
- [ ] ADR-019: statistical validation framework.
- [ ] FU-6: PIISurrogate v2 with SLM detection for names / cities / addresses.

## Recommended first engineering sprint

1. Create `docs/gate_h_seal.md` and define what counts as done.
2. Implement H2 receipts + Merkle schema changes.
3. Implement H1 result auditing for one generated-tool class.
4. Add diagnostic pause/fail-safe logic for repeated failures.
5. Add test coverage for all new governance and audit behaviors.

## Notes

- Gate H is explicitly future work in `docs/gate_h_resilience_plan.md`.
- The project is currently `Gate G` complete; Gate H is the first major new milestone beyond operational readiness.
- This action plan is intended to capture everything that remains for Gate H, from planning to execution.
