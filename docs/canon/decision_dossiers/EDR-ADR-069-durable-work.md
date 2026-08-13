# EDR-ADR-069 — Durable Mission, Task and effect recovery

**Decision:** ADR-069
**Program:** P06 — Self-Build and Foundry
**Evidence state:** `PROVISIONAL`
**Decision disposition authority:** `docs/canon/decision_registry.jsonl`

## Question

What durable boundary should own Mission, Task, command, approval and receipt
history without imposing event sourcing on every Atlas subsystem?

## Constraints

- Golden Route preserves human approval before effects.
- High sensitivity still requires a human or denial.
- External effects are auditable and third-party execution fails closed.
- The local runtime must not claim exactly-once execution for arbitrary remote
  APIs.

## Observed evidence

- `EVD-LOCAL-ADR-069` makes Mission v0 a semantic projection, not yet the
  universal durable owner of work state.
- `EVD-LOCAL-TASK-CONTRACTS` defines task states and transitions.
- `EVD-LOCAL-TASK-PERSISTENCE` persists pending approval material but does not
  provide a universal task/command journal.
- `EVD-EXT-EVENT-SOURCING` recommends selective use with explicit projection,
  privacy and schema-evolution management.
- `EVD-EXT-AWS-WORKFLOWS` demonstrates durable workflow history while leaving
  external-effect idempotency to the activity boundary.

## Alternatives compared

1. Keep separate owners for Mission, TaskPersistence, approval and update
   state. This avoids migration but leaves recovery and ownership ambiguous.
2. Introduce a selective durable history for Mission, Task, commands,
   approvals and receipts, with reconstructible projections and explicit
   idempotency/reconciliation for external effects. This adds migration work
   but keeps event sourcing inside the work boundary.

## Recommendation

Adopt selective durable history, initially over the local transactional store,
with projections for existing callers. Use an append-only journal only for
work-state transitions and receipts; do not event-source memory, configuration
or every internal object. External calls are at-least-once and must use an
idempotency key, status query or reconciliation protocol.

No runtime persistence migration is complete yet.

**Operator decision recorded 2026-07-31**: accept this recommendation
(SELECTIVE_DURABLE_HISTORY). `docs/canon/implementation_registry.yaml`
ADC-WO-102 moved `REQUIRES_OPERATOR` → `READY` (decision made; the unified
Mission/Task/Orchestrator/Policy/Evidence interface set described in its
`target_state` is not yet built). `docs/canon/open_questions.jsonl`
`OPEN-OPERATOR-MISSION-TASK` marked `RESOLVED`.

## Root-document GoldenRoute boundary (2026-08-13)

GoldenRoute and ColdUpdate now admit a deliberately narrow root-document
case: an existing, single-component `*.md` path may be modified through the
same request → validate → approve → apply transaction used for `docs/`.
Creation, deletion, cross-path patches, symlinks and non-regular files remain
fail-closed. `agents.md` is additionally immutable because it is the exact
five-line pointer to `AGENTS.md`; `config/governance.json` remains outside the
allowed surface. Acceptance coverage exercises a real root `README.md`
modification and proves that the pointer is unchanged. This widens document
addressability, not durable-work authority: approval, validation, audit and
commit semantics are unchanged, and no root-document request was autoapplied.

## Confidence and limits

**Confidence:** medium. A TaskPersistence snapshot survives a process
boundary, but the selective Mission/Task/command/effect history proposed by
this dossier does not exist yet. The narrower result cannot raise confidence
in the unimplemented journal's recovery behavior.

**Falsifier status — NOT RUN as written (correction 2026-08-12).** The matrix
falsifier asks whether a **selective journal** can reconstruct an approved task
without hidden mutable state. `tests/test_task_persistence_recovery.py` never
creates that journal: it exercises the existing file-backed `TaskPersistence`
snapshot in two Python processes. Its 3 tests are valuable supporting evidence,
not execution of the dossier's falsifier. They prove this narrower contract:

1. A subprocess constructs a `Task`, persists it `AWAITING_APPROVAL`,
   transitions it to `EXECUTING` (simulating human approval), persists
   again, and exits — the process is gone, nothing survives in memory.
2. A second, genuinely separate subprocess (new Python interpreter, zero
   shared state) opens a fresh `TaskPersistence` over the same directory
   and loads the task by id.
3. The test asserts field-by-field equality against what the first
   process wrote — id, intent, status (`executing`, proving the SECOND
   write survived, not a stale first snapshot), priority, sensitivity,
   metadata, and result.

The 3 tests ran green again on 2026-08-12. The 2026-07-31 dossier reported a
separate manual PID check, but that manual command was not repeated in the
current audit. A companion test confirms the Merkle receipt for
`approval.persisted` exists independently in its own chain (two receipts for
two real writes, not one reused), and a third confirms `load()` of an unknown
id returns `None` rather than fabricating a result.

**What this does NOT yet answer:** reconstruction of Mission→Task→command→
approval→effect from one durable history, reconciliation of an ambiguous
external effect, throughput under concurrent writers, behavior across a
SQLite/runtime version upgrade, or recovery of a Mission. A valid falsifier
run first requires a minimal journal implementation and a crash/restart test
that rebuilds those projections without consulting legacy mutable owners.

**Revisit triggers:** local recovery benchmark results (satisfied for the
Task-recovery case 2026-07-31), SQLite runtime/version changes, or a
constitutional change to Mission-to-Task authority.

## Security and rollback

The journal chains commands, approvals and receipts to existing audit evidence.
Migration is additive: legacy projections remain readable until verified
reconstruction passes. Rollback disables new writers and rebuilds projections
from the prior compatible state; it does not erase audit history.

## Evidence IDs

`EVD-LOCAL-ADR-069`, `EVD-LOCAL-TASK-CONTRACTS`,
`EVD-LOCAL-TASK-PERSISTENCE`, `EVD-EXT-EVENT-SOURCING`,
`EVD-EXT-AWS-WORKFLOWS`.
