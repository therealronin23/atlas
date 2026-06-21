# ATLAS CORE — Operating Context For Agents

This file is operational context, not marketing copy. If it conflicts with live
evidence, live evidence wins.

## OPERATING LOOP (read this first, every task — it's the forcing function)

Lightweight pre-flight. Glance, don't deliberate — no MCP/API fan-out to "decide".

**Matrioska (structure of all work):** `Gate → ADR → Fase → Tipo`. Every task declares
its node. **Tipo** of debt/work: **1** = build-on-top (defer OK) · **2** =
foundational/correctness (fix BEFORE stacking) · **3** = wall/real limit (work around
or accept, not a "task"). Order: tipo-2 first, tipo-1 by dependency, tipo-3 apart.

**Live state lives in `WORK_LEDGER.md`** (the "where are we"), never only in chat. Read
it on resume; update it when you open/close a node. Compaction must lose nothing because
state = ledger + design-doc checklists + memory, not the transcript.

**5 pre-flight questions (cheap, static):**
1. Which matrioska node am I in? (record in `WORK_LEDGER.md`)
2. Is there a **skill** for this? (see `.claude/skills/.../skills/`: `planning-and-task-breakdown`,
   `test-driven-development`, `incremental-implementation`, `debugging-and-error-recovery`,
   `code-review-and-quality`, `security-and-hardening`, `documentation-and-adrs`,
   `code-simplification`, `spec-driven-development`). Invoke via the Skill tool.
3. Design/plan/audit/decide → **Opus (me)**. Picar código → **delegate**: substantial →
   Sonnet, trivial → Haiku, multi-step build → `/autobuild`. Default: delegate the typing.
4. Which **tipo** (1/2/3)? It sets the order.
5. Am I registering this in ledger + design doc + memory — **not only in chat**?

**Standing manías (canonical "how"; auto-memory `feedback-*.md`, obey them):**
`plan-then-execute` · `decide-with-facts` · `honesty-over-sycophancy` ·
`convergence-discipline-verification` · `debt-closure-workflow` · `roadmap-is-guide-not-law` ·
`stdlib-over-new-deps` · `no-aux-scripts-bloat` · `no-cli-against-live-workspace` ·
`no-gui-in-tests` · `no-deepen-hitl-coupling` · `no-security-lectures-local` ·
`arxiv-citation-verification`.

**This loop self-evolves:** when the user states a recurring preference or a workflow
improvement → (a) write/update a `feedback-*.md` memory with Why + How-to-apply, (b) add a
one-liner to `MEMORY.md`, (c) add its name to the manías line above. New manías join the
forcing function automatically.

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
- Self-improvement: ColdUpdateManager, SelfAuditRunner (24h loop; runs IN-process
  via `ATLAS_SELF_AUDIT_SCHEDULER=1` — single Merkle writer, not the CLI one-shot
  which would be a second writer), ADR-039 self-maintenance
  scouts/proposers/adopter, ADR-040 decider/revert registry.
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

## Current Direction (2026-06)

Active line beyond the Atlas runtime: a verifiable AI compliance gateway
(ADR-051/053/054). The public-facing calling card is a design paper —
`docs/paper_subject_enforced_completeness.md` ("Subject-Enforced Completeness for AI
Inspection Logs") — plus a demo. The *in-path verifiable AI compliance filter* (alias
Osmosis) and its candidate mechanisms live in the osmosis membrane:
`docs/membrana/` (OSM-000 manifest + registry OSM-001..039). Public artifacts speak about
the filter, not Atlas. The May Gates (`docs/gate_*`) are historical; the project pivoted.

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

Vocabulario nuevo (compliance/transparency, 2026-06). Glosario y autoridad de nombres:
`docs/membrana/OSM-000_membrana.md`.

| Use (técnico) | Alias narrativo (solo docs humanos) |
| --- | --- |
| `in-path verifiable AI compliance filter` | Osmosis / Filtro Osmosis |
| `admission gate` | membrane / membrana |
| `adaptive defense layer` | antivirus inmune (evitar) |
| `external knowledge ingestion & verification pipeline` | organismo de conocimiento |
| `defense-pattern mutation & selection` | afinidad maduración |
| `decision/action provenance record` | (NO "chain-of-thought auditable") |

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

## Runtime Dependency: bubblewrap (bwrap)

Code execution via `LayeredIsolationSandbox.execute_in_jail()` requires
[bubblewrap](https://github.com/containers/bubblewrap) (ADR-055).

Install:
```bash
# Debian/Ubuntu
sudo apt-get install bubblewrap

# Fedora/RHEL
sudo dnf install bubblewrap

# Arch
sudo pacman -S bubblewrap
```

Without `bwrap` in PATH, Python code execution is **fail-closed**
(`BwrapUnavailableError`). All other Atlas functionality is unaffected.

Requirements:
- Kernel ≥ 3.8 with unprivileged user namespaces enabled
  (`/proc/sys/kernel/unprivileged_userns_clone` = 1 on Ubuntu/Debian)
- Not required for test suite — `BwrapJail` tests mock subprocess calls

Jail properties enforced (Slice 1):
- uid/gid 65534 (nobody) via user namespace
- Network namespace — no external network access
- `/` bind-mounted read-only; `/tmp` ephemeral tmpfs
- `--die-with-parent` — child dies if parent exits

Slice 2 (seccomp-bpf allowlist) deferred — requires `libseccomp` (external dep,
against project rules). The uid/net namespace isolation is the primary containment.

## ADR Status Snapshot

Resolved/implemented: core gates A-I, observability, ColdUpdate, twin API/kanban
bridge, audit search, block memory, agentic tool loop, HITL suspend/resume,
subprocess hardening, MCP client, untrusted-content boundary, Sentinel adoption
gate, ADR-039 self-maintenance slices, ADR-040 decider/revert registry,
ADR-053 TransparencyGateway, ADR-055 BwrapJail Slice 1.

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
