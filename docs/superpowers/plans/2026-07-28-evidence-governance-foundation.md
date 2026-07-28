# Evidence Governance Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make evidence-backed decision status a machine-validated, traceable
canon surface before changing durable runtime or product boundaries.

**Architecture:** The existing decision registry remains the unique disposition
index. Two additive JSONL registries record source evidence and the comparison
matrix; Markdown dossiers make the reasoning reviewable. `scripts/check_canon.py`
validates their links, authority boundaries, source independence and local path
evidence without a new dependency.

**Tech Stack:** Python 3.12 standard library, PyYAML already declared by Atlas,
JSON Schema draft 2020-12 artifacts, JSONL, pytest, existing canon integrity
gate and documentation-index audit.

## Global Constraints

- Do not modify `config/governance.json`.
- Do not add a Python dependency; validation remains standard-library/PyYAML.
- `decision_registry.jsonl` remains the sole decision-disposition authority.
- Repeated or derivative sources never count as independent corroboration.
- New records must use exactly one program `P00`–`P12`.
- `EVIDENCE_QUALIFIED` requires two independent source-tier 1–4 records and a
  non-empty falsifier/revisit condition; otherwise the matrix state is
  `PROVISIONAL`.
- Local evidence paths must be repository-relative, non-traversing and exist.
- Canon validation and `docs_index_audit.py --strict` must pass before commit.
- Update `WORK_LEDGER.md`, `MEMORY.md`, `docs/INDEX.yaml` and the design
  record in the same commit as the functional change.

---

## File Structure

- `schemas/evidence_source.schema.json`: interchange contract for one evidence
  source record.
- `schemas/decision_evidence.schema.json`: interchange contract for a decision
  comparison record.
- `docs/canon/evidence_registry.jsonl`: evidence source inventory, one record
  per independent source/observation.
- `docs/canon/decision_evidence_matrix.jsonl`: decision-to-alternatives-to-
  evidence links; does not supersede the decision registry.
- `docs/canon/decision_dossiers/*.md`: human-readable evidence packets for
  the first four active architecture boundaries.
- `docs/canon/authority_registry.yaml`: discovers the additive evidence
  registries and defines their non-authority role.
- `scripts/check_canon.py`: validates record shapes, cross-references,
  source-tier rules, paths and decision-state constraints.
- `tests/test_canon_integrity.py`: isolated-candidate behavioral tests for the
  new gate rules.
- `WORK_LEDGER.md`, `MEMORY.md`, `docs/INDEX.yaml`: live continuation and
  document discoverability.

### Task 1: Specify and seed the evidence registries

**Files:**
- Create: `schemas/evidence_source.schema.json`
- Create: `schemas/decision_evidence.schema.json`
- Create: `docs/canon/evidence_registry.jsonl`
- Create: `docs/canon/decision_evidence_matrix.jsonl`
- Modify: `docs/canon/authority_registry.yaml`
- Modify: `docs/canon/decision_registry.jsonl`

**Interfaces:**
- Produces `EvidenceSource` JSON objects with `id`, `program`, `kind`,
  `source_tier`, `locator`, `independence_key`, `retrieved_at`, `claim_scope`,
  `strength` and `status`.
- Produces `DecisionEvidence` JSON objects with `id`, `decision_id`, `program`,
  `state`, `alternatives`, `evidence_ids`, `recommendation`, `confidence`,
  `falsifiers`, `revisit_triggers`, `operator_decision_required` and `dossier`.
- Produces optional `evidence_qualification` on a decision-registry row;
  `PROVISIONAL` is the initial state for the four reassessed ADRs.

- [x] **Step 1: Add the failing isolated-candidate tests**

  Extend `JSONL_REGISTRIES` and `_make_candidate()` in
  `tests/test_canon_integrity.py` with valid minimal rows. Add these tests:

  ```python
  def test_evidence_matrix_rejects_unknown_evidence_id(tmp_path: Path) -> None:
      root = _make_candidate(tmp_path)
      matrix = root / "docs/canon/decision_evidence_matrix.jsonl"
      rows = [json.loads(line) for line in matrix.read_text().splitlines()]
      rows[0]["evidence_ids"] = ["EVD-NOT-REGISTERED"]
      _write_jsonl(matrix, rows)

      result = _run(root)

      assert result.returncode == 1
      assert "UNKNOWN_EVIDENCE_REFERENCE" in result.stdout
  ```

  ```python
  def test_evidence_qualified_requires_primary_or_local_evidence(tmp_path: Path) -> None:
      root = _make_candidate(tmp_path)
      matrix = root / "docs/canon/decision_evidence_matrix.jsonl"
      rows = [json.loads(line) for line in matrix.read_text().splitlines()]
      rows[0]["state"] = "EVIDENCE_QUALIFIED"
      _write_jsonl(matrix, rows)

      result = _run(root)

      assert result.returncode == 1
      assert "INSUFFICIENT_QUALIFYING_EVIDENCE" in result.stdout
  ```

- [x] **Step 2: Run the two tests to establish the missing contract**

  Run:

  ```bash
  PYTHONPATH=src python -m pytest tests/test_canon_integrity.py \
    -k 'evidence_matrix_rejects_unknown_evidence_id or evidence_qualified_requires_primary_or_local_evidence' -q
  ```

  Expected: FAIL because the current validator neither requires nor validates
  either registry.

- [x] **Step 3: Add the JSON Schema artifacts**

  Create `schemas/evidence_source.schema.json` with closed properties and the
  source kinds/tier mapping below:

  ```json
  {
    "kind": "LOCAL_RUNTIME",
    "source_tier": 1,
    "status": "ACTIVE",
    "strength": "HIGH"
  }
  ```

  Allowed kind/tier pairs are `LOCAL_CHECKOUT:1`, `LOCAL_RUNTIME:1`,
  `PRIMARY_STANDARD:2`, `OFFICIAL_DOCUMENTATION:3`, `RESEARCH_PAPER:4`,
  `INDEPENDENT_REPLICATION:5`, `ATLAS_MEASUREMENT:6`, `VENDOR_CLAIM:7`, and
  `ANALOGY:8`. Require non-empty `id`, `program`, `locator`,
  `independence_key`, `retrieved_at`, `claim_scope`, `strength` and `status`.

  Create `schemas/decision_evidence.schema.json` with closed properties,
  states `EVIDENCE_QUALIFIED`, `PROVISIONAL`, `EXPERIMENT`,
  `REQUIRES_OPERATOR`, `BLOCKED`, `REJECTED`, `SUPERSEDED`, and an
  `alternatives` array of at least two objects. Each alternative requires
  `id`, `label`, `disposition`, and `tradeoffs`.

- [x] **Step 4: Seed the current evidence inventory and matrix**

  Add source rows for the local ADR/code evidence and primary sources used in
  the approved design. Use the following four matrix rows, all initially
  `PROVISIONAL`:

  ```json
  {"id":"DEM-ADR-069-DURABLE-WORK","decision_id":"ADR-069","program":"P06"}
  {"id":"DEM-ADR-057-MEMORY-PROMOTION","decision_id":"ADR-057","program":"P04"}
  {"id":"DEM-ADR-058-CONTROL-PLANE","decision_id":"ADR-058","program":"P01"}
  {"id":"DEM-ADR-078-WORKBENCH-LINEAGE","decision_id":"ADR-078","program":"P08"}
  ```

  Each row includes the null alternative, one incremental alternative, its
  recommendation, at least one falsifier, at least one revisit trigger and a
  repository-relative dossier path. Set the corresponding decision rows'
  `evidence_qualification` to `PROVISIONAL`; do not alter their current ADR
  disposition.

- [x] **Step 5: Make evidence discovery explicit without creating a second authority**

  Add `evidence_sources`, `decision_evidence_matrix` and `decision_dossiers`
  to `registries` in `docs/canon/authority_registry.yaml`, plus a note that the
  decision registry retains disposition authority. Do not change candidate
  status or constitutional fields.

- [x] **Step 6: Leave the contract, seed and failing tests uncommitted until enforcement exists**

  The next task makes these tests pass and commits the whole vertical slice.
  This prevents a transient broken commit from entering the review history.

### Task 2: Enforce evidence integrity in the canon gate

**Files:**
- Modify: `scripts/check_canon.py`
- Modify: `tests/test_canon_integrity.py`

**Interfaces:**
- Consumes both new JSONL registries plus `decision_registry.jsonl`.
- Produces `Finding` codes `UNKNOWN_EVIDENCE_REFERENCE`,
  `UNKNOWN_DECISION_REFERENCE`, `INVALID_EVIDENCE_TIER`,
  `INVALID_EVIDENCE_PATH`, `INSUFFICIENT_QUALIFYING_EVIDENCE`,
  `MISSING_EVIDENCE_FALSIFIER`, `MISSING_EVIDENCE_REVISIT_TRIGGER`,
  `EVIDENCE_STATE_DRIFT` and `MISSING_EVIDENCE_DOSSIER`.

- [x] **Step 1: Add the remaining failing behavioral tests**

  Add tests that mutate the valid miniature candidate in exactly one way:

  ```python
  def test_matrix_rejects_decision_state_drift(tmp_path: Path) -> None:
      root = _make_candidate(tmp_path)
      registry = root / "docs/canon/decision_registry.jsonl"
      rows = [json.loads(line) for line in registry.read_text().splitlines()]
      next(row for row in rows if row["id"] == "ADR-001")["evidence_qualification"] = "REJECTED"
      _write_jsonl(registry, rows)
      result = _run(root)
      assert result.returncode == 1
      assert "EVIDENCE_STATE_DRIFT" in result.stdout
  ```

  ```python
  def test_local_evidence_path_must_exist_and_not_escape_root(tmp_path: Path) -> None:
      root = _make_candidate(tmp_path)
      registry = root / "docs/canon/evidence_registry.jsonl"
      rows = [json.loads(line) for line in registry.read_text().splitlines()]
      rows[0]["locator"] = "../secret"
      _write_jsonl(registry, rows)
      result = _run(root)
      assert result.returncode == 1
      assert "INVALID_EVIDENCE_PATH" in result.stdout
  ```

- [x] **Step 2: Run the new tests and verify they fail**

  Run:

  ```bash
  PYTHONPATH=src python -m pytest tests/test_canon_integrity.py \
    -k 'matrix_rejects_decision_state_drift or local_evidence_path_must_exist' -q
  ```

  Expected: FAIL because no evidence-specific checks exist.

- [x] **Step 3: Extend `scripts/check_canon.py` with exact registry and state rules**

  Add the two files to `JSONL_REGISTRIES`. Define the allowed source kinds,
  expected tiers and matrix states as constants. Implement:

  ```python
  def _validate_evidence_sources(
      root: Path, rows: list[dict[str, Any]], findings: list[Finding]
  ) -> dict[str, dict[str, Any]]: ...

  def _validate_decision_evidence_matrix(
      root: Path,
      rows: list[dict[str, Any]],
      sources: dict[str, dict[str, Any]],
      decisions: list[dict[str, Any]],
      findings: list[Finding],
  ) -> None: ...
  ```

  Rules:

  - `LOCAL_CHECKOUT`, `LOCAL_RUNTIME` and `ATLAS_MEASUREMENT` locators are
    validated as safe, existing paths under the candidate root; URL locators
    are allowed for other kinds but must use `https://`.
  - Every matrix decision id must exist in `decision_registry.jsonl`.
  - Every `evidence_id` must resolve; two IDs with the same
    `independence_key` count as one corroborating source.
  - A `PROVISIONAL` row needs at least two alternatives, a non-empty
    recommendation, falsifier, revisit trigger and dossier file.
  - `EVIDENCE_QUALIFIED` also needs at least two independent tier 1–4 sources.
  - If a decision row has `evidence_qualification`, it must equal the matrix
    state for that `decision_id`; a decision referenced by the matrix must have
    the field.

- [x] **Step 4: Run the evidence tests and the entire integrity test module**

  Run:

  ```bash
  PYTHONPATH=src python -m pytest tests/test_canon_integrity.py -q
  PYTHONPATH=src python scripts/check_canon.py
  ```

  Expected: all tests pass and the real candidate reports `canon integrity:
  PASS`.


- [x] **Step 5: Keep the validated contract uncommitted until dossiers make the real candidate valid**

  The dossier files are mandatory runtime inputs of `check_canon.py`. The
  commit occurs in Task 3 so a clean checkout never contains a broken matrix.

### Task 3: Publish the first four dossiers and continuation state

**Files:**
- Create: `docs/canon/decision_dossiers/EDR-ADR-057-memory-promotion.md`
- Create: `docs/canon/decision_dossiers/EDR-ADR-058-control-plane.md`
- Create: `docs/canon/decision_dossiers/EDR-ADR-069-durable-work.md`
- Create: `docs/canon/decision_dossiers/EDR-ADR-078-workbench-lineage.md`
- Modify: `WORK_LEDGER.md`
- Modify: `MEMORY.md`
- Modify: `docs/INDEX.yaml`
- Modify: `tests/test_os_event_schema.py`

**Interfaces:**
- Each dossier matches its matrix `dossier` path and contains: question,
  constitutional constraints, observed local evidence, alternatives,
  comparison limits, recommendation, confidence, falsifiers, revisit triggers,
  security/license/rollback effect and linked evidence IDs.

- [x] **Step 1: Write the four dossiers from the seeded matrix records**

  Use a consistent short structure. For example, `EDR-ADR-058-control-plane.md`
  must state that current mutating 7341 routes are contradictory evidence,
  distinguish a logical command plane from a compulsory second TCP port, and
  list local IPC plus authenticated command admission as the recommended
  incremental alternative. It must not claim the route migration is complete.

- [x] **Step 2: Add a ledger entry and a durable lesson**

  Add one top-level `WORK_LEDGER.md` entry naming the evidence foundation,
  its commit series and the next work order: P00/P01/P09 review before
  Mission/Task implementation. Add `evidence-before-operator-choice` to
  `MEMORY.md`: the operator decides constitutional intent; technical means
  require comparison, local verification and falsifiers.

- [x] **Step 3: Regenerate and validate the documentation index**

  Run:

  ```bash
  PYTHONPATH=src python scripts/docs_index_audit.py --write
  PYTHONPATH=src python scripts/docs_index_audit.py --strict
  ```

  Expected: every dossier and the design/plan document is indexed, with no
  missing or orphaned document entry.

- [x] **Step 4: Run the full applicable validation set**

  Run:

  ```bash
  PYTHONPATH=src python -m pytest tests/test_canon_integrity.py -q
  PYTHONPATH=src python -m pytest tests/test_os_event_schema.py -q
  PYTHONPATH=src python scripts/check_canon.py
  PYTHONPATH=src python scripts/docs_index_audit.py --strict
  MYPYPATH=src python -m mypy src/atlas/
  ```

  Classify any failure before changing unrelated code.

- [x] **Step 5: Commit the complete validated vertical slice**

  ```bash
  git add AGENTS.md MEMORY.md WORK_LEDGER.md feedback-evidence-before-operator-choice.md \
    docs/INDEX.yaml docs/architecture/DECISION_REVIEW.md \
    docs/canon/authority_registry.yaml docs/canon/decision_registry.jsonl \
    docs/canon/evidence_registry.jsonl docs/canon/decision_evidence_matrix.jsonl \
    docs/canon/decision_dossiers schemas/evidence_source.schema.json \
    schemas/decision_evidence.schema.json scripts/check_canon.py \
    tests/test_canon_integrity.py tests/test_os_event_schema.py \
    docs/superpowers/plans/2026-07-28-evidence-governance-foundation.md
  git commit -m "feat(canon): enforce evidence traceability"
  ```

### Task 4: Make optional protocol test collection capability-aware

**Files:**
- Modify: `tests/test_acp_server.py`
- Modify: `tests/test_graph_server_communities.py`

The `acp` and `mcp` extras are deliberately optional in `pyproject.toml`, while
CI installs both extras for protocol coverage. The local default environment
must therefore skip only the protocol-dependent tests when those extras are
absent, rather than report a false product regression. Core ACP helper tests
remain runnable without the extra.

- [x] **Step 1: Reproduce and classify the failure**

  `tests/test_acp_server.py` fails only on methods importing `acp`; graph
  community tests fail only at the lazy `mcp.server.fastmcp` import. Both
  packages are absent locally and are declared optional dependencies, while the
  CI workflow installs `--extra mcp --extra acp`.

- [x] **Step 2: Add narrow skip guards**

  Mark only ACP schema-response test classes as requiring `acp`; mark graph
  community tests as requiring `mcp`. Do not skip pure helpers that do not load
  the optional packages.

- [x] **Step 3: Verify local behavior**

  Run:

  ```bash
  PYTHONPATH=src python -m pytest tests/test_acp_server.py -q
  PYTHONPATH=src python -m pytest tests/test_graph_server_communities.py -q
  ```

  Expected: the five dependency-free ACP tests pass, protocol-dependent tests
  are reported as skipped locally, and CI continues to exercise them with its
  declared extras.

- [x] **Step 4: Commit the validation repair**

  ```bash
  git add tests/test_acp_server.py tests/test_graph_server_communities.py
  git commit -m "test(validation): honor optional protocol extras"
  ```

### Task 5: Close optional-adapter type-safety debt

**Files:**
- Modify: `src/atlas/tools/image_gen_tool.py`
- Modify: `src/atlas/tools/video_gen_tool.py`
- Modify: `src/atlas/acp/server.py`
- Modify: `tests/test_image_gen_tool.py`
- Modify: `tests/test_video_gen_tool.py`
- Modify: `tests/test_acp_server.py`

- [x] **Step 1: Reproduce the strict-type failures**

  The first `mypy src/atlas/` run found two unchecked `fal_client.subscribe`
  returns and one optional ACP base-class `Any` error. These are adapter-boundary
  gaps, not an invitation to install optional dependencies.

- [x] **Step 2: Add red malformed-payload regressions**

  Fake `fal_client` modules returning lists must raise `TypeError` at the
  adapter. The ACP test proves `make_agent_class()` binds the SDK base only
  after a runtime import.

- [x] **Step 3: Normalize provider data and make the ACP binding dynamic**

  Both media adapters copy only `Mapping` payloads whose keys are strings. The
  ACP factory uses runtime `type(...)` construction so importing the optional
  package does not introduce a static `Any` base class.

- [x] **Step 4: Verify focused tests and the complete type gate**

  ```bash
  PYTHONPATH=src python -m pytest tests/test_image_gen_tool.py \
    tests/test_video_gen_tool.py tests/test_acp_server.py -q
  MYPYPATH=src python -m mypy src/atlas/
  ```

  Result: `23 passed, 7 skipped`; `Success: no issues found in 318 source files`.

- [x] **Step 5: Commit the isolated work order**

  ```bash
  git commit -m "fix(adapters): close optional SDK type gaps"
  ```

### Task 6: Enforce operator-decision work-order eligibility

**Files:**
- Modify: `scripts/check_canon.py`
- Modify: `tests/test_canon_integrity.py`
- Modify: `docs/canon/implementation_registry.yaml`

- [x] **Step 1: Audit the P00/P01/P09 continuation boundary**

  P01 has no safe ownership migration before the reserved Mission/Task and
  7341 decisions. P00 did have a runnable gap: the gate validated work-order
  syntax but not whether a decision-gated work item was executable.

- [x] **Step 2: Add red relationship tests**

  A decision-required `READY` work order, a `REQUIRES_OPERATOR` item without
  its explicit flag, an unknown blocker, and an incompatible blocker linkage
  must all fail the real validator on a miniature candidate.

- [x] **Step 3: Implement cross-registry eligibility checks**

  The implementation validator now returns its registered work-order map;
  operator questions resolve against it. The gate rejects untracked execution
  eligibility and reports a stable actionable finding code.

- [x] **Step 4: Remove focal static-type debt in the validator**

  Mypy revealed three existing narrowing defects in `check_canon.py`; the
  same slice now makes the script type-clean without changing validation
  semantics.

- [x] **Step 5: Verify and commit the governance enforcement slice**

  ```bash
  PYTHONPATH=src python -m pytest tests/test_canon_integrity.py -q
  PYTHONPATH=src python scripts/check_canon.py
  MYPYPATH=src python -m mypy scripts/check_canon.py
  git commit -m "feat(canon): gate operator decision work orders"
  ```

## Plan Self-Review

- Spec coverage: sections 4–8 and 11–12 are implemented by Tasks 1–3. The
  P00–P12 substantive reassessment is deliberately deferred to separate plans,
  as required by section 10 of the approved design.
- Scope: this plan does not change runtime boundaries, add dependencies or
  promote any provisional decision; it only makes those later changes
  evidence-gated.
- Consistency: `evidence_qualification` appears only as a decision-registry
  annotation and is cross-checked against `DecisionEvidence.state`; decision
  disposition remains unchanged.
- Placeholder scan: no unresolved implementation markers are used.
