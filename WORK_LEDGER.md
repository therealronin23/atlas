# WORK LEDGER — live state

Authority for WHERE/status only. Detail lives in design docs; why/lessons live in
`MEMORY.md` and `feedback-*.md`. Keep this short.

Format: `[estado] node — next action / blocked-by`. Estados: ✅ done · 🔄 active ·
⬜ pending · 🧱 wall · ⏸ parked.

🔄 **Context hygiene / ecosystem recovery (Tipo 2)** —
`docs/governance/audits/audit_context_premortem_2026-07-07.md` found context
collapse: oversized ledger, tracked local skill bundles, missing WHY authority,
browser readiness overclaim, and system-vapor. Closed in this pass: canonical map,
compact `AGENTS.md`/ledger, `MEMORY.md` authority, Claude SessionStart no-ledger
hook, `.claude/skills` de-tracked while kept on disk, browser readiness code fix.
Follow-up closure: Playwright Chromium v1223 installed locally; browser/computer-use
tests now pass. `pyyaml>=6.0.3` accepted as a floor bump with tests/mypy evidence.
`knowledge-src/preferencias` classified as policy/design seed and backed by
`MemoryTrunk.add_from_knowledge_src`/`add_from_user_preference`.
Next: finish staged review/commit hygiene.

🔄 **Canonical Atlas ecosystem** —
`docs/design/atlas_ecosystem_map.md` is now the state map for sealed foundations,
active assimilation, MCP surface, skills/prompts/knowledge sources, parked work,
vapor, and walls. Next: keep new work classified there before adding features.

🔄 **Selective assimilation line** —
Atlas improves by dissecting external systems and absorbing useful capabilities
without cloning product identities (`feedback-absorb-without-cloning.md`). Active
references: Cursor, Codex, Claude Code, MemGPT/MemPalace, Hermes, Crawl4AI,
Playwright MCP, Stirling PDF, desktop-control.

✅ **Dirty state classification** —
`pyproject.toml` floor bump is accepted in this recovery slice; `knowledge-src/`
is no longer an unclassified scratch dump. Remaining dirty state is the intended
context-recovery change plus local skill-bundle de-tracking.

🔄 **Browser/computer-use readiness** —
`src/atlas/core/reality.py` now checks Playwright's expected Chromium executable,
not just any cached browser binary. Current status: ready after installing
Playwright Chromium/headless shell v1223; `pytest -m "computer_use"` passes.

✅ **Vapor triage** —
`scripts/sanitation_audit.py` now separates unclassified vapor from classified
0-importer modules. Current result: no unclassified orphan modules; 15 modules
classified as KEEP/PARK with explicit owner/rationale.
