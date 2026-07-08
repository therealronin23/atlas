# WORK LEDGER — live state

Authority for WHERE/status only. Detail lives in design docs; why/lessons live in
`MEMORY.md` and `feedback-*.md`. Keep this short.

Format: `[estado] node — next action / blocked-by`. Estados: ✅ done · 🔄 active ·
⬜ pending · 🧱 wall · ⏸ parked.

✅ **SelfBuildRunner fuera del árbol vivo (2026-07-08)** —
`run_item` y `run_item_with_evolution` ejecutan ToolCoder y generan el patch en
worktrees git efímeros (mismo patrón que `_evaluate_candidate_in_worktree` /
ColdUpdateBatcher); `_revert_new_changes`/`_git_status_lines` eliminados — el
revert sobre el árbol vivo podía destruir trabajo concurrente sin commitear
(misma clase que el incidente "9 YAML regenerados"). El patch ahora incluye
ficheros NUEVOS (`git add -A` dentro del worktree efímero). Invariante intacto:
origin="self_audit" → HITL siempre. `tests/test_self_build_runner.py` green
(incl. regresión: fichero sucio del operador durante el run sobrevive a un
run_item fallido); mypy `src/atlas/` clean.

✅ **Dual audit MCP + Atlas runtime (2026-07-07)** —
`docs/governance/audits/audit_complete_premortem_2026-07-07.md` sección B+C cerrada:
manifest memory drift (`recall_multihop`/`shred`), catálogo skills, read_only trunk,
`.cursor/mcp.json`, path `.claude/skills`, docs stale marcados. MCP smoke stdio
desde Codex OK; `trunk_recommend_stack` y `trunk_health` exponen shortlist/diagnóstico
2026 sin instalar terceros; Cursor config preserva `src` + venv `site-packages`.
Runtime: `pytest` green, mypy clean, browser ready, Merkle OK. LLM: groq smoke OK;
openrouter rate-limited; Hermes sin `HERMES_BASE_URL` → local/mock. Dependency
floors accepted: `pyyaml>=6.0.3`, `cryptography>=49.0.0`, `litellm>=1.89.0`.

🔄 **Canonical Atlas ecosystem** —
`docs/design/atlas_ecosystem_map.md` es el mapa de estado. Next: clasificar trabajo
nuevo ahí antes de features.

🔄 **Selective assimilation line** —
`feedback-absorb-without-cloning.md`. Referencias activas: Cursor, Codex, Claude Code,
MemGPT/MemPalace, Hermes, Crawl4AI, Playwright MCP, Stirling PDF, desktop-control.

✅ **Browser/computer-use** — Playwright Chromium v1223; `pytest -m computer_use` pasa.

✅ **Vapor triage** — `sanitation_audit.py`: 0 vapor no clasificado; 15 módulos PARK/KEEP.
