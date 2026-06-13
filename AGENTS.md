# ATLAS CORE — Operating Context For Agents

This file is operational context, not marketing copy. If it conflicts with live
evidence, live evidence wins.

## Reality First

Before making claims about Atlas state, run:

```bash
cd ~/proyectos/atlas-core
source .venv/bin/activate
PYTHONPATH=src atlas reality --json
```

For fresh verification:

```bash
PYTHONPATH=src atlas reality --run-checks --include-browser --json
```

Do not hand-maintain test counts in docs. Do not claim Hermes, Telegram,
browser, LLM, or MCP are live unless the current environment or a fresh smoke
proves it.

## What Atlas Is

Atlas is a local intelligence runtime. It coordinates local tools, local models,
free/provider models, memory, approvals, audit, and cold self-improvement. It is
not a SaaS wrapper and not a chatbot shell.

The desired direction is maximum verified capability:

- know what is true locally;
- mark unknowns as unknown;
- execute through typed capabilities;
- audit external effects in Merkle;
- keep dangerous changes reversible or human-approved;
- improve itself through isolated validation, not hot self-patching.

## Current Architectural Shape

- Core runtime: `src/atlas/core/orchestrator.py` plus collaborators in
  `src/atlas/core/orchestrator_parts/`.
- Agentic loop: `AgenticExecutor` handles tool-calls, suspend/resume HITL,
  untrusted-content wrapping, and mutation dispatch.
- Security: capability tokens, `AtlasExecutor`, AST Guard, SSRF Bridge,
  process hardening, pending approval HMAC, Sentinel MCP adoption gate.
- Memory: system context, block memory, error registry, approved patterns,
  vector store hooks, distiller.
- Self-improvement: ColdUpdateManager, SelfAuditRunner, ADR-039
  self-maintenance scouts/proposers/adopter, ADR-040 decider/revert registry.
- Build-up layers (cores done, wiring deferred — see ROADMAP + `docs/backlog.md`):
  Layer 1 universal verifier (`core/verify.py`, ADR-041), Layer 2 cascade
  routing (`router/cascade.py`, ADR-042), Layer 3 swarm + worker backend
  (`core/swarm.py`, `core/swarm_backend.py`, `core/swarm_reconcile.py`,
  ADR-045/046), Layer 4 LessonStore (`core/lesson_store.py`, ADR-044).
  VerifiedProducer (ADR-048, núcleo A-F): `core/adversarial_panel.py`,
  `core/verified_producer.py`, `core/deterministic_producer.py`,
  `core/llm_producer.py`, `core/maintenance_scout.py`, `core/maintenance_worker.py`.
  Proposed: adversarial verification + grounding (ADR-047).
- Interfaces: CLI, dashboard/API, Telegram, voice, browser/editor tools.

Hermes is not assumed live. If `HERMES_BASE_URL` and `HERMES_API_KEY` are absent,
Atlas runs with the mock adapter or local takeover if configured.

## Non-Negotiable Rules

1. Every external effect must be Merkle-audited.
2. Generated Python code must pass AST Guard before execution.
3. `config/governance.json` is never modified by agents or runtime instructions.
4. `sensitivity="high"` forces human approval or denial in autonomous modes.
5. DEGRADED/OMEGA thermal modes must not load heavy local LLMs.
6. No new dependencies without explicit ADR or gate-level approval.
7. Tests must cover code changes before merge.
8. Before editing files, state the intended diff.
9. On completion, run relevant tests and summarize what is verified and what is
   still unknown.

## Naming Rules

Use technical names in code, comments, prompts, and instructions. Narrative
aliases belong only in human-facing historical docs.

| Use | Do not use in code |
| --- | --- |
| `SystemContextLoader` | `TrinityMemo` |
| `ErrorRegistry` | `FailureAtlas` |
| `ApprovedPatternStore` | `PatternLibrary` |
| `ProviderMetricsStore` | `PerformanceLedger` |
| `LayeredIsolationSandbox` | `MatrioskaSandbox` |
| `OperationalMode.NORMAL` | `TriageMode.ALFA` |
| `OperationalMode.DEGRADED` | `TriageMode.OMEGA` |
| `OfflineFallbackMode` | `ModoFantasma` |

## Key Commands

```bash
cd ~/proyectos/atlas-core
source .venv/bin/activate

PYTHONPATH=src python -m pytest tests/ -q
PYTHONPATH=src python -m pytest tests/ -q -m "computer_use"
MYPYPATH=src python -m mypy src/atlas/

PYTHONPATH=src atlas reality
PYTHONPATH=src atlas doctor
PYTHONPATH=src atlas health
PYTHONPATH=src atlas audit --verify
```

Live smokes require current secrets/network:

```bash
set -a && source .env && set +a
PYTHONPATH=src python scripts/inference_smoke.py
PYTHONPATH=src python scripts/hermes_smoke.py
PYTHONPATH=src python scripts/operational_smoke.py
```

## ADR Status Snapshot

Resolved/implemented: core gates A-I, observability, ColdUpdate, twin API/kanban
bridge, audit search, block memory, agentic tool loop, HITL suspend/resume,
subprocess hardening, MCP client, untrusted-content boundary, Sentinel adoption
gate, ADR-039 self-maintenance slices, ADR-040 decider/revert registry.

Still not absolute:

- live provider/service state depends on environment and smoke evidence;
- browser readiness depends on local Playwright browser installation;
- MCP server behavior is external and remains untrusted after adoption;
- seccomp/namespaces/VM isolation are not full local guarantees;
- autonomous codegen remains constrained by validation, reversibility, risk, and
  human approval policy.

## How To Resume

1. Activate the venv.
2. Load `.env` only if live smokes are needed.
3. Run `atlas reality --json`.
4. Read failing/degraded items before trusting docs.
5. Prefer small reversible changes with tests.
