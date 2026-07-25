# Multisource Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Feed trustworthy non-GitHub reference material into Atlas research while retaining candidate admission and installation gates.

**Architecture:** A manifest declares exact publisher domains and curated sources. A pure loader validates that schema, optionally fetches bounded text only after SSRF approval, and emits research findings. Existing digest, quality gate, vetting, trial and HITL transitions remain the sole path to an executable adoption.

**Tech Stack:** Python 3.12, stdlib HTML parsing, PyYAML, SSRFBridge, pytest.

## Global Constraints

- No new dependency, execution, install, wildcard domain, or private-network egress.
- The loader must fail closed per source; malformed data and denied/failing fetches yield no finding.
- `official` findings are knowledge material, not direct catalog candidates.
- ADR-076 high-sensitivity adoption remains unchanged.

### Task 1: Manifest validation and bounded official-source extraction

**Files:**
- Modify: `src/atlas/core/self_maintenance/curated_sources.py`
- Test: `tests/test_curated_sources.py`

**Interfaces:** `load_curated_findings(path, *, bridge=None, fetch=None) -> list[PanoramaFinding]` accepts legacy GitHub sources plus manifest publishers/sources. A source must use HTTPS and a publisher-declared exact domain. With `bridge` and `fetch`, a source emits cleaned text capped at the existing finding excerpt limit.

- [x] Write tests for an accepted publisher source, an undeclared host, a denied bridge, and markup removal.
- [x] Run the new tests and confirm each fails against the GitHub-only loader.
- [x] Implement the smallest schema parser, exact host validation, bounded text extraction, and per-source fail-closed handling.
- [x] Run `tests/test_curated_sources.py` green.

### Task 2: Wire research to the guarded source loader

**Files:**
- Modify: `src/atlas/core/orchestrator_parts/maintenance_facade.py`
- Test: `tests/test_maintenance_research_tick.py`

**Interfaces:** `maintenance_research_tick()` passes its existing SSRF bridge and egress fetcher into Task 1; a denied source does not prevent open discovery or other sources.

- [x] Write an integration test proving a curated official finding reaches the report through injected collaborators.
- [x] Confirm the test fails because the facade does not pass collaborators.
- [x] Add the two keyword arguments only; preserve cadence and return shape.
- [x] Run the tick test file green.

### Task 3: Curate the broad initial source catalogue

**Files:**
- Modify: `docs/knowledge/curated_sources.yaml`
- Test: `tests/test_curated_sources.py`

**Interfaces:** The manifest declares official protocol, AI-provider, cloud, developer-platform, package, security, and research publishers. Individual source records specify their role and topic; all non-GitHub records remain `official` research material.

- [x] Add a test that every checked-in entry validates without fetching.
- [x] Populate the versioned publisher/source manifest using only exact official URLs.
- [x] Run source tests green.

### Task 4: Operational truth and release verification

**Files:**
- Modify: `WORK_LEDGER.md`
- Modify: `docs/design/atlas_ecosystem_map.md` only if the existing taxonomy lacks the source-ingestion boundary.
- Test: targeted tests from Tasks 1-3, mypy on changed Python modules.

- [x] Record the separation between material ingestion, candidate admission and activation.
- [x] Run targeted tests and mypy; run `atlas reality --json` after integrating into the live checkout.
- [ ] Commit the isolated change; integrate only after the diff is reviewed.
