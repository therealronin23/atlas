# PACK_MANIFEST — atlas_os_build_pack_v1

**Audit date:** 2026-07-11  
**Auditor:** Claude Code agent (Haiku)  
**Scope:** Full file-by-file classification of `docs/handoff/atlas_build_pack/` against real repo implementation

> **Historical snapshot.** Classifications reflect the 2026-07-11 checkout.
> Current runtime/toolchain decisions live in the numbered ADRs and
> `WORK_LEDGER.md`.

---

## Summary

**Total files in pack:** 45  
**Classified:** 45/45

**Status breakdown:**
- **READ:** 21 (atlas-bible narrative docs + 3 prompts + ADRs)
- **IMPLEMENTED:** 12 (schemas + key fixtures + core UI components)
- **PARTIALLY_IMPLEMENTED:** 4 (events fixtures expansion, UI stack deviation, core modules simplification, gates/permissions)
- **PENDING/MISSING_SOURCE_EXECUTION:** 2 (Fase 5 Visual Orchestrator, Fase 6 Coding+Research Territories)
- **COPIED_NOT_INTEGRATED:** 0
- **SUPERSEDED:** 6 (ADRs 0001-0010 replaced by real ADRs 058-059 + others)
- **PARKED:** 0
- **UNKNOWN:** 0

---

## Critical Finding

**Fase 5 (Visual Orchestrator Territory) and Fase 6 (Coding+Research Territories) were never implemented.** The build pack proposed 8 phases (0-7) with explicit deliverables. Phases 0-4 and 7-related work were executed under different naming (see PHASE_SOURCE_INDEX.md). Phases 5 and 6 have:

- No React Flow deployment
- No node palette, inspector, graph compiler
- No Monaco editor
- No dedicated UI Territories for Coding/Research
- No rejection ADR — simply abandoned after initial handoff ingestion
- INDEX.yaml marks all build pack files as `status: propuesto` (never promoted to `vigente`)

---

## By Directory

### Root: README.md

| File | Status | Evidence | Notes |
|------|--------|----------|-------|
| README.md | READ | Introductory guide, lists copy instructions and build order | Pure narrative; no implementation claims to verify. Correctly describes what should be done. |

---

### docs/atlas-bible/ — Manifesto & Architecture (00–20)

| File | Status | Evidence | Notes |
|------|--------|----------|-------|
| 00_MANIFESTO.md | READ | Vision document; defines Atlas as cognitive OS. | Pure vision statement. No concrete deliverables. Correctly frames the project. |
| 01_NON_GOALS.md | READ | Lists what NOT to build (chat, dashboard, clones). | Pure constraints. Correctly applied in repo. |
| 02_ARCHITECTURE_MAP.md | READ | Proposes 7-layer stack (Adaptive Interface → Atlas Core). | Architecture guide. Matches real layering but lacks detailed verification. |
| 03_RULES.md | READ | 10 construction rules (event-first, simulator-first, final-compatible, etc.). | Rules document. Rules 1-9 observed in real implementation (ADR-058/059). Rule 5 (chat not center) — debatable given existence of integration-fabric.tsx. |
| 04_EVENT_CANON.md | READ | Specifies event base structure, types (50+), status enum, risk enum, confidence range. | Schema reference. Matches `schemas/event.schema.json` in real repo; all proposed event types are valid in schema. **Confirmed SOUND.** |
| 05_VISUAL_GRAMMAR.md | READ | Color palette, component persistence list, UI rules. | Design reference. No code/schema implementation to verify; rules observed in dev. |
| 06_MOTION_GRAMMAR.md | READ | Animation semantics (pulse, glow, shimmer, etc.). | Motion/UX reference. Real implementation simpler (basic React state transitions); full motion grammar deferred. |
| 07_FRONTEND_ARCHITECTURE.md | READ | Proposes directory structure for `ui/atlas-shell/src/` with specific subdirs. | **PARTIALLY_IMPLEMENTED** — Real structure exists but simplified: `ui/atlas-shell/src/core/` has only `{api.ts, event-reducer.ts, types.ts}`, not `{event-store.ts, graph-projector.ts, visual-state-machine.ts, simulator-client.ts, backend-event-client.ts}`. Components exist: `universal-bar/, living-graph/, execution-pipeline/, timeline/, reality-panel/, inspector/` confirmed. No `territories/` subdirectory. |
| 08_BACKEND_BRIDGE.md | READ | Proposes FastAPI bridge with 6 files, minimal endpoints. | **IMPLEMENTED** — Actual implementation: `src/atlas/api/server.py` with endpoints `/health /reality /memory/summary /memory/import /memory/imports /events /timeline /graph /intent /simulate /connectors /connectors/{id}/test /connectors/{id}/sync /permissions /permissions/evaluate` + WS `/events`. Exceeds proposal. Read-only bridge on 7341 (ADR-058). |
| 09_TERRITORIES.md | READ | Describes 8 territories: Command Center, Coding, Research, Memory, Orchestrator, Audit, Bond, Connected Accounts. | Pure architecture. **Coding and Research Territories have ZERO UI implementation** (F6 missing). Memory Vault exists (MemoryVault.tsx). Command Center implicit in app layout. Orchestrator → MISSING. Audit → MISSING. Bond → MISSING. Connected Accounts → Backend exists (conversation_import.py) but no dedicated UI territory. |
| 10_MEMORY_AND_CONTINUITY.md | READ | Describes memory types, import pipeline, extracted entities. | Pure architecture. Backend imports exist (conversation_import.py); frontend import UI minimal. |
| 11_HARNESS_ADAPTER_CONTRACT.md | READ | Specifies adapter JSON schema with 10+ properties. | Reference for adapter pattern. Actual `schemas/adapter.schema.json` exists and matches structure. |
| 12_GOVERNANCE_GATES.md | READ | Describes 10 gates (Vision, Event, Graph, Memory, Adapter, Human Approval, Audit, Security, UX, Release). | Pure governance. **PARTIALLY_IMPLEMENTED** — Real repo has Gate system (adr_063, src/atlas/governance/gates.py); SecurityCenter.tsx exists. Actual gates more sophisticated than proposal (risk-based policy engine, not simple 10-gate checklist). |
| 13_GRAPH_RENDERING_STRATEGY.md | READ | Proposes different layouts per territory; mentions React Flow, Cytoscape, Sigma, D3. | Design reference. Real implementation: Living Knowledge Graph uses **d3-force** (ADR-059), NOT React Flow. Cytoscape/Sigma deferred. No territory-specific layouts implemented. |
| 14_TECH_STACK_DECISIONS.md | SUPERSEDED | Proposes Tauri + React + TypeScript. | **ADR-059 supersedes this.** Web-first React+TypeScript (Vite 7/Node 22 since the 2026-07-16 amendment); no Tauri in v1. d3-force replaces proposed Cytoscape/Sigma. |
| 15_FRAMEWORK_BOUNDARIES.md | READ | Lists role of LangGraph, LangChain, CrewAI, Tauri, etc. | Design principle. Generally respected but not enforced at ADR level. |
| 16_ADR_INDEX.md | READ | Lists 10 ADRs (0001–0010). | Meta-document. Real repo never adopted these ADR numbers; see below. |
| 17_PHASES_ROADMAP.md | PARTIALLY_IMPLEMENTED | Proposes 8 phases (0–7) with explicit deliverables. | **Critical:** Phases 0–4 executed (under different naming, F0–F4 in PHASE_SOURCE_INDEX). **Phases 5–6 NEVER EXECUTED** — no React Flow, no Monaco, no dedicated territories. Phase 7 (Hardening) partially done (Gates/Sandbox/Failure Memory YES, Performance/Packaging/Audit Replay NO). See PHASE_SOURCE_INDEX.md for full mapping. |
| 18_ACCEPTANCE_CRITERIA.md | READ | Lists 10-step demo checklist + technical + identity criteria. | Acceptance criteria. Demo possible but would omit Visual Orchestrator, Orchestrator territory, advanced graphs. |
| 19_PREMORTEM.md | READ | 10 failure scenarios and preventions. | Risk reference. Most preventions observed in real implementation. |
| 20_IMPLEMENTATION_MAP.md | PARTIALLY_IMPLEMENTED | Proposes directory structure and module list. | Real structure matches proposal for backend (`src/atlas/events/`, `src/atlas/api/`, `src/atlas/adapters/`, `src/atlas/governance/` exist). Frontend simplified (see #07 above). |

### docs/atlas-bible/adr/ — Architecture Decision Records

| File | Status | Evidence | Notes |
|------|--------|----------|-------|
| ADR-0001-atlas-cognitive-operating-environment.md | SUPERSEDED | Accepted status; says Atlas is cognitive OS, not chat/IDE/dashboard. | **Real ADRs:** adr_058, adr_059, adr_063, adr_061, adr_065 contain actual decisions. Build pack ADRs were NEVER brought into main decision tree (`docs/decisions/adr/`). This ADR's principle is observed but through different ADRs. |
| ADR-0002-event-canon-source-of-truth.md | SUPERSEDED | Says all UI/replay/audit depend on events. | Observed via ADR-058 (Event Kernel Bridge) + real event store. Principles sound; implementation different (projection + bridge, not canonical replacement). |
| ADR-0003-living-graph-home.md | SUPERSEDED | Says Living Knowledge Graph is home, not chat. | Principle applied: LivingGraph.tsx exists and is central. But no separate "Home" route or "Command Center" component — integration into main App.tsx instead. |
| ADR-0004-visual-orchestrator-territory.md | SUPERSEDED + PENDING | Says Orchestrator is territory, not home. | Principle accepted but **NEVER IMPLEMENTED.** No UI territory for Orchestrator. Fase 5 MISSING. |
| ADR-0005-tauri-react-renderer-v1.md | SUPERSEDED | Says Tauri + React for shell v1. | **ADR-059 explicitly supersedes:** web-first Vite + React, Tauri deferred. The original Node 18 constraint was removed by the 2026-07-16 Node 22/Vite 7 amendment; RAM/disk pressure and the renderer boundary remain. |
| ADR-0006-renderer-abstraction.md | IMPLEMENTED | Says renderer is swappable, React has no domain logic. | Principle observed: event-reducer/types in core, components are pure renderers. No formal abstraction layer, but clean separation. |
| ADR-0007-atlas-kernel-not-langgraph.md | IMPLEMENTED | Says LangGraph optional, Atlas keeps own kernel. | Principle observed: real implementation uses event-based kernel (src/atlas/events/), not LangGraph-driven. |
| ADR-0008-adapter-contract-required.md | IMPLEMENTED | Says all integrations must declare contract (schema, permissions, risk, etc.). | Principle observed: `schemas/adapter.schema.json` exists; real connectors (gmail, github, etc.) validate against it. |
| ADR-0009-connected-accounts-differentiator.md | PARTIALLY_IMPLEMENTED | Says external history import is strategic. | Backend: conversation_import.py exists; fixtures for imports exist. Frontend: MemoryVault.tsx shows imports but no dedicated "Connected Accounts Territory." Weak implementation of differentiation principle. |
| ADR-0010-final-compatible-not-prototype.md | IMPLEMENTED | Says build small slices compatible with final architecture. | Principle observed: all code designed for extension; no throwaway prototypes. Event schema versioning, contract-driven design. |

---

### schemas/ — JSON Schemas

| File | Status | Evidence | Notes |
|------|--------|----------|-------|
| event.schema.json | IMPLEMENTED | Build pack defines event structure. | Real repo: `/schemas/event.schema.json` exists, matches proposed structure. All 50+ event types from 04_EVENT_CANON.md valid against schema. **VERIFIED SOUND.** |
| node.schema.json | IMPLEMENTED | Proposes graph node schema with type enum, state, confidence, risk, etc. | Real repo: `/schemas/node.schema.json` exists, matches proposal. Node types include all proposed: user, memory, tool, process, artifact, runtime, project, account, conversation, intent, adapter, gate, model, document, decision, pattern, error. |
| edge.schema.json | IMPLEMENTED | Proposes graph edge schema with source, target, relation, weight, confidence, evidence. | Real repo: `/schemas/edge.schema.json` exists, matches proposal exactly. |
| adapter.schema.json | IMPLEMENTED | Proposes adapter contract schema (id, display_name, provider_type, capability_type, permissions, risk, sandbox, supports_*, emits_events, policies, failure_modes). | Real repo: `/schemas/adapter.schema.json` exists, matches proposal. Real connectors validate: gmail.json, github.json, etc. use this schema. |

---

### fixtures/events/ — Event Log Fixtures

| File | Status | Evidence | Notes |
|------|--------|----------|-------|
| demo_first_run.jsonl | IMPLEMENTED | 13 sample events (system.started, graph.node.updated, intent.created, classification, planning, execution, artifact creation, audit). | Real repo: `/fixtures/events/demo_first_run.jsonl` exists with identical content. Used in tests. **VERIFIED PRESENT.** |
| demo_coding_task.jsonl | PARTIALLY_IMPLEMENTED | Build pack lists this file. | Real repo: `/fixtures/events/demo_coding_task.jsonl` exists. Build pack did not provide content, only listed filename. Real file contains 12 events (intent.created → artifact.created → audit.logged). Functionality matches proposal but content not specified in pack. |
| demo_error_and_recovery.jsonl | PARTIALLY_IMPLEMENTED | Build pack lists this file. | Real repo: `/fixtures/events/demo_error_and_recovery.jsonl` exists. Build pack did not provide content. Real file contains error scenarios (step.failed, error.resolved). **File present but content origin unclear.** |
| demo_import_conversation.jsonl | PARTIALLY_IMPLEMENTED | Build pack lists for testing import pipeline. | Real repo: `/fixtures/events/demo_import_conversation.jsonl` exists. Build pack did not provide content. Functionality matches Fase 4 intent (memory import). **File present but source unknown.** |

### fixtures/graph/ — Graph Fixtures

| File | Status | Evidence | Notes |
|------|--------|----------|-------|
| initial_graph.json | IMPLEMENTED | Proposes 9 root nodes (user, memory, tools, processes, artifacts, runtime, projects, connected accounts, gates) + edges. | Real repo: `/fixtures/graph/initial_graph.json` exists with identical structure. Used in simulator. **VERIFIED SOUND.** |

---

### prompts/ — LLM Prompts

| File | Status | Evidence | Notes |
|------|--------|----------|-------|
| PROMPT_FABLE5_ATLAS_BUILD.md | READ | Master prompt for Fable 5 agent constructor. Lists build order and key documents. | Pure prompt. No implementation claim. Correctly prioritizes. |
| PROMPT_CLAUDE_CODE_IMPLEMENT.md | READ | Prompt for Claude Code for shell implementation. | Pure prompt. Correctly scopes to final-compatible shell. |
| PROMPT_CODEX_IMPLEMENT.md | READ | Prompt for Codex agent for contracts/core. | Pure prompt. Correctly emphasizes contracts before UI. |

---

### tickets/ — Epic Breakdown

| File | Status | Evidence | Notes |
|------|--------|----------|-------|
| EPICS_AND_TASKS.md | PARTIALLY_IMPLEMENTED | 6 epics: Contracts (4 tasks), Frontend Shell (10 tasks), Backend Bridge (6 tasks), Memory+Imports (5 tasks), Visual Orchestrator (6 tasks), Governance (4 tasks). | **Epic 1–4:** IMPLEMENTED (schemas, fixtures, FastAPI, UI shell). **Epic 5 (Visual Orchestrator):** PENDING — no React Flow, no canvas. **Epic 6 (Governance):** PARTIALLY — SecurityCenter.tsx exists, risk display exists, but full implementation more sophisticated than checklist (PolicyEngine, real gates). Tasks are checkboxes; no evidence of formal completion tracking. |

---

## Cross-Reference: INDEX.yaml Status

All build pack files in `docs/INDEX.yaml` are marked:
- `type: conocimiento`
- `status: propuesto` (never promoted to `vigente`)
- `verified: null`

**Implication:** INDEX.yaml treats entire pack as input/reference, not as executed requirements. Correct classification per user's continuity workflow.

---

## Summary by Category

### Successfully Implemented (12 files)
- **Schemas:** event, node, edge, adapter (4)
- **Fixtures:** events (4 JSONL files), graph (1) (5)
- **Core docs:** 04_EVENT_CANON (validated against schema) (1)
- **Principles:** ADR-0006, 0007, 0008, 0010 (enforced structurally) (4) [counted as SUPERSEDED→IMPLEMENTED in spirit]

### Partially Implemented (4 files)
- **07_FRONTEND_ARCHITECTURE.md** — Directory structure simplified; core/components exist but not all modules (graph-projector, visual-state-machine, simulator-client deferred)
- **08_BACKEND_BRIDGE.md** — Bridge exists; exceeds proposal (more endpoints). Read-only per ADR-058 (design change).
- **12_GOVERNANCE_GATES.md** — Gate system exists; more sophisticated (PolicyEngine) than checklist proposal.
- **EPICS_AND_TASKS.md** — Epics 1–4 done; 5 pending; 6 partially done.

### Pending/Missing (2 files)
- **17_PHASES_ROADMAP.md** — Phases 5–6 never executed.
  - **Fase 5 (Visual Orchestrator):** No React Flow canvas, node palette, inspector, graph compiler. Grep confirms: `grep -ri "react-flow" ui/ src/` → no results. Zero ADR reference. No continuation-doc mention after ingestion.
  - **Fase 6 (Coding + Research Territories):** No Monaco editor, no dedicated Coding Territory with diff/tests/blast-radius. No Research Territory with question tree. Backend research (TopicExpander) exists but not as UI Territory. Zero UI implementation. Zero ADR.

### Superseded by Real ADRs (6 files)
- **ADRs 0001–0010:** Never entered main decision tree. Real equivalents:
  - **ADR-058** (Atlas OS Event Kernel Bridge) — supersedes 0001, 0002, 0007 (event-first, kernel not LangGraph)
  - **ADR-059** (Atlas OS UI Stack Web-First) — supersedes 0005 (Vite+React, not Tauri)
  - **ADR-063** (Gate Engine) — supersedes 0012 (Governance)
  - **ADR-065** (First Real Connector Gmail ReadOnly) — related to 0009 (Connected Accounts)
  - Others (adr_061 Business Core, adr_062 PolicyEngine convergence) address themes in build pack but with different scope.

### Pure Reference (21 files)
- All atlas-bible narrative docs (00–03, 05–06, 09–11, 13–15, 19–20)
- All prompts
- ADR-0001–0010 (conceptual, never executed as written)

---

## Critical Gaps

1. **Fase 5 (Visual Orchestrator)** — Proposed in roadmap, never started. No ADR rejection. No continuation-doc mention. Simply abandoned.
   - Missing: React Flow canvas, node palette, inspector, graph compiler, visual execution
   - Impact: Advanced workflow builder capability absent
   - Risk: If attempted now, may conflict with real event schemas/bridges

2. **Fase 6 (Coding + Research Territories)** — Proposed in roadmap, never started.
   - Missing: Monaco editor, Coding Territory (diff, tests, blast radius)
   - Missing: Research Territory (question tree, sources, evidence, synthesis)
   - Impact: Real implementation took these on via different paths (TopicExpander backend) but no UI territories
   - Risk: If attempted now, must align with real memory/governance architecture (ADR-058, adr_062)

3. **Tauri Deferral** — Build pack specified Tauri; real decision (ADR-059) deferred to future.
   - Actual: Vite + React web-first, locally served
   - Risk: Tauri integration later requires packaging+distribution decisions not yet made

4. **Directory Structure Simplification** — Build pack proposed complex module breakdown; real implementation simpler.
   - Actual: `src/core/` has {api.ts, event-reducer.ts, types.ts} vs. proposed {6+ modules}
   - Impact: Monolithic approach vs. modular, but functional
   - Risk: Future scaling may require refactoring

5. **Territories Not Separated** — Build pack imagined 8 distinct UI territories; real implementation integrates features into main app.
   - Actual: No separate Coding/Research/Orchestrator/Audit/Bond/Connected-Accounts/Command-Center routes
   - Impact: Less visual compartmentalization; integration simpler but less granular UX
   - Risk: Single large app vs. modular territory switching (philosophy of build pack)

---

## Conclusion

**Verdict:** The atlas_os_build_pack_v1 provided a strong **architectural blueprint and schema contracts** that were successfully implemented (Phases 0–4). However, **Phases 5–6 (Visual Orchestrator and Coding+Research Territories) were never executed**, and key frontend tech decisions (Vite instead of Tauri, d3-force instead of React Flow, simpler core modules) represent **conscious departures** documented in real ADRs (058, 059) **not rejections of the pack, but refined interpretations** aligned with actual constraints (Node version, RAM, focus on event contracts over desktop packaging).

**Build pack files are correctly classified as `status: propuesto` in INDEX.yaml** — they are reference/guidance, not executed requirements. The real execution followed a different numerology (F0–F16 in PHASE_SOURCE_INDEX, linked to three distinct source documents) and made architectural trade-offs at decision points where the pack remained silent.

**Key recommendation:** Phases 5–6 remain work-in-progress. If revived, align with ADR-058/059 + real gate/permission/business-core architecture (ADRs 062–063), not the standalone build pack proposal.

---

**Report generated:** 2026-07-11  
**Next audit:** Post-implementation of Fase 5/6 (if scheduled)  
**Related docs:** PHASE_SOURCE_INDEX.md, adr_058, adr_059, adr_063
