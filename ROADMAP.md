# ATLAS — Roadmap

This roadmap tracks direction. It does not duplicate live test counts or service
claims. Run `atlas reality` for current facts.

## Current Direction

Atlas is moving toward maximum verified capability, not unchecked autonomy.
The build-up order (universal verifier → model-routing cascade → governed
swarm → LessonStore) and its principles live in
`docs/design/direction_2026-06-12_construir_hacia_arriba.md`.

The target is a runtime that can:

- observe its real local state;
- expose unknown/degraded subsystems honestly;
- execute through typed, audited capabilities;
- quarantine untrusted content;
- propose and validate improvements in isolated worktrees;
- autonomously apply only low-risk, reversible, validated changes;
- require human approval or denial for high-risk, credential, governance,
  destructive, network-expanding, or irreversible actions.

## Closed Foundations

- Gates A-I: local core, Hermes contracts, inference pipeline, dashboard/voice,
  computer-use, operational service runner, health endpoints.
- ADR-024/025: observability and ColdUpdate/SelfAudit.
- ADR-026..029: twin architecture, exec API, kanban bridge, audit search and
  reverse audit.
- ADR-030..033: block memory and agentic tool loop with suspend/resume HITL.
- ADR-034..038: process hardening, MCP client, threat model, untrusted boundary,
  Sentinel adoption gate.
- ADR-039: self-maintenance pipeline with scouts, analyst, proposers, adopter,
  scheduler integration.
- ADR-040: central decider, autonomous/hybrid modes, reversible action registry,
  `revert(action_hash)`.

## Build-Up Layers (cores done, wiring deferred)

The "construir hacia arriba" direction, layer by layer. Each core is a verified,
additive library; operational wiring is tracked in `docs/design/backlog.md`.

- **Layer 1 — Universal verifier** (ADR-041): `verify(artifact) -> Evidence`,
  asymmetric rule (nothing rises without a cheaper verifier; else `UNKNOWN`).
- **Layer 2 — Cascade routing** (ADR-042): cheapest capable producer, escalate
  on FAIL/UNKNOWN, `CostLedger` (cost per verified result). Production entry
  point is Layer 3 (no autonomous `cascade.route` until then).
- **Layer 3 — Swarm on blackboard** (ADR-045/046): workers coordinated by
  verifiable artifacts; `Envelope` policies; sole-writer coordinator; worker
  backend (disposable git worktrees, pure producers, env-hijack-safe);
  reconciliation to ColdUpdate (`origin="swarm"`, auto-apply starts OFF).
- **Layer 4 — LessonStore** (ADR-044): typed verified lessons (detection +
  avoid-pattern + Evidence); entry law: no Evidence PASS, no lesson.
- **Proposed — Adversarial verification + grounding** (ADR-047):
  devil's-advocate panel for irreversible actions, domain knowledge base,
  human-verifier assistance. Horizontal; serves every vertical.

Next concrete step: a real `produce_diff`/`validate` for the first maintenance
worker (Layer 3 becomes runnable). Designed carefully — it is execution on the
live repo.

## Active Priorities

1. **Reality Kernel**
   - `atlas reality` is the source of truth for version, git state, readiness,
     docs freshness, Hermes/LLM/MCP/browser status, and optional live checks.
   - Docs must not hand-maintain test counts.

2. **Security Closure**
   - Command execution and generated-code execution must share subprocess
     hardening.
   - MCP stdio servers must start in isolated sessions with bounded env and
     child hardening.

3. **Computer-Use Evidence**
   - Browser readiness must be proven by local Playwright installation and tests
     or reported degraded.
   - CI should not silently accept broken computer-use once the environment is
     stable.

4. **Capability Plane**
   - Surface tool readiness as ready/degraded/unavailable.
   - Mark tools read-only/mutating, reversible/irreversible, trusted/untrusted,
     live/stub.
   - First surface: `atlas capabilities`.

5. **Strict Readiness**
   - Add a strict doctor/reality gate that fails on Merkle corruption, stale
     docs, failed core/mypy checks, or required degraded capabilities.

6. **Postmortem Discipline**
   - Every major audit records false beliefs, verified facts, root causes,
     fixes, and residual risk.

7. **Runtime Process Guard**
   - Single-writer enforcement for the live Merkle chain: any Atlas CLI entry
     that would write audit records must detect an existing writer
     (`atlas serve`, self-audit loop) on the same `ATLAS_HOME` and refuse,
     instead of relying on operator discipline.
   - Lock file or pidfile under `memory/audit/`; `--force` only with explicit
     acknowledgement. Origin: 2026-06-12, an unisolated 24h self-audit loop ran
     for 15 cycles against the live chain alongside `atlas serve` (chain
     verified intact afterwards, but only by luck).

8. **Defensive Security Expertise**
   - First surface: `atlas security-audit <path>` for dependency-free Python
     static checks.
   - Next: scoped lab creation, fuzz harness planning, crash triage, and
     responsible disclosure drafts.

## Deferred Or Conditional

- Hermes live operation: only when a host is configured and smoked.
- Full VM/seccomp isolation: requires explicit infra/dependency decision.
- Wider autonomous apply: only after stronger rollback, blast-radius controls,
  and empirical validation.
- External MCP/tool adoption: always untrusted, fail-closed, and reversible where
  possible.
