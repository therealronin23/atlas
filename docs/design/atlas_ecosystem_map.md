# Atlas Ecosystem Map

Canonical map for Atlas state after the 2026-07-07 context recovery. This file
classifies the ecosystem; it is not a feature roadmap. The strategy is selective
assimilation without cloning: study external systems, absorb useful capabilities
or patterns, wrap them with Atlas invariants, measure, and improve.

## Taxonomy and States

Taxonomy: `Core`, `Capability`, `Adapter`, `MCP Surface`, `Skill`, `Prompt`,
`Knowledge Source`, `Absorbed Pattern`, `External Service`, `Governance`,
`Memory/Lesson`.

States: `SELLADO`, `ACTIVO`, `PENDIENTE`, `PARK`, `VAPOR`, `MURO`.

## Canonical Map

| Item | Taxonomy | State | Evidence | Authority | Relationship to Atlas | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| Gates A-I historical foundations | Governance | SELLADO | ROADMAP closed foundations; gate closure docs | `ROADMAP.md`, `docs/decisions/gates/CLOSURE.md` | Historical runtime foundation | Keep as sealed reference; do not duplicate state |
| ADR-024..040 runtime/governance base | Governance/Core | SELLADO | ROADMAP closed foundations | `docs/decisions/adr/`, `ROADMAP.md` | Observability, ColdUpdate, MCP client, untrusted boundary, decider | Keep sealed unless a new ADR explicitly supersedes |
| BwrapJail Slice 1 | Capability/Governance | SELLADO | AGENTS runtime dependency note; ADR-055 | `docs/decisions/adr/adr_055_os_level_sandbox_jail.md` | Fail-closed code execution containment | Keep; seccomp remains deferred |
| Reality kernel | Core | ACTIVO | `atlas reality` command; browser readiness now checks Playwright's expected executable | `src/atlas/core/reality.py`, `ROADMAP.md` | Source of truth for live state | Keep checks honest; avoid provider/live claims without smoke evidence |
| Selective assimilation strategy | Governance | ACTIVO | User preference recorded as memory | `feedback-absorb-without-cloning.md`, `MEMORY.md` | Guides external repo/tool absorption | Apply before adding any external capability |
| Absorption master plan | Governance/Absorbed Pattern | ACTIVO | Hermes/Codex/Cursor/Claude/Crawl4AI/Stirling/desktop sections | `docs/design/absorption_master_plan.md` | Working method for studying and wrapping external systems | Continue as detail doc, not live status |
| MCP trunk | MCP Surface | ACTIVO | `.cursor/mcp.json` wires atlas-trunk; manifest synced; Codex stdio smoke verified `tools/list`, `trunk_kinds`, `trunk_recommend_stack`, `trunk_prepare`, `trunk_health` | `docs/design/mcp_trunk_portable.md`, `.cursor/mcp.json` | Interoperability surface and task preflight surface for Cursor/clients | Keep manifest parity test; reload Cursor after config change |
| Cursor MCP wiring | MCP Surface | ACTIVO | `.cursor/mcp.json` committed; atlas-trunk stdio to `~/atlas-mcp` + repo root; env includes `src` + venv `site-packages` for sanitized clients | `.cursor/mcp.json` | Cross-play for Cursor agent sessions | Verify connection in Settings → Tools & MCP after reload |
| MCP 2026 shortlist | MCP Surface/Governance | ACTIVO | `trunk_recommend_stack` ranks installed/verified first; `trunk_health` surfaces configured servers, missing env names, read-only tools, and prioritized trial candidates | `docs/design/mcp_catalog.yaml`, `src/atlas/mcp/catalog.py`, `src/atlas/mcp/trunk_server.py` | Curated discovery without blind installation | Run trial/security review/consent before promoting any candidate |
| Trunk task preflight | MCP Surface/Absorbed Pattern | ACTIVO | `trunk_prepare(goal)` returns compact task packets from catalog/workbench/usage signals; AtlasCoder/ToolCoder inject a fail-open preflight section before coding loops | `src/atlas/mcp/trunk_prepare.py`, `src/atlas/core/trunk_preflight.py`, `tests/test_trunk_prepare.py` | Makes the trunk a context control plane per task without Redis/LangGraph dependencies | Measure real tool usage and refine catalog purposes/aliases |
| Playwright MCP | MCP Surface/Capability | ACTIVO | Absorption doc: live stdio handshake and token-cost measurement | `docs/design/absorption_master_plan.md` | Browser-accessibility external surface | Keep gated; browser readiness still must be honest |
| Crawl4AI | Capability/Knowledge Source | ACTIVO | Absorption doc: isolated venv, SSRF, untrusted wrapping, tests | `docs/design/absorption_master_plan.md` | Scraping/knowledge ingestion capability | Keep; revisit benchmark vs agent-browser only when needed |
| Stirling PDF | External Service/Capability | ACTIVO | Absorption doc: deployed via Docker with wrapper route | `docs/design/absorption_master_plan.md` | PDF capability through governed external service | Keep as absorbed service; do not fold into core |
| Desktop-control | Capability/Adapter | PENDIENTE | GUI slice closed, real-display control pending | `docs/design/absorption_master_plan.md` | Potential host-control capability | Design gating before enabling mutating real-display control |
| Hermes Agent | Absorbed Pattern/External Service | ACTIVO | Hermes Agent oficial de Nous instalado en `~/.hermes/hermes-agent`; Hermes posee Telegram, Atlas ya delega saliente por `HermesKanbanAdapter` sobre `hermes kanban` local (`atlas reality`: `hermes.mode=kanban_local`; smoke live `t_57d5aa9f` y `t_cd4cf949` delegados), y el runtime estable quedó endurecido con NVIDIA NIM como proveedor primario verificado. Groq quedó validado a nivel API con la clave nueva pero fuera del fallback automático porque la cuenta on-demand devuelve 413/TPM con el contexto mínimo de Hermes; OpenRouter y Gemini siguen fuera del camino activo por crédito agotado / clave inválida | `~/.hermes/hermes-agent`, `~/.hermes/config.yaml`, `~/.hermes/.env`, `scripts/hermes_local.sh`, `scripts/hermes_agent_stub/agent.py`, `src/atlas/hermes/kanban_bridge.py`, `src/atlas/hermes/hermes.py`, `src/atlas/core/orchestrator.py`, ADR-026 | Source of patterns and optional peer service | Retire el stub REST cuando se confirme que ya no tiene callers reales fuera de compatibilidad heredada |
| Codex CLI / Cursor / Claude Code | Absorbed Pattern | ACTIVO | Cross-comparison found concrete coding workflow gaps | `docs/design/absorption_master_plan.md` | Sources for patching, repo context, permissions, hooks | Absorb specific patterns when verified and compatible |
| MemGPT / MemPalace class systems | Absorbed Pattern/Memory/Lesson | PENDIENTE | User strategy; not yet reconciled to code evidence in this pass | `MEMORY.md` | Memory architecture inspiration | Audit concrete mechanisms before implementation |
| `.claude/skills/` local bundle | Skill | SELLADO | `git rm --cached -r .claude/skills`; local files still present; `.gitignore` covers it | `.gitignore`, context audit | Install/cache artifact for external agents | Keep out of Git; reinstall/update through skill tooling |
| Skills as Atlas ecosystem objects | Skill | ACTIVO | Trunk design: skills are "saber", MCP is "hacer" | `docs/design/mcp_trunk_portable.md` | Procedural knowledge, separate from MCP surface | Serve/install with provenance and consent, not as repo dump |
| Prompts/franken-prompt modules | Prompt | MURO | MCP design: MCP cannot impose system prompt | `docs/design/mcp_trunk_portable.md` | Advisory templates unless delivered by real client channel | Do not overclaim; only implement through real wrapper/hook |
| Knowledge-src root | Knowledge Source | ACTIVO | `KnowledgeTrunk` ingests API sources with provenance; `knowledge-src/preferencias` is classified as policy/design seed | `src/atlas/mcp/knowledge_trunk.py`, `src/atlas/mcp/memory_trunk.py`, `knowledge-src/preferencias` | API/source ingestion into Atlas memory plus explicit factual/personal memory routing | Keep raw source data provenance-backed; do not ingest policy notes as facts |
| Dependency floors | Governance | SELLADO | `pyyaml>=6.0.3`, `cryptography>=49.0.0`, and `litellm>=1.89.0` accepted; tests/mypy/reality pass; `uv lock --check` blocked by redteam resolver conflict | `pyproject.toml`, `WORK_LEDGER.md` | Existing dependency floor declarations, not new dependencies | Keep floors unless a dependency audit requires newer ones |
| Compliance gateway/Osmosis | Capability/Governance | PARK | AGENTS current direction; paper/demo public artifacts | `docs/decisions/adr/adr_051*`, `docs/membrana/` | Public-facing compliance/filter line | Keep parked unless user reopens product/demo work |
| Universal verifier ADR-041 | Core | PENDIENTE | ROADMAP build-up layer, core present but wiring deferred | `ROADMAP.md`, ADR-041 | Evidence gate for artifacts | Wire only when it closes a current capability path |
| Cascade routing ADR-042 | Core | PENDIENTE | ROADMAP/backlog says operational wiring deferred | `ROADMAP.md`, `docs/design/backlog.md` | Producer routing by cost/evidence | Keep pending; do not declare live |
| Swarm / worker backend ADR-045/046 | Core | PENDIENTE | ROADMAP says gated/deferred; ledger history reports schedulers off | `ROADMAP.md`, `docs/design/backlog.md` | Governed proposal generation | Keep off until objective autonomy criteria exist |
| LessonStore ADR-044 | Memory/Lesson | ACTIVO | `workspace/lessons/` is the shared authority for Atlas self-maintenance wiring and twin-local learning continuity | `src/atlas/core/orchestrator_parts/maintenance_facade.py`, `src/atlas/mcp/trunk_server.py`, `WORK_LEDGER.md` | Verified lessons and avoid patterns | Keep one shared store; do not fork Atlas/Hermes lesson state |
| Browser/computer-use local runtime | Capability | ACTIVO | Playwright Chromium/headless shell v1223 installed; `pytest -m "computer_use"` passes | `src/atlas/tools/browser.py`, `src/atlas/core/reality.py` | Host browser control | Re-run browser checks after Playwright upgrades or cache cleanup |
| Zero-importer module radar | Governance | ACTIVO | `scripts/sanitation_audit.py` reports no unclassified vapor and lists 15 classified zero-importer modules | `scripts/sanitation_audit.py`, `docs/audits/audit_context_premortem_2026-07-07.md` | Keeps unwired/entrypoint/parked capabilities honest without deleting tested components | Keep classifications current; unclassified vapor must be wired, parked, or quarantined |

## Absorbed Patterns Matrix: Aider/Cursor/Codex/Claude Code

This matrix details architectural patterns observed in Aider, Cursor, Codex, and Claude Code, prioritized by detected real pressure in Atlas delegations as of 2026-07-08. The goal is selective assimilation of core architectural strengths, not cosmetic features.

| Capability | Aider (Pattern, Reference, Priority) | Cursor (Pattern, Reference, Priority) | Codex (Pattern, Reference, Priority) | Claude Code (Pattern, Reference, Priority) |
|---|---|---|---|---|
| **1. Code Generation/Completion** | *Interactive Diff-based Editing*. Ref: Aider CLI, `git diff` integration. Priority: High. | *Multi-file Contextual Generation*. Ref: Cursor IDE, multi-file chat. Priority: High. | *Function/Block Completion*. Ref: Original Codex papers/demos. Priority: Medium. | *Natural Language to Code (API-driven)*. Ref: Claude API docs, safety features. Priority: Medium. |
| **2. Context Management/Retrieval** | *Git-aware Context Window*. Ref: Aider's `git diff` and `git add -p`. Priority: High. | *Semantic Codebase Indexing*. Ref: Cursor's "smart" context, embeddings/ASTs. Priority: High. | *Prompt Engineering for Context*. Ref: Early LLM usage patterns. Priority: Low. | *Conversation History + File Snippets*. Ref: Claude chat, file attachments. Priority: Medium. |
| **3. Tool Use/Orchestration** | *Shell Command Integration*. Ref: Aider's interactive shell. Priority: High. | *Integrated Terminal & Debugger*. Ref: Cursor IDE features. Priority: High. | *Limited External Tooling*. Ref: Original Codex usage. Priority: Low. | *Function Calling/Tool Use API*. Ref: Claude's tool use capabilities. Priority: High. |
| **4. Self-Correction/Feedback Loops** | *Test-Driven Iteration*. Ref: Aider's `TDD` mode. Priority: High. | *User-Guided Refinement*. Ref: Cursor's chat interface. Priority: Medium. | *Implicit Feedback from User*. Ref: Early LLM interaction. Priority: Low. | *Error Analysis & Suggestion*. Ref: Claude's debugging capabilities. Priority: High. |
| **5. Human-in-the-Loop/Approval** | *Interactive Diff Approval*. Ref: Aider's `git add -p` workflow. Priority: High. | *Chat-based Review & Edit*. Ref: Cursor's integrated chat and editing. Priority: High. | *Manual Review & Copy-Paste*. Ref: Basic LLM interaction. Priority: Low. | *Explicit Approval Prompts*. Ref: Claude's safety features, conversational flow. Priority: High. |

## Zero-Importer Triage Snapshot

Classification from the 2026-07-07 sanitation radar. This is not deletion
approval; it prevents zero-importer modules from being called live by accident.

| Module group | State | Rationale | Next action |
| --- | --- | --- | --- |
| `_crawl4ai_worker.py` | KEEP | Subprocess entrypoint used by `CrawlerTool` in isolated venv | Keep out of normal import graph |
| `root_cause_classifier.py`, `benchmark_gate.py`, `failure_lesson_sink.py`, `evolution_gate.py` | KEEP | Injectable components used by ColdUpdate/Batcher/SelfBuild paths when configured | Do not claim always-on; wire only through explicit runtime config |
| `incremental_coder.py`, `lesson_runner.py` | PARK | Tested coding/lesson workflows without current runtime owner | Reopen with CLI/runtime owner or quarantine later |
| `history_compactor.py`, `token_budget.py` | PARK | Standalone context utilities; caller-owned | Wire only when a caller needs them |
| `preflight_gate.py`, `batch_premortem.py`, `topic_expander.py`, `panorama_scout.py`, `sota_snapshot.py` | PARK | Self-maintenance/discovery helpers; scheduler/service-runner owner not enabled | Reopen with service-runner path |
| `immunity/live_loop.py` | PARK | Gated hook adapter, no hot-path owner enabled | Keep disabled unless gateway hook is explicitly reopened |

## Operating Rule

New work must add or update one row here before adding another roadmap item.
If a capability has no non-test consumer, mark it honestly as `PENDIENTE`,
`PARK`, `KEEP as entrypoint/injectable`, or `VAPOR`; do not call it live.
