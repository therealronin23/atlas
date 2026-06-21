# Atlas Max Capability Roadmap

## Premise

Atlas should become an expert programming and cybersecurity workbench. The goal
is not unlimited harm; it is unlimited legitimate capability under evidence,
containment, reproducibility, and disclosure discipline.

The target phrase is **maximum verified capability**:

- expert code understanding and generation;
- exploit-class bug discovery in owned or authorized targets;
- reproducible vulnerability research in isolated labs;
- defensive remediation and regression tests;
- responsible disclosure records;
- no hidden live claims and no unbounded execution.

## Pillar 1 — Expert Programming Engine

- Repository intelligence:
  - symbol graph, call graph, dependency graph, ownership map;
  - semantic search over code, tests, ADRs, audit records, failures;
  - stale-doc and stale-test detection.
- Software-liquid workflow:
  - intent -> design -> patch -> isolated validation -> review -> apply -> rollback;
  - automatic minimal diffs with explicit blast radius;
  - generated tests before generated implementation for risky changes;
  - multi-language adapters, starting with Python, TypeScript, shell, SQL.
- Quality gates:
  - unit, integration, typecheck, lint, mutation tests where available;
  - performance and memory regression checks for hot paths;
  - proof artifact attached to every generated patch.

## Pillar 2 — Defensive Cybersecurity Lab

- Static analysis:
  - taint tracking for file/network/process/secret flows;
  - unsafe deserialization, injection, SSRF, authz bypass, path traversal,
    command execution, crypto misuse, concurrency and TOCTOU checks;
  - dependency advisory ingestion with provenance and corroboration.
- Dynamic analysis:
  - fuzz harness generation for parsers, APIs, CLIs and protocol handlers;
  - sanitizer-friendly test runners where the language supports them;
  - crash triage: minimize input, classify impact, generate regression test.
- Authorized vulnerability research:
  - scoped target registry: owned repos, local labs, CTFs, bug-bounty scopes;
  - no scanning/exploitation outside explicit scope;
  - responsible disclosure packet: affected version, reproduction, impact,
    suggested fix, timeline.

## Pillar 3 — Containment

- Every research task declares:
  - target scope;
  - allowed techniques;
  - network boundaries;
  - data handling rules;
  - rollback or cleanup plan.
- High-risk techniques require HITL:
  - exploit development beyond proof-of-concept in a lab;
  - credential handling;
  - public target interaction;
  - destructive fuzzing;
  - malware-like behavior.
- Labs should be disposable:
  - temp worktree/container/VM;
  - no host secrets;
  - network denied by default;
  - artifacts retained only as evidence.

## Pillar 4 — Knowledge And Training

- Build a local curriculum from:
  - secure coding guides;
  - CWE/CVE examples;
  - exploit writeups converted into defensive patterns;
  - CTF/lab tasks;
  - Atlas's own postmortems.
- Every learned pattern must include:
  - detection heuristic;
  - false-positive notes;
  - safe reproduction;
  - patch pattern;
  - regression test.

## Pillar 5 — Operational Truth

- `atlas reality` remains the entrypoint for state.
- `atlas capabilities` remains the entrypoint for tool readiness.
- Atlas may not claim expertise from docs; it earns it via local evidence:
  - passing checks;
  - benchmark results;
  - solved lab tasks;
  - patches accepted;
  - vulnerabilities responsibly reported and fixed.

## Next Concrete Builds

1. `atlas capabilities --json` feeds dashboard/doctor.
2. `atlas security audit <path>`: read-only SAST pass with CWE-tagged findings.
3. `atlas fuzz plan <target>`: generate a harness plan, not execution.
4. `atlas lab create`: disposable local target sandbox.
5. `atlas disclosure draft`: responsible disclosure from verified evidence.

No item above needs a new dependency for the first MVP; deeper fuzzing/sanitizer
integrations can be proposed later via ADR.
