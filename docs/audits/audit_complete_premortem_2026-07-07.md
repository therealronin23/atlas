# Complete audit + premortem — Atlas core

Date: 2026-07-07.
Node: Context hygiene / ecosystem recovery.
Tipo: 2, foundational/correctness.
Skill used: `code-review-and-quality`.

## Scope

This audit covers the current working tree, runtime truth checks, verification
commands, context/authority hygiene, dependency state, browser/computer-use
readiness, MCP/Hermes live claims, and dead-or-unwired module risk. It does not
claim live provider quality because no live inference or Hermes smoke was run
with current secrets.

## Evidence

- `atlas reality --json`: repo `main`, dirty tree, Merkle OK,
  browser initially degraded, LLM providers configured but not smoke-proven.
- Follow-up repair installed Playwright Chromium/headless shell v1223; `atlas
  reality --json` then reports browser/computer-use ready.
- `atlas reality --run-checks --include-browser --json`: initially degraded by
  `pytest_browser` and `browser readiness`; after repair, strict failures clear
  in local reality and browser marked ready.
- Core tests: full `pytest` passed in this recovery slice.
- Browser/computer-use tests failed before repair and passed after repair.
- Mypy strict: `Success: no issues found in 216 source files`.
- Merkle audit: chain intact.
- `atlas doctor`: 5/6 checks passed; `hermes_twin` warning because kanban board
  is unreachable.
- `atlas health`: governance and Merkle OK; Hermes not reachable; recent WAL
  includes `mcp.server_failed` and self-maintenance events.
- `scripts/sanitation_audit.py`: initially 15 modules had zero non-test importers;
  follow-up repair now reports no unclassified vapor and lists those modules as
  classified zero-importers.
- Git state: dirty recovery slice with MCP trunk, documentation, tests, and
  dependency floor updates staged together.

## Findings

### Closed: browser/computer-use readiness

The strict reality check fails because Playwright's expected Chromium executable
is absent:

`/home/ronin/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome`

This is now reported honestly by `src/atlas/core/reality.py`, and unit coverage
exists in `tests/test_reality.py`. The expected Chromium/headless-shell revision
has been installed locally and `pytest -m computer_use` passes.

### Important: the working tree is too dirty for unrelated work

The current tree mixes multiple concerns:

- context recovery docs and hook cleanup;
- runtime browser readiness fix;
- `.claude/skills` de-tracking;
- staged dependency floor updates;
- untracked `knowledge-src/`;
- new memory/design/audit files.

Core correctness is green, but merge safety is not just test status. The current
state should be split or at least committed as one explicit context-recovery
change before new feature work continues.

### Closed: dependency floor decision

`pyproject.toml` records existing dependency floors, currently including
`pyyaml>=6.0.3`, `cryptography>=49.0.0`, and `litellm>=1.89.0`. These are
accepted as floor bumps, not new dependencies. Targeted memory/MCP tests,
browser tests, mypy, and the final verification pass provide compatibility
evidence. Caveat: `uv.lock` already resolves `cryptography` to 49.0.0, but
`uv lock --check` cannot currently validate the lock because the `redteam` extra
has an unrelated `garak`/`pyrit` resolver conflict for future Python splits.

### Closed: `knowledge-src/preferencias` classification

The untracked file contains a design note about memory classes:

- `factual`: information from `knowledge-src`;
- `personal`: user-derived interaction memory;
- proposed helpers for each.

That note is now classified as policy/design seed, not factual ingestion data.
The owner path is `MemoryTrunk`: `add_from_knowledge_src` writes factual memory
and `add_from_user_preference` writes personal memory. Tests verify the routing
and that supersession preserves `memory_class` and `expires_at`.

### Closed: zero-importer modules are classified

The sanitation audit initially reported zero non-test importers for:

- `src/atlas/tools/_crawl4ai_worker.py`
- `src/atlas/core/lesson_runner.py`
- `src/atlas/core/incremental_coder.py`
- `src/atlas/core/history_compactor.py`
- `src/atlas/core/token_budget.py`
- `src/atlas/immunity/live_loop.py`
- `src/atlas/core/self_maintenance/root_cause_classifier.py`
- `src/atlas/core/self_maintenance/benchmark_gate.py`
- `src/atlas/core/self_maintenance/topic_expander.py`
- `src/atlas/core/self_maintenance/preflight_gate.py`
- `src/atlas/core/self_maintenance/batch_premortem.py`
- `src/atlas/core/self_maintenance/sota_snapshot.py`
- `src/atlas/core/self_maintenance/panorama_scout.py`
- `src/atlas/core/self_maintenance/failure_lesson_sink.py`
- `src/atlas/core/self_maintenance/evolution_gate.py`

This was not proof that all were dead; it was proof that their runtime owner was
unclear. The radar now separates unclassified vapor from classified zero-importer
modules. Current result: no unclassified vapor; the 15 modules are classified as
KEEP/PARK with explicit reasons.

### Important: Hermes and MCP are configured, not proven live

Reality reports Hermes delegation as degraded/local takeover and MCP as
configured. Doctor/health do not prove Hermes live; health reports Hermes not
reachable and recent MCP failure events. The correct external claim is:
configured/degraded, not live.

### Positive control: core code health is currently good

Core tests, mypy, Merkle verification, governance validation, and docs test-count
freshness all pass. The browser readiness change is narrow and covered. The
context recovery also reduces SessionStart context injection and restores the
single-authority model.

## Premortem

If the project fails from this state, the most likely failure is not a single
runtime bug. It is operational drift:

1. New work starts while the tree is already dirty, mixing feature changes with
   context recovery and dependency policy.
2. Agents trust configured capabilities as live capabilities, especially browser,
   Hermes, MCP, or LLM providers.
3. The self-maintenance loop treats PARK/KEEP-injectable modules as always-on
   live systems instead of respecting their classification.
4. `knowledge-src` becomes a dumping ground rather than a verified ingestion
   boundary.
5. `.claude/skills` de-tracking is correct, but the staged deletion is so large
   that reviewers miss the smaller runtime and governance changes hidden beside
   it.
6. Core tests keep passing, which creates false confidence while browser,
   external services, and context discipline remain degraded.

The predicted failure mode is slow incoherence: more docs, more pending objects,
more apparent capabilities, and less confidence about what Atlas can actually do
today.

## Required closure order

1. Finish or split the current context-recovery change before any new feature
   work.
2. Keep the zero-importer classifications current; any new unclassified vapor
   must be wired, parked, or quarantined before feature stacking.
3. Run live smokes only when secrets/network are intentionally loaded, then
   update claims for Hermes, LLM, and MCP based on that evidence.

## Verdict

The original blockers are closed except for ordinary review/commit hygiene and
live external smokes. The core is healthy; browser/computer-use is ready locally;
dependency and `knowledge-src` classification are explicit; zero-importer
modules are classified rather than unowned.

---

## Section A — MCP Trunk Audit (2026-07-07 closure)

### Evidence (tronco + CLI)

- `.cursor/mcp.json` created: atlas-trunk stdio → `~/atlas-mcp` + repo root.
- Codex MCP client smoke: stdio handshake + `tools/list` + `trunk_kinds` OK
  when `PYTHONPATH` includes both repo `src` and venv `site-packages`.
- `trunk_recommend_stack` added and smoke-tested over stdio; shortlist policy is
  installed/verified first, candidates as discovery only.
- `trunk_health` added and smoke-tested; reports catalog counts, configured servers,
  read-only tools, missing env var names, and prioritized `research-2026` trial candidates.
- 2026 discovery candidates added to catalog: GitHub, Context7, Fetch, Figma,
  Supabase/Postgres, Notion, Sentry, Cloudflare, Stripe, Docker, Kubernetes,
  Tavily, Perplexity, Time.
- Research sources for this shortlist: official MCP Registry, MCP authorization
  spec 2025-11-25, `modelcontextprotocol/servers`, `github/github-mcp-server`,
  `upstash/context7`, Figma MCP developer docs, Supabase MCP.
- `scripts/atlas_install_trunk.py` re-run: `read_only_tools` now includes
  `trunk_list_roots`, `trunk_selfcheck`, `trunk_recommend_stack`.
- Skills on disk: `atlas-coding-discipline`, `deliberation_council`,
  `deliberation_council_portable` — all catalogued after fix.
- `sanitation_audit.py`: 0 unclassified vapor.
- `native_roots()` drift confirmed and fixed: `recall_multihop`, `shred` missing
  from manifest but present in `memory_server.py`.
- `mcp_six_primitives_audit.md` marked SUPERSEDED (primitives implemented in
  `trunk_capabilities.py`).

### Findings CLOSED

| ID | Finding | Fix |
|----|---------|-----|
| MCP-1 | Manifest drift (memory tools) | `trunk_manifest.py` + `test_trunk_manifest_parity.py` |
| MCP-2 | `deliberation_council_portable` uncatalogued | `mcp_catalog.yaml` ia-agentes sector |
| MCP-3 | Superpowers as `kind: skill` | Reclassified `kind: plugin` |
| MCP-4 | Dual skill path `.agents` vs `.claude` | `capability_router.py`, `mcp_trial.py` default |
| MCP-5 | Read-only gap for navigation primitives | `_TRUNK_READ_ONLY_TOOLS` extended |
| MCP-6 | Stale six-primitives audit | SUPERSEDED banner |
| MCP-7 | Sanitized MCP client env can hide SDK deps | `.cursor/mcp.json` includes venv `site-packages`; routing hook preserves existing `PYTHONPATH` |
| MCP-8 | 2026 catalog breadth without routing discipline | `trunk_recommend_stack` + `trunk_health`; candidates remain non-installable until trial/consent |

### Premortem MCP (residual risks)

1. Cursor must reload after `.cursor/mcp.json` — agents without trunk reinvent context.
2. External MCP tools lazy-invisible until first invoke — document, don't overclaim.
3. `place_skill` install action still PARK (no runner) — OK for this slice.
4. Governance root MCP deferred — design doc only, not live.

---

## Section B — Atlas Runtime Audit (2026-07-07 closure)

### Evidence

- `atlas reality --json`: status ok; browser ready; MCP configured (2 servers);
  Hermes local_takeover; LLM configured.
- `atlas doctor`: 5/6 — hermes_twin WARN (kanban unreachable).
- `atlas health`: governance OK, Merkle OK, hermes_mode mock, hermes_reachable false.
- Full `pytest` passed in this recovery slice.
- Mypy strict: Success, 216 source files.
- `inference_smoke.py` (with `.env`): groq OK (428ms); openrouter models rate-limited.
- `hermes_smoke.py` / `operational_smoke.py`: require `HERMES_BASE_URL` — not set;
  correct claim is local/mock, not live VPS.

### Capabilities matrix (honest)

| Capability | Status | Evidence |
|------------|--------|----------|
| audit.merkle | ready | doctor + audit --verify |
| execution.command | ready | bwrap path tested |
| browser.computer_use | ready | Chromium v1223 + computer_use tests |
| hermes.delegation | degraded | local_takeover; no HERMES_BASE_URL |
| llm.inference | configured/partial live | groq smoke OK; openrouter rate-limited |
| mcp.tools | configured | 2 servers in `~/atlas/mcp_servers.json` |
| self_improvement.cold_update | ready | tests |
| autonomy.decider | autonomous | decider tests |

### Invariantes (pass)

- Merkle chain intact
- governance.json validated
- Zero unclassified vapor (15 PARK/KEEP classified)
- SessionStart hook does not inject full ledger
- WORK_LEDGER compact (~25 lines post-audit)

### Premortem Atlas (residual risks)

1. OpenRouter rate limits look like provider failure — document as external, not Atlas bug.
2. Hermes VPS not wired — any "Hermes live" claim is false until `HERMES_BASE_URL` set.
3. PARK self-maintenance modules must not enter hot-path without explicit owner.
4. WAL `mcp.server_failed` for external server `ai.adeu/adeu` — investigate if recurring.
5. `uv lock --check` is blocked by the `redteam` extra resolver conflict; do not
   treat the dependency floor bump as lockfile-validated until that is resolved.

---

## Section C — Unified Verdict

**Live today (evidence-backed):** core runtime, Merkle audit, browser/computer-use,
groq inference smoke, MCP trunk surface (after Cursor reload), sanitation radar.

**Configured/degraded (honest):** Hermes (local/mock), openrouter LLM (rate-limited),
MCP client (spawn configured, live handshake varies by server), LessonStore/ADR
pending layers (PARK/PENDIENTE per ecosystem map).

**Next follow-ups:** reload Cursor for atlas-trunk; set `HERMES_BASE_URL` for VPS
smokes; optional `place_skill` runner; monitor `ai.adeu/adeu` MCP failures.
