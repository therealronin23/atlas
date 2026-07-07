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

- `atlas reality --json`: repo `main`, commit `94bd4609`, dirty tree, Merkle OK,
  browser initially degraded, LLM providers configured but not smoke-proven.
- Follow-up repair installed Playwright Chromium/headless shell v1223; `atlas
  reality --json` then reports browser/computer-use ready.
- `atlas reality --run-checks --include-browser --json`: initially degraded by
  `pytest_browser` and `browser readiness`; after repair, strict failures clear
  in local reality and browser marked ready.
- Core tests: `2825 passed, 2 skipped, 27 deselected, 6 warnings`.
- Browser/computer-use tests before repair: `16 failed, 10 passed, 1 skipped`.
- Browser/computer-use tests after repair: `26 passed, 1 skipped`.
- Mypy strict: `Success: no issues found in 216 source files`.
- Merkle audit: chain intact.
- `atlas doctor`: 5/6 checks passed; `hermes_twin` warning because kanban board
  is unreachable.
- `atlas health`: governance and Merkle OK; Hermes not reachable; recent WAL
  includes `mcp.server_failed` and self-maintenance events.
- `scripts/sanitation_audit.py`: initially 15 modules had zero non-test importers;
  follow-up repair now reports no unclassified vapor and lists those modules as
  classified zero-importers.
- Git state: 548 dirty paths, including 537 staged deletions under
  `.claude/skills`, 6 modified tracked paths, and 5 untracked paths.

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
- staged `pyyaml>=6.0.3` dependency bump;
- untracked `knowledge-src/`;
- new memory/design/audit files.

Core correctness is green, but merge safety is not just test status. The current
state should be split or at least committed as one explicit context-recovery
change before new feature work continues.

### Closed: dependency floor decision

`pyproject.toml` is staged with `pyyaml>=6.0.3`. This is accepted as a dependency
floor bump, not a new dependency. Targeted memory/MCP tests, browser tests, mypy,
and the final verification pass provide compatibility evidence.

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
