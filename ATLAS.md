# Atlas

> DOC-0 RC2 candidate for commit `d01d4b931fd7f02af81a32c63c889d35f574fcab`. This entrypoint becomes
> authoritative only when ADR-072 is accepted and this change is merged.

## What Atlas is

Atlas is a sovereign cognitive operating-system product. Its current profile,
**Atlas Hosted**, is a local-first persistent runtime that runs on an existing
host operating system and turns user intent and context into governed,
reversible and auditable work.

Atlas Hosted is not a native kernel, a chatbot shell, a dashboard, an IDE
wrapper or a provider router. It may expose all of those kinds of surfaces or
adapters without becoming any one of them.

## Current direction

1. Finish Atlas Hosted before opening Atlas Native.
2. Use Linux as the initial reference host.
3. Converge the existing system through contracts and adapters; do not rewrite
   the repository wholesale.
4. Separate Guardian, Trunk µCore, System Services, Cognition, Providers and
   Surfaces.
5. Give every mutable state one authority.
6. Preserve current accepted decisions such as memory by use case, Gate Engine,
   Mission Layer, Golden Route and dedicated Linux/Android applications.

## How to know what is true

- **Intended direction:** `docs/canon/` after ADR-072 adoption.
- **Accepted decisions:** `docs/decisions/adr/`.
- **Current state:** `PYTHONPATH=src atlas reality --json`, tests and the fresh
  structural graph.
- **Current work:** `WORK_LEDGER.md`.
- **Historical context:** handoffs, packs, continuation snapshots and archive.

Live evidence may prove that an implementation claim is false or stale. It does
not silently redefine Atlas product identity or future architecture.

## Current program

DOC-0 is recovering authority and traceability before the major Hosted
convergence phases H00-H14. The source corpus is not yet fully absorbed line by
line; `docs/canon/ATLAS_COVERAGE.yaml` states that limitation explicitly.

## First commands

```bash
python scripts/canon_audit.py --strict
python scripts/canon_inventory.py --strict
PYTHONPATH=src atlas reality --json
```

Then query the structural graph for the component being changed and read only
the claims, ADRs and designs linked to that component.
