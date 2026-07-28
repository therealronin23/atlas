# Deferred Items

This file records deliberate non-imports and later work. A deferred item is
not implemented, wired, configured, live or product-accepted.

## Operator and dependency boundaries

- `ADC-WO-102`: durable Mission/Task owner and orchestration boundary.
- `ADC-WO-103`: memory/knowledge ownership and private-to-shared promotion.
- `ADC-WO-107`: port-7341 mutation boundary.
- `ADC-WO-100`: authenticated Hermes pairing and rollback smoke.
- `ADC-WO-105`: Membrane/Osmosis enforcement profile.
- `ADC-WO-104`: Native Wave 5, still conditional behind measured Hosted limits
  and explicit authorization.
- `ADC-WO-108`: Engineering Finding/review/diagnostic plane after candidate
  acceptance; `ADC-WO-109` through `ADC-WO-111` follow its contracts.
- `ADC-WO-106`: autonomous adoption of remote executable MCP packages remains
  rejected, not deferred for automatic activation.

## Runtime-dependent verification

- Hermes, external providers, authenticated MCP servers, Telegram and other
  credentialed integrations are not `LIVE_VERIFIED` until an authorized fresh
  smoke and rollback receipt exists.
- Playwright is absent in this environment. The browser capability and
  `computer_use` tests degrade/skip cleanly, but no browser liveness claim is
  valid.
- The shared Kuzu graph is at `c95038c` and stale against the candidate. It
  must be rebuilt after integration, never by overwriting the shared runtime
  from this worktree.
- F2.6 has never been recorded as run.

## Product and quality follow-up

- Atlas Workbench convergence remains comprehensive by decision, but begins
  only after the Engineering Finding contracts and the dedicated Cut 2 scope
  are approved; no blind CodeOSS/VSCodium/Void/Zed tree merge is authorized.
- The Atlas shell remains a harness and has a 674.82 kB production JavaScript
  chunk. Code splitting is a later Product OS performance work order.
- FastEmbed 0.8.0 changes the selected model's pooling behavior. Atlas embeds
  package version and artifact digest in persistent identity, but a local
  retrieval-quality and migration benchmark must precede any dependency pin or
  custom pooling registration.

## Historical/documentary debt

- The immutable R2.1 ZIP is intentionally excluded from Git after checksum
  verification.
- Daily research is `RESEARCH`, not adoption evidence; deduplication, source
  verification, licensing, dependency decision and trial remain separate.
- 165 current documents have no markdown-link edges. They are classified in
  the 912-entry index; this is navigation debt, not missing authority.
- One expired graveyard item and historical broken links remain visible rather
  than being rewritten out of history.
