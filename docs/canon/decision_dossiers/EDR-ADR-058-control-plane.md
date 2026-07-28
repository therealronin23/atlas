# EDR-ADR-058 — Query projection and governed command plane

**Decision:** ADR-058
**Program:** P01 — Institutional Kernel
**Evidence state:** `PROVISIONAL`
**Decision disposition authority:** `docs/canon/decision_registry.jsonl`

## Question

How can Atlas restore the accepted read-only bridge while providing a command
path for the future Workbench without creating a second ungoverned authority?

## Constraints

- Port 7341 is accepted as an Atlas OS event-kernel/read projection.
- UI and protocol clients do not own Task, Policy or Memory truth.
- External effects remain auditable and Golden Route approval precedes effects.
- A new public surface, dependency or remote transport needs its own decision.

## Observed evidence

- `EVD-LOCAL-ADR-058` defines the read-only bridge boundary.
- `EVD-LOCAL-API-7341` shows current mutating routes, including an approval
  route, which contradict that boundary.
- `EVD-EXT-CQRS` documents separate write authority and materialized read
  models.
- `EVD-EXT-K8S-CONTROLLERS` and `EVD-EXT-K8S-API` demonstrate admitted desired
  state, observed status, concurrency checks and dry-run as distinct concerns.

## Alternatives compared

1. Retain mutable 7341 routes as the primary command surface. This minimizes
   immediate migration but preserves an explicit ADR contradiction.
2. Keep 7341 as a query projection and create a logical command plane with
   authenticated admission, idempotency, expected version, policy evaluation
   and durable receipts. Local IPC is the initial desktop transport; it is not
   a claim that another public TCP listener is necessary.

## Recommendation

Adopt the second alternative. A command is durably admitted before a controller
executes its effect; the controller publishes observed status and a receipt.
Every command carries authenticated identity, `idempotency_key`,
`expected_version`, sensitivity and rationale. Dry-run is supported where the
command has a meaningful no-effect evaluation.

No mutating route has been migrated by this dossier.

## Confidence and limits

**Confidence:** high for the boundary separation; medium for the initial IPC
transport until an Atlas Workbench client proves the contract end to end.

**Falsifier:** local IPC cannot preserve authenticated identity, idempotency and
approval receipts across a desktop-host restart.

**Revisit triggers:** introduction of a paired remote node transport, or a
supported client that cannot migrate through a safe read-only adapter.

## Security and rollback

The migration is fail-closed: unsupported mutating requests are rejected, not
silently tunneled through 7341. Rollback retains the read projection and
re-enables only a previously versioned command adapter after validating its
policy and receipt path; it never bypasses high-sensitivity approval.

## Evidence IDs

`EVD-LOCAL-ADR-058`, `EVD-LOCAL-API-7341`, `EVD-EXT-CQRS`,
`EVD-EXT-K8S-CONTROLLERS`, `EVD-EXT-K8S-API`.
