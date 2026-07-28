# Deferred Items

This file records deliberate non-imports and later work. A deferred item is not
implemented, wired, configured, live, or product-accepted.

## Live checkout sources

- `docs/design/mcp_catalog_stage1_triage.jsonl` was not imported. Its 2,106
  semantic records matched the tracked baseline and only generated timestamps
  changed. The exact live file remains in the preserved checkout and backup.
- `atlas-canon-compiler-codex-handoff-r2.1-2026-07-27.zip` remains an immutable
  external corpus identified by SHA-256. It is intentionally excluded from Git.
- Daily research sources are preserved as `RESEARCH`. Deduplication, source
  verification, synthesis, dependency decisions, and adoption remain separate
  governed work.

## Runtime-dependent verification

- Hermes pairing, external providers, authenticated MCP servers, Telegram, and
  other credentialed integrations remain not `LIVE_VERIFIED` until a fresh
  operator-authorized smoke succeeds.

## Product convergence

- Atlas Workbench implementation follows candidate closure. Its later
  convergence is intended to be comprehensive, but its exact scope and internal
  sequence remain for the dedicated operator design discussion.
