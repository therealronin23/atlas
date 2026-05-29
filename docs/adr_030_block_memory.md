# ADR-030 — Block memory (Letta/MemGPT core memory)

- **Status:** Accepted (2026-05-29)
- **Depends on:** ADR-024 (Merkle logging v2)
- **Absorbs from Letta/MemGPT:** *core memory* — a small set of labelled,
  character-bounded text blocks that are always in context and that the agent
  edits in place. This was the last genuinely-open fork item from the
  absorption master plan.

## Context

Atlas already has **archival** memory: `KuzuVectorStore` plus
relevance/recency ranking — a searchable long tail queried on demand. What it
lacked is the complement Letta/MemGPT call *core memory*: a tiny, always-resident
working set (`persona`, `human`, `project`, …) that lives in every prompt and
that the agent rewrites itself as facts change.

Without it, durable-but-small facts ("the human is Tomás", "current focus is
the twin") either bloat the system prompt as static text or get lost in the
archival long tail where they compete with everything else for retrieval.

## Decision

### Module — `src/atlas/memory/block_memory.py`

- `MemoryBlock` dataclass: `label`, `value`, `limit` (default 2000 chars),
  `description`, `updated_at`. Exposes `.chars` and `.is_full`.
- `BlockMemory(store_path, merkle=None)` manager. All blocks persist together
  in a single `blocks.json` because the whole set is small and always loaded
  together.
- Read: `get`, `labels`, `all`, and `render()` — the last produces a
  deterministic `<label>\nvalue\n</label>` section per block, ordered by label,
  for prompt injection.
- Mutations: `create`, `set`, `append`, `replace`, `delete`.

### Character limit is a pressure mechanism, not a truncator

An edit that would push a block past its `limit` raises `BlockLimitExceeded`
rather than silently truncating. This is the MemGPT pressure signal: the caller
(the agent) must summarise or evict, never lose data through a lossy write.

### Coding-rule alignment

- **stdlib only** (rule 6): `json` + `dataclasses`, no new dependency.
- **Every mutation audited** (rule 1): `create`/`set`/`append`/`replace`/`delete`
  log `memory.block.created` / `memory.block.edited` / `memory.block.deleted`
  to the Merkle ledger (added to `AUDIT_ACTIONS`). Audit is optional — passing
  `merkle=None` is safe for tests/standalone use.

### CLI — `atlas blocks`

`list` / `show` / `create` / `set` / `append` / `delete`. Instantiates
`BlockMemory` directly from `workspace/memory/blocks`, wired to the same
`MerkleLogger` the rest of Atlas uses, mirroring `atlas audit --verify`.

## Scope / Non-Goals

- **Core memory only.** Archival memory and ranking are already covered by
  `KuzuVectorStore`; this ADR does not touch them.
- **No automatic prompt injection yet.** `render()` exists and is tested, but
  wiring it into the live system prompt is a deliberate follow-up rather than a
  half-built change in this ADR.
- No new dependency; no second persistence engine.
