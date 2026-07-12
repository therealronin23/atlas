# Prompt for Fable — Phase 15

You are continuing Atlas Core. You must treat this ZIP as the product and architecture source of truth for the next phase.

## Goal

Transform the current Atlas repository from a technically useful validation harness into the foundation of Atlas as an objective-driven cognitive OS.

## Immediate rules

1. Do not replace the existing EventBus or create a second canonical event stream.
2. Do not polish the existing React web shell as final UX. Rename/document it as validation harness if not already done.
3. Do not create another static graph screen.
4. Do not implement dangerous external actions: no real filing, no certificate use, no outbound send, no deletion, no silent remote control.
5. Do not clone n8n, Jarvis, Odoo, Salesforce, Retool, Airtable, Raycast or any external product.
6. Study, assimilate, wrap, nativize, fork — in that order.
7. Fork nothing without explicit license review and ADR.
8. Every new action must declare capabilities, risk, data class, gate requirements and audit events.

## Phase 15 execution target

Build the documentation, schemas, fixtures and first code scaffolds for:

- Product constitution.
- True Liquid Software.
- Sector Registry and Objective Registry.
- Gestoría vertical slice.
- External Thought Import.
- Presence Engine / Cognitive Physics.
- Integration Fabric.
- Easy Connection Layer.
- Atlas Native Business Core.
- Adaptive Question Engine.
- Connection Store and Connector Recipes.
- CRM/ERP native abstractions.
- Security boundaries and policy engine contracts.

## Deliverables

At the end of the phase, write:

- `CONTINUATION_STATE.md`
- `NEXT_AI_INSTRUCTIONS.md`
- `OPEN_QUESTIONS.md`
- `KNOWN_RISKS.md`
- `IMPROVEMENT_PROPOSALS.md`
- `TESTING_STATUS.md`

Use the templates in `/continuation`.

## Continuous improvement mandate

Before closing the phase, identify at least 10 possible weaknesses in what you built. Classify them as product, UX, backend, security, integration, data, legal, testing or maintainability. Fix what is safe to fix. For unresolved items, create explicit next steps.
