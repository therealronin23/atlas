# Deferred Items

This file records deliberate non-imports and later work. A deferred item is not
implemented, wired, configured, live, or product-accepted.

## Live checkout sources

- `docs/design/mcp_catalog_stage1_triage.jsonl` was not imported. Its 2,106
  semantic records matched the tracked baseline and only generated timestamps
  changed. The exact live file remains in the preserved checkout and backup.
- A concurrent stage-2 refresh changed only `ai.filepad/filepad` from HTTP 500
  to HTTP 503 while remaining incomplete; it is transient runtime evidence,
  not a canonical source change.
- The live classified catalog grew from six to 32 research candidates after
  isolation. The 26 new rows retain misleading `installed`/`connected` modes
  without admission. Their research source is preserved, but they were not
  promoted into the operational catalog; the six imported rows are explicitly
  `NOT_INSTALLED` and gated.
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
- Cut 1 (`EngineeringFinding`, review and diagnostics), Cut 2
  (CodeOSS/VSCodium/Void plus Zed assimilation), and Android remain separate
  work orders with dependency and operator gates.

## Structural and documentary debt

- The shared Kuzu graph is fresh for baseline `c95038c` and stale for the
  candidate. Rebuild it after integration rather than replacing the original
  runtime graph from an isolated worktree.
- The sanitation radar reports 159 current markdown documents with no
  markdown-link edges. All 906 documents are nevertheless classified in
  `docs/INDEX.yaml`; this is navigation debt, not missing authority.
- Eleven broken links and one expired graveyard item are confined to historical
  archive material. They remain visible rather than rewriting history.
- The Atlas shell production chunk is approximately 675 kB; code splitting is
  a non-blocking Product OS performance item.
