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

## Confidence and limits

**Confidence:** medium. The split ownership is concrete local evidence and the
durable-workflow pattern is strong, but Atlas must still measure recovery,
throughput and upgrade behavior locally.

**Falsifier:** recovery tests show that a selective journal cannot reconstruct
an approved task without hidden mutable state, or a smaller compatible boundary
meets the same recovery contract with less complexity.

**Revisit triggers:** local recovery benchmark results, SQLite runtime/version
changes, or a constitutional change to Mission-to-Task authority.

## Security and rollback

The journal chains commands, approvals and receipts to existing audit evidence.
Migration is additive: legacy projections remain readable until verified
reconstruction passes. Rollback disables new writers and rebuilds projections
from the prior compatible state; it does not erase audit history.

## Evidence IDs

`EVD-LOCAL-ADR-069`, `EVD-LOCAL-TASK-CONTRACTS`,
`EVD-LOCAL-TASK-PERSISTENCE`, `EVD-EXT-EVENT-SOURCING`,
`EVD-EXT-AWS-WORKFLOWS`.
