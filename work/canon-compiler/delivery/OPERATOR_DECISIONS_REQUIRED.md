# Operator Decisions Required

These decisions are intentionally not inferred from existing code.

## Candidate acceptance

1. Accept, reject or request amendments to **ATLAS DEFINITIVE CANDIDATE**.
   Acceptance is the only action that may elevate it to `ATLAS CANON ACCEPTED`
   and unblock Cut 1.

## Constitutional boundaries

2. `ADC-WO-102`: choose the durable Mission/Task owner, state machine,
   idempotency, approval persistence and Orchestrator boundary.
3. `ADC-WO-103`: choose Memory/Knowledge owners and promotion paths, including
   private-to-shared distillation, temporal claims and deletion propagation.
4. `ADC-WO-107`: authorize a governed mutating port-7341 API or restore the
   accepted read-only boundary.

## External and distributed authority

5. `ADC-WO-100`: provide authority/credentials for a fresh Hermes pairing and
   rollback smoke. Historical deployment is insufficient.
6. `ADC-WO-105`: choose Osmosis as optional limited gateway or non-bypass
   enforcement with its availability, threat and rollback guarantees.
7. `ADC-WO-104`: open Native Wave 5 only after a measured Hosted limitation,
   accepted threat model, resource budget, porting evidence and rollback plan.

## Product decisions after acceptance

ADR-078 already decides the first product and desktop host; do not reopen those
by accident.

8. Approve the exact comprehensive Cut 2 scope and maintenance/licensing
   boundaries after `ADC-WO-108` stabilizes the internal engineering plane.
9. Approve the dedicated Android architecture after Surface API and Workbench
   contracts are stable.

High-sensitivity human control and remote executable MCP auto-adoption are not
open defaults. Weakening the former requires a new constitutional decision;
the latter remains rejected.
