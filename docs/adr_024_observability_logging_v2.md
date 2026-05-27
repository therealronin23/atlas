# ADR-024 — Observability and Logging v2

**Status:** SEALED (MVP v1, 2026-05-25).
**Context:** Atlas already has MerkleLogger. `grok.md` proposes a richer stack:
MerkleLogger + MicroLedger + TelemetryBus + Operational WAL, with inspiration
from KERI/ACDC.

## Decision To Make

Whether Atlas should add a second-generation observability stack around the
existing MerkleLogger without weakening the forensic chain.

## Proposed Shape

| Layer | Purpose | Persistence | Risk |
|---|---|---|---|
| MerkleLogger | forensic append-only record of important actions | durable | already core |
| MicroLedger | compact rolling summaries and receipts | durable/compact | new complexity |
| TelemetryBus | in-process metrics/events for dashboard/alerts | ephemeral or sampled | event volume |
| Operational WAL | high-volume operational trace for debugging | rotating files | retention/privacy |

## Principles

- MerkleLogger remains the authoritative forensic log.
- Telemetry must not include raw secrets or unredacted PII.
- MicroLedger entries should be derived from Merkle/audit events, not compete
  with them.
- Any key rotation or witness mechanism inspired by KERI must be optional and
  documented before implementation.
- Dashboard/export endpoints stay localhost or Tailscale-only.

## Candidate Deliverables

1. `src/atlas/logging/telemetry_bus.py`
2. `src/atlas/logging/microledger.py`
3. `src/atlas/logging/operational_wal.py`
4. `src/atlas/monitoring/prometheus_exporter.py`
5. Dashboard pages for provider, task and thermal metrics.

## Open Questions

- What events must always be Merkle-level vs telemetry-only?
- What retention policy is acceptable for operational traces?
- Should Hermes-VPS act as an optional witness for audit receipts?
- Should signing/key rotation be part of this ADR or a later ADR?

