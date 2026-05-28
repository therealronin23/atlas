# ADR-029 — Audit full-text search + reverse twin audit

- **Status:** Accepted (2026-05-29)
- **Depends on:** ADR-024 (Merkle logging v2), ADR-027 (`/api/exec` inbound), ADR-028 (twin kanban)
- **Absorbs from Hermes-Agent:** `hermes sessions` full-text search; closes the
  "Hermes runs unaudited" gap by exposing Atlas's ledger to Hermes.

## Context

Two twin-absorption items remained after ADR-028:

1. **Atlas lacked full-text search over its own history.** `atlas insights`
   aggregates the Merkle ledger but cannot answer "what did Atlas do about
   *X*?". Hermes ships FTS5-backed search behind `hermes sessions`.
2. **Hermes runs unaudited.** Atlas keeps an append-only, hash-chained Merkle
   ledger; Hermes-Agent has no equivalent. The twin had one auditable
   hemisphere and one opaque one.

## Decision

### A. `atlas search` — FTS5 over the Merkle ledger

- **Module:** `src/atlas/core/audit_search.py` — `search_records(records, query, limit)`.
- **Engine:** the SQLite **FTS5** extension via stdlib `sqlite3`. No new
  dependency (coding rule 6). An ephemeral in-memory index is built per query
  from the records Atlas already writes, so there is no second source of truth.
- **Query model:** free text; whitespace-separated terms are an implicit AND.
  User input is wrapped as quoted FTS5 phrases so stray operators (`"`, `*`)
  cannot break the `MATCH` expression. Results are ranked by `bm25`.
- **Degradation:** when the local SQLite build lacks FTS5 (the VPS and the
  laptop ship different builds), it falls back to a substring AND match —
  same result shape, newest-first, no relevance score.
- **CLI:** `atlas search <terms...> [--limit N] [--json]`.

### B. `/api/exec/audit` — reverse twin audit

- **Endpoint:** `POST /api/exec/audit` in `src/atlas/interfaces/exec_api.py`,
  same HMAC + timestamp auth as the rest of `/api/exec/*`.
- **Behaviour:** records a Hermes-origin action into Atlas's Merkle ledger and
  returns the chained receipt (`id`, `hash_self`, `hash_prev`).
- **Provenance (non-negotiable):** the agent is forced to `hermes_vps` and the
  action is namespaced under `hermes.` server-side, so a Hermes-origin record
  can never be confused with an Atlas-native one.
- **Boundary validation:** `action` required; `result` ∈ {success, failure,
  blocked, pending, refused}; `risk_level` ∈ {safe, moderate, high, critical};
  `payload` must be a JSON object. Anything else is a 400.
- **Hermes-side artifact:** `scripts/hermes_skill_atlas_audit/` ships a
  stdlib-only client (`atlas_audit.py`) and a `SKILL.md` for deployment to
  `~/.hermes/skills/atlas-audit/` on the VPS. Audit is best-effort: if Atlas is
  offline the client exits non-zero and Hermes must not block a reply on it.

## Direction of authority (ADR-000)

Atlas stays the system of record. The reverse channel does not let Hermes
mutate Atlas state — it only *appends a receipt* of something Hermes already
did. Atlas decides; Hermes reports.

## Non-Goals

- No retroactive import of Hermes's pre-existing history.
- No second ledger; the Hermes receipts live in Atlas's one chain.
- No new dependency for search; if FTS5 is unavailable, substring match stands.
