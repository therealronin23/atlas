# Implementation Report

## Closed work orders

Fifteen work orders are complete in the current delivery, including the prior
convergence baseline:

- `ADC-WO-000` through `ADC-WO-006`: preservation, live-source disposition,
  canonical authority, candidate documents, CI integrity, reality reconciliation
  and independent delivery preparation;
- `ADC-WO-007` through `ADC-WO-010`: high-sensitivity enforcement, fail-closed
  MCP vetting/re-vetting, UI advisory remediation and lineage reconciliation;
- `ADC-WO-101`: Workbench host/first-product decision;
- `ADC-WO-112`: optional SDK adapter type safety;
- `ADC-WO-113`: operator-decision work-order eligibility;
- `ADC-WO-114`: current delivery evidence, archive and review artifacts.

Eleven work orders remain explicitly deferred: five require an operator,
five are dependency-blocked, and remote executable MCP auto-adoption remains
rejected by design.

## Implementation changes after the former delivery anchor

### Evidence-qualified governance

The decision registry remains the disposition authority. Additive evidence
source and decision-evidence registries, schemas and dossiers make sources,
alternatives, falsifiers and revisit triggers reviewable. The canon gate now
rejects unsafe local evidence paths, unresolvable cross-links, duplicate
corroboration, state drift and unsupported `EVIDENCE_QUALIFIED` claims.

### Operator-owned execution boundaries

The canon gate now makes it impossible for the registry to present an
operator-required item as `READY`. Every `REQUIRES_OPERATOR` work order must
declare that fact, and an operator question's blocker must exist and be
compatible. This closes a documentation-state bypass without deciding
Mission/Task ownership, memory promotion, the mutating API bridge, Native Wave
5, Hermes credentials or Osmosis enforcement.

### Optional-adapter safety and type gate

The image/video adapters reject malformed `fal_client` values at the boundary
instead of assuming an `Any` mapping. Their existing error path turns that into
an auditable failed generation. ACP's optional SDK class is now dynamically
bound only after its lazy import, eliminating the unchecked `Any` base class.
Regression tests cover both behaviors and strict mypy is clean over 318 source
files.

### Validation honesty

Protocol-specific tests now skip only when their optional ACP/MCP extras are
absent locally; CI installs both extras and retains those checks. The additive
schema test no longer assumes a fixed global schema count, so new canonical
schemas do not create a false regression.

## Existing security and lineage controls retained

- High sensitivity is normalized after every supported or injected Decider.
- Sentinel errors, corrupt snapshots and drift deny, record evidence and
  quarantine affected MCP servers; argv inspection is separated from admission.
- The UI remains a validation harness, not the final product surface.
- No whole-tree editor merge occurred: CodeOSS/VSCodium, Void and Zed keep
  their governed host/donor roles until their dependent contracts exist.

## Rollback

Each functional change is an atomic local commit. Revert in reverse concern
order: delivery artifacts, eligibility gate, adapter type safety, optional-test
classification, evidence governance, then prior convergence commits. The
original checkout and pre-convergence bundle remain an independent rollback
root. No external service or `config/governance.json` change is part of this
delivery.
