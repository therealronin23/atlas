# Product Strategy Notes

**Source material:** distilled from `Gemini-Temporary Chat.md`.
**Status:** non-legal, non-commercial planning note.

This file captures product/market ideas without turning them into technical
commitments. It is not legal advice.

## Positioning

Atlas is strongest when positioned as a local sovereign AI gateway:

- local-first execution;
- privacy and redaction before external inference;
- auditable action chain;
- explicit permissions;
- optional Hermes/VPS continuity;
- useful for domains where trust, logs and privacy matter.

Potential early domains from the chat:

- small legal offices;
- accounting/gestoría workflows;
- clinics or private medical offices;
- technical consultancies;
- internal automation for small businesses.

## IP Strategy Caveats

The chat discussed copyright, patents, trade secrets and open-core licensing.
Treat those as prompts for professional advice, not conclusions.

Practical near-term stance:

1. Keep secrets and `.env` out of git.
2. Do not publish raw research dumps containing personal metadata.
3. Keep Gate/ADR discipline strong; process quality is part of the asset.
4. Do not spend money on patents before the product works outside the
   developer machine.
5. If commercialization becomes real, consult a qualified IP lawyer in the
   target jurisdiction.

## Product Readiness Reality

Atlas is not yet a consumer product. It is a powerful technical prototype.

Before selling or deploying for others:

- installation must be reproducible;
- dashboard and approvals must be understandable to non-developers;
- backups and restore must be documented;
- audit export must be explainable;
- failure modes must be boring and recoverable;
- support burden must be realistic.

## Useful Differentiator

Do not compete with generic chatbots on convenience. Compete on:

- sovereign local policy;
- evidence trail;
- safe tool execution;
- privacy-preserving delegation;
- human approval for real-world effects.

