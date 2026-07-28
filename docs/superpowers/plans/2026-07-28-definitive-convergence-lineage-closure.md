# Atlas Definitive Convergence — Lineage Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the current `ATLAS DEFINITIVE CANDIDATE` by reconciling every live product lineage, fixing the verified Sentinel and Merkle regressions, aligning canon/code/tests with the operator-approved Atlas Workbench direction, and producing a fully validated local delivery without modifying the preserved checkout or merging to `main`.

**Architecture:** This is **Cut 0: definitive candidate and lineage closure**. `atlas-core` remains the canonical integration target. Existing CodeOSS/VSCodium, Void, Zed, Doc0, and self-build repositories or worktrees are treated as evidence-bearing lineages, not as repositories to merge wholesale. Already integrated capabilities are retained in place; missing product work is represented by an accepted Workbench boundary and deferred to a separately planned cut. The browser shell remains a validation harness. No full editor-source transplant occurs in this cut.

**Tech Stack:** Python 3.12, pytest, mypy, JSONL/YAML canon registries, Git worktrees/bundles, React/Vite/TypeScript, npm, existing Atlas CLI/runtime checks.

## Global Constraints

- Approved design: `docs/superpowers/specs/2026-07-28-atlas-lineage-workbench-symbiosis-design.md`.
- Work only in `/home/ronin/proyectos/atlas-definitive-convergence` on `codex/atlas-definitive-convergence-20260727-154020`.
- Preserve `/home/ronin/proyectos/atlas-core`, its dirty files, all existing branches/worktrees, and `/home/ronin/proyectos/atlas-definitive-backup`.
- Never modify `config/governance.json`, push, open a PR, merge to `main`, rewrite history, run `git clean`, or use `git reset --hard`.
- Reuse, move, port, wrap, or connect existing implementation. Do not rewrite an existing capability merely to make it look native.
- Do not vendor the complete CodeOSS, VSCodium, Void, or Zed trees in Cut 0.
- Do not claim `LIVE_VERIFIED` without a fresh successful runtime check.
- Keep ADR-076 C rejected, Wave 5 conditional, remote executable MCP auto-adoption blocked, and high-sensitivity effects human-controlled or denied.
- Every code change is test-first and each cohesive work order lands in an atomic local commit.

---

### Task 1: Reconcile the preserved operator working tree

**Files:**
- Modify: `docs/canon/source_registry.jsonl`
- Modify: `docs/INDEX.yaml`
- Add: `docs/knowledge/research_2026-07-28.md`
- Modify: `work/canon-compiler/delivery/SOURCE_TRACEABILITY.jsonl`
- Modify: `work/canon-compiler/delivery/DEFERRED_ITEMS.md`
- Modify: `docs/canon/implementation_registry.yaml`

**Interfaces:**
- Each dirty source receives one disposition: `IMPORTED`, `REGENERATED_CANONICALLY`, `DEFERRED_UNVERIFIED`, or `PRESERVED_ONLY`.
- Research documents remain `RESEARCH`; they never become implementation or runtime evidence by import alone.

- [ ] **Step 1: Capture immutable comparisons**

Run:

```bash
git -C /home/ronin/proyectos/atlas-core status --short --branch
git -C /home/ronin/proyectos/atlas-core diff -- docs/INDEX.yaml docs/design/mcp_catalog_classified.yaml docs/design/mcp_catalog_stage1_triage.jsonl docs/design/mcp_catalog_stage2_report.jsonl
sha256sum /home/ronin/proyectos/atlas-core/docs/knowledge/research_2026-07-2{5_inbox,6,7,8}.md
```

Expected: the original checkout remains dirty but unchanged; all nine dirty paths are accounted for.

- [ ] **Step 2: Import the missing research source**

Use `apply_patch` to add the exact text of `research_2026-07-28.md` to the candidate. Do not copy the ZIP or generated stage reports into tracked source.

- [ ] **Step 3: Record dispositions**

Record:

- four research documents: `IMPORTED`, authority `RESEARCH`;
- `docs/INDEX.yaml`: `REGENERATED_CANONICALLY`;
- classified MCP catalog: `IMPORTED_SELECTIVELY`, with installed-state claims accepted only when locally verified;
- stage 1/stage 2 reports: `DEFERRED_UNVERIFIED`;
- R2.1 ZIP: `PRESERVED_ONLY`, identified by SHA-256, never copied into Git.

Mark `ADC-WO-001` `DONE` only after every dirty path is represented.

- [ ] **Step 4: Validate**

Run:

```bash
PYTHONPATH=src python scripts/check_canon.py
PYTHONPATH=src python -m pytest tests/test_canon_integrity.py -q
python scripts/docs_index_audit.py --strict
git -C /home/ronin/proyectos/atlas-core status --short --branch
```

Expected: canon and index checks pass; original status is byte-for-byte unchanged.

- [ ] **Step 5: Commit**

```bash
git add docs/knowledge/research_2026-07-28.md docs/INDEX.yaml docs/canon/source_registry.jsonl docs/canon/implementation_registry.yaml work/canon-compiler/delivery/SOURCE_TRACEABILITY.jsonl work/canon-compiler/delivery/DEFERRED_ITEMS.md
git commit -m "canon(sources): reconcile live operator evidence"
```

---

### Task 2: Repair the governed native-command Sentinel regression

**Files:**
- Modify: `src/atlas/security/sentinel_gate.py`
- Modify: `tests/test_sentinel_gate.py`

**Interfaces:**
- `SentinelGate._is_governed_native_command(cmd)` accepts:
  - `python -m <module>` only when the module is in `_ATLAS_NATIVE_MCP_MODULES`;
  - the tracked `tests/fixtures/mcp_echo_server.py` smoke fixture with the normal two-token argv `[python, script]`.
- Every other Python script and every unmeasured third-party executable stays quarantined.

- [ ] **Step 1: Add focused failing tests**

Add direct tests for:

```python
assert gate.vet_command(
    _cfg(cmd=[sys.executable, str(FIXTURE)])
) is None
assert gate.vet_command(
    _cfg(cmd=[sys.executable, "/tmp/mcp_echo_server.py"])
) is not None
```

- [ ] **Step 2: Prove the regression**

Run:

```bash
PYTHONPATH=src python -m pytest tests/test_sentinel_gate.py -k "governed_echo or registry_with_sentinel" -q
```

Expected before the fix: the tracked two-token fixture is rejected and the registry E2E test fails.

- [ ] **Step 3: Implement the minimal argv fix**

Change `_is_governed_native_command` so Python script inspection requires `len(cmd) >= 2`, while the `-m` branch separately requires `len(cmd) >= 3`. Preserve the exact tracked-fixture suffix check and the native-module allowlist.

- [ ] **Step 4: Validate the security boundary**

Run:

```bash
PYTHONPATH=src python -m pytest tests/test_sentinel_gate.py tests/test_sentinel_revet_tick.py tests/test_mcp_registry_lazy.py -q
MYPYPATH=src python -m mypy src/atlas/security/sentinel_gate.py
```

Expected: all focused tests pass; `npx`, arbitrary scripts, ambiguous identifiers, shell evaluation, IOC commands, drift, and corrupt snapshots remain fail-closed.

- [ ] **Step 5: Commit**

```bash
git add src/atlas/security/sentinel_gate.py tests/test_sentinel_gate.py
git commit -m "fix(sentinel): admit tracked native smoke fixture"
```

---

### Task 3: Correct the Merkle callback contract and audit MCP spawn before effect

**Files:**
- Modify: `src/atlas/mcp/registry.py`
- Modify: `tests/test_mcp_registry_lazy.py`
- Modify: `tests/test_trunk_timeout_and_extras.py`

**Interfaces:**
- `McpRegistry(..., merkle_log: Callable[..., Any] | None)` accepts `MerkleLogger.log`, whose return value is intentionally ignored.
- With a configured logger, `_start_one` emits `mcp.server_start_requested` before invoking the transport factory.
- If that configured pre-spawn audit raises, the server is not spawned and `start_all()` leaves it unavailable. Omitting a logger remains supported for isolated harnesses and existing tests.

- [ ] **Step 1: Add failing ordering and failure tests**

Use a fake logger and fake factory that append to one list:

```python
events: list[str] = []

def audit(**kwargs: object) -> object:
    events.append(str(kwargs["action"]))
    return object()

def factory(cfg: McpServerConfig) -> _FakeTransport:
    events.append("spawn")
    return _FakeTransport(cfg.name, ["tool"])
```

Assert `events.index("mcp.server_start_requested") < events.index("spawn")`. Add a second test whose logger raises on `mcp.server_start_requested`; assert the factory was never called.

- [ ] **Step 2: Prove the gaps**

Run:

```bash
PYTHONPATH=src python -m pytest tests/test_mcp_registry_lazy.py -k "start_requested or audit_failure" -q
MYPYPATH=src python -m mypy src/atlas/mcp/registry.py src/atlas/mcp/trunk_server.py
```

Expected before the fix: ordering tests fail and mypy reports the `MerkleLogger.log` return-type mismatch at `trunk_server.py`.

- [ ] **Step 3: Implement the narrow contract**

Widen only the callback return annotation to `Any`. Add a private required pre-spawn audit helper that distinguishes “no logger configured” from “configured logger failed”; call it immediately before `self._factory(cfg)`. Keep ordinary result logging best-effort.

- [ ] **Step 4: Validate**

Run:

```bash
PYTHONPATH=src python -m pytest tests/test_mcp_registry_lazy.py tests/test_trunk_timeout_and_extras.py tests/test_sentinel_gate.py -q
MYPYPATH=src python -m mypy src/atlas/mcp/registry.py src/atlas/mcp/trunk_server.py
```

Expected: all tests and focused mypy pass; no process is created after a configured pre-spawn audit failure.

- [ ] **Step 5: Commit**

```bash
git add src/atlas/mcp/registry.py tests/test_mcp_registry_lazy.py tests/test_trunk_timeout_and_extras.py
git commit -m "fix(mcp): enforce auditable pre-spawn boundary"
```

---

### Task 4: Establish the product-lineage authority

**Files:**
- Add: `docs/canon/product_lineage_registry.jsonl`
- Modify: `docs/canon/authority_registry.yaml`
- Modify: `scripts/check_canon.py`
- Modify: `tests/test_canon_integrity.py`

**Interfaces:**
- One JSON object per line with required keys:
  `id`, `name`, `kind`, `path_hint`, `branch`, `head`, `upstream`, `authority`, `capabilities`, `disposition`, `target_cut`, `evidence`.
- Allowed dispositions:
  `CANONICAL_TARGET`, `ALREADY_INTEGRATED`, `PORT_SOURCE`, `HOST_BASELINE`, `PATTERN_DONOR`, `RESEARCH_REFERENCE`, `HISTORICAL_PRECURSOR`, `SUPERSEDED`.

- [ ] **Step 1: Add validator tests**

Test rejection of:

- duplicate lineage IDs;
- missing or non-40-character `head`;
- unknown disposition;
- a non-canonical lineage marked `CANONICAL_TARGET`;
- any path presented as runtime proof.

Test acceptance of a complete temporary registry.

- [ ] **Step 2: Prove the validator is red**

Run:

```bash
PYTHONPATH=src python -m pytest tests/test_canon_integrity.py -k lineage -q
```

Expected: fail because the registry and validation do not yet exist.

- [ ] **Step 3: Add the verified lineages**

Register exactly:

| ID | Head | Disposition |
|---|---|---|
| `LINEAGE-ATLAS-CORE-CANDIDATE` | current candidate HEAD at record-update time | `CANONICAL_TARGET` |
| `LINEAGE-VOID-BASELINE` | `d8e96edc608097cbaa97ba07e8857785ad029f28` | `PORT_SOURCE` |
| `LINEAGE-VOID-FORWARD-PORT` | `34803da741beadd1520ae2639366f14c9f971d7f` | `PORT_SOURCE` |
| `LINEAGE-CODEOSS-1-129-1` | `8a7abeba6e03ea3af87bfbce9a1b7e48fed567b8` | `HOST_BASELINE` |
| `LINEAGE-ZED` | `c9e8e611dbc279afa0914d28c4d37ad07f38c03b` | `PATTERN_DONOR` |
| `LINEAGE-DOC0-RC2-CAPABILITIES` | `d01d4b931fd7f02af81a32c63c889d35f574fcab` | `ALREADY_INTEGRATED` |
| `LINEAGE-DOC0-RC2-CANON` | `3284d61b85d80db727b6162b250ec711a2acb83c` | `HISTORICAL_PRECURSOR` |

Inventory every remaining Atlas self-build worktree discovered by `git worktree list`; classify it without cherry-picking.

- [ ] **Step 4: Validate**

Run:

```bash
PYTHONPATH=src python scripts/check_canon.py
PYTHONPATH=src python -m pytest tests/test_canon_integrity.py -q
```

Expected: all registered heads and classifications parse; one and only one canonical target exists.

- [ ] **Step 5: Commit**

```bash
git add docs/canon/product_lineage_registry.jsonl docs/canon/authority_registry.yaml scripts/check_canon.py tests/test_canon_integrity.py
git commit -m "canon(lineage): register Atlas product ancestry"
```

---

### Task 5: Reconcile precursor capabilities semantically

**Files:**
- Add: `work/canon-compiler/delivery/LINEAGE_RECONCILIATION_REPORT.md`
- Modify: `docs/canon/component_reality_matrix.jsonl`
- Modify: `docs/canon/component_registry.jsonl`
- Modify: `docs/canon/capability_registry.jsonl`
- Modify: `work/canon-compiler/delivery/SOURCE_TRACEABILITY.jsonl`

**Interfaces:**
- Every source capability receives one result:
  `PRESENT_CANONICALLY`, `PORT_LATER`, `PATTERN_ONLY`, `REJECTED`, or `SUPERSEDED`.
- Git topology alone never decides integration.

- [ ] **Step 1: Compare the Doc0 precursor**

Use `git show d01d4b9 --name-status` from its worktree and verify the candidate implementations and tests for ACP, coding bridge, checkpoints, media generation, Home Assistant, lesson lifecycle, and NebulaGraph.

Record all of these as `PRESENT_CANONICALLY`; do not cherry-pick the disconnected commit.

- [ ] **Step 2: Compare the desktop forward port**

Use:

```bash
git -C /home/ronin/proyectos/atlas-ide-forward-port diff --name-status b3166e7..34803da
git -C /home/ronin/proyectos/atlas-ide-forward-port diff b3166e7..34803da -- src/vs/workbench/contrib/void/electron-main/atlasBackendMainService.ts
```

Record the provider roles, port-7342 bridge, lifecycle supervision, and tests as `PORT_LATER` for the Workbench convergence. Do not copy them into `src/atlas` or vendor editor sources in Cut 0. This Cut 0 disposition does not cap the breadth of the later Workbench integration.

- [ ] **Step 3: Classify host and donor baselines**

- CodeOSS 1.129.1: `HOST_BASELINE`, not Atlas implementation.
- VSCodium: privacy/build/update pipeline to be pinned during the Workbench cut.
- Zed: ACP/client and interaction-pattern donor; no source transplant into the CodeOSS tree.
- `atlas-shell`: existing validation harness, not product acceptance evidence.

- [ ] **Step 4: Validate reality references**

Run:

```bash
PYTHONPATH=src python scripts/check_canon.py
PYTHONPATH=src python -m pytest tests/test_acp_server.py tests/test_git_checkpoint.py tests/test_home_assistant_tool.py tests/test_image_gen_tool.py tests/test_video_gen_tool.py tests/test_lesson_lifecycle.py -q
npm --prefix ui/atlas-shell run build
```

Expected: precursor backend capabilities and their tests are present; the UI build passes; no external product lineage is labelled `LIVE_VERIFIED`.

- [ ] **Step 5: Commit**

```bash
git add docs/canon/component_reality_matrix.jsonl docs/canon/component_registry.jsonl docs/canon/capability_registry.jsonl work/canon-compiler/delivery/LINEAGE_RECONCILIATION_REPORT.md work/canon-compiler/delivery/SOURCE_TRACEABILITY.jsonl
git commit -m "canon(product): reconcile precursor capabilities by lineage"
```

---

### Task 6: Adopt the Atlas Workbench decision without pretending it is built

**Files:**
- Add: `docs/decisions/adr/adr_078_atlas_workbench_lineage_convergence.md`
- Modify: `docs/decisions/adr/adr_071_dedicated_apps_supersede_web_first_ux.md`
- Modify: `docs/canon/decision_registry.jsonl`
- Modify: `docs/canon/conflict_registry.jsonl`
- Modify: `docs/canon/supersession_registry.jsonl`
- Modify: `docs/canon/open_questions.jsonl`
- Modify: `docs/canon/implementation_registry.yaml`

**Interfaces:**
- ADR-078 status: `ACCEPTED` by operator on 2026-07-28.
- Product boundary:
  - current CodeOSS plus VSCodium privacy/build discipline is the host chain;
  - Void is a capability donor;
  - Zed is an ACP and interaction-pattern donor;
  - the first complete surface is the Atlas Engineering Workbench for missions, findings, incidents, diffs/fix proposals, validation, receipts, and approvals;
  - editor behavior exists only for surgical correction;
  - bespoke autocomplete/tab-completion is out of scope.
- Cut 0 accepts the boundary but does not claim implementation.

- [ ] **Step 1: Write ADR-078**

Include context, decision, invariants, lineage dispositions, licensing boundary, Cut 0/1/2 sequencing, rollback, and explicit non-claims.

- [ ] **Step 2: Resolve the old shell question**

Replace `OPEN-OPERATOR-PRODUCT-SHELL` with a resolved record referencing ADR-078. Mark `ADC-WO-101` decision complete. Add:

- `ADC-WO-010`: lineage reconciliation, `DONE` after Tasks 4–6;
- `ADC-WO-108`: Engineering Finding/Review Coordinator contract, `BLOCKED` on definitive-candidate acceptance;
- `ADC-WO-109`: comprehensive CodeOSS/VSCodium/Void Workbench convergence, scope to be decided in its own design, `BLOCKED` on `ADC-WO-108` and an exact upstream pin;
- `ADC-WO-110`: Zed ACP/pattern assimilation, `BLOCKED` on Workbench contract tests and license review.

Do not leave product-shell selection as `REQUIRES_OPERATOR`.

- [ ] **Step 3: Validate decision atomicity**

Run:

```bash
PYTHONPATH=src python scripts/check_canon.py
PYTHONPATH=src python -m pytest tests/test_canon_integrity.py -q
```

Expected: ADR-078 is indexed; resolved questions are not listed as pending; implementation remains conservatively `ACCEPTED_DESIGN`, never `CODE_PRESENT`.

- [ ] **Step 4: Commit**

```bash
git add docs/decisions/adr/adr_078_atlas_workbench_lineage_convergence.md docs/decisions/adr/adr_071_dedicated_apps_supersede_web_first_ux.md docs/canon/decision_registry.jsonl docs/canon/conflict_registry.jsonl docs/canon/supersession_registry.jsonl docs/canon/open_questions.jsonl docs/canon/implementation_registry.yaml
git commit -m "canon(product): accept Atlas Workbench convergence boundary"
```

---

### Task 7: Reconcile the definitive documents and ledger

**Files:**
- Modify: `ATLAS.md`
- Modify: `ARCHITECTURE.md`
- Modify: `PROGRAMS.md`
- Modify: `PLAN.md`
- Modify: `STATUS.md`
- Modify: `README.md`
- Modify: `WORK_LEDGER.md`
- Modify: `MEMORY.md` only for durable operator decisions

**Interfaces:**
- `CURRENT`: Atlas backend and validation harness, plus preserved external product lineages.
- `TARGET`: Engineering Workbench and internal review/debug/control plane.
- `TRANSITION`: Cut 0 candidate closure → Cut 1 backend review contracts → Cut 2 comprehensive Workbench convergence.

- [ ] **Step 1: Update product and program projections**

Reconcile P08 with ADR-078 and P02/P03/P06/P09 with the future internal review/debug flow. Keep all P00–P12 permanent programs and preserve P10–P12.

- [ ] **Step 2: Correct status claims**

State:

- Doc0 capability precursor: already integrated and tested where focused tests pass;
- Void forward port: preserved `PORT_SOURCE`, not wired into the candidate;
- CodeOSS/VSCodium: accepted host chain, not yet Atlas product code;
- Zed: pattern/ACP donor, not parked or final product;
- Hermes, MCP providers, and external models: not live unless fresh checks prove otherwise.

- [ ] **Step 3: Update durable memory and ledger**

Record only the approved convergence rule and product boundary in `MEMORY.md`. Record commits, validations, dispositions, and remaining work in `WORK_LEDGER.md`.

- [ ] **Step 4: Validate**

Run:

```bash
PYTHONPATH=src python scripts/check_canon.py
python scripts/docs_index_audit.py --strict
git diff --check
```

Expected: one human entrypoint, no duplicate product authority, no stale “operator decision required” for the Workbench shell, and no whitespace errors.

- [ ] **Step 5: Commit**

```bash
git add ATLAS.md ARCHITECTURE.md PROGRAMS.md PLAN.md STATUS.md README.md WORK_LEDGER.md MEMORY.md docs/INDEX.yaml
git commit -m "docs(atlas): align definitive candidate with Workbench lineage"
```

---

### Task 8: Run full validation and adversarial closure

**Files:**
- Modify as findings require: only files already in scope
- Add/Modify: `work/canon-compiler/delivery/VALIDATION_RESULTS.json`
- Add/Modify: `work/canon-compiler/delivery/ADVERSARIAL_AUDIT.md`

- [ ] **Step 1: Run canonical and Python gates**

```bash
PYTHONPATH=src python scripts/check_canon.py
PYTHONPATH=src python -m pytest tests/ -q
MYPYPATH=src python -m mypy src/atlas/
PYTHONPATH=src atlas audit --verify
PYTHONPATH=src atlas reality --json
```

- [ ] **Step 2: Run safe expanded runtime checks**

```bash
PYTHONPATH=src atlas reality --run-checks --include-browser --json
PYTHONPATH=src atlas doctor
PYTHONPATH=src atlas health
```

Never install optional dependencies merely to turn an environmental result green.

- [ ] **Step 3: Run UI gates**

```bash
npm --prefix ui/atlas-shell ci
npm --prefix ui/atlas-shell run build
npm --prefix ui/atlas-shell audit --audit-level=high
```

- [ ] **Step 4: Perform independent adversarial review**

Inspect authority duplication, false runtime claims, orphan code/docs, security bypasses, audit-before-effect, rollback, generated files, imports, accidental dependencies, secrets, and delivery completeness. Classify every finding `BLOCKING`, `MAJOR`, `MINOR`, or `INFO`.

Correct every `BLOCKING` and every technically resolvable `MAJOR`, rerunning the smallest failing gate and then the complete applicable gate.

- [ ] **Step 5: Record classified results**

For each failure use exactly:

`INTRODUCED_REGRESSION`, `PRE_EXISTING`, `ENVIRONMENTAL`, `OPTIONAL_DEPENDENCY_MISSING`, `RUNTIME_UNAVAILABLE`, `FLAKY`, or `UNKNOWN`.

The JSON record includes command, exit code, start/end time, result, classification, and evidence path.

- [ ] **Step 6: Commit**

```bash
git add work/canon-compiler/delivery/VALIDATION_RESULTS.json work/canon-compiler/delivery/ADVERSARIAL_AUDIT.md
git commit -m "test(convergence): record definitive validation evidence"
```

---

### Task 9: Assemble and verify the local delivery

**Files:**
- Add/Modify: all required files under `work/canon-compiler/delivery/`
- Modify: `docs/canon/implementation_registry.yaml`
- Modify: `WORK_LEDGER.md`

- [ ] **Step 1: Finalize required reports**

Produce:

- `DEFINITIVE_CONVERGENCE_REPORT.md`
- `CANON_COMPILATION_REPORT.md`
- `IMPLEMENTATION_REPORT.md`
- `ADVERSARIAL_AUDIT.md`
- `OPERATOR_DECISIONS_REQUIRED.md`
- `DEFERRED_ITEMS.md`
- `VALIDATION_RESULTS.json`
- `COMPONENT_REALITY_MATRIX.jsonl`
- `IMPLEMENTED_WORK_ORDERS.json`
- `DEFERRED_WORK_ORDERS.json`
- `LOCAL_COMMITS.json`
- `FINAL_DIFF.patch`
- `SOURCE_TRACEABILITY.jsonl`

Synchronize the delivery matrix with `docs/canon/component_reality_matrix.jsonl`. Mark only actually completed work orders `DONE`.

- [ ] **Step 2: Scan the final tree**

```bash
git diff --check
git status --short --branch
git log --oneline c95038c9d7e97ddc6339f38abe6dad09b166f47d..HEAD
rg -n --hidden -g '!node_modules/**' -g '!.git/**' '(BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|api[_-]?key\\s*[:=]|token\\s*[:=])' .
```

Manually review every match; do not print secret values into reports.

- [ ] **Step 3: Commit the delivery manifest**

```bash
git add docs/canon/implementation_registry.yaml WORK_LEDGER.md work/canon-compiler/delivery
git commit -m "docs(delivery): assemble definitive candidate evidence"
```

- [ ] **Step 4: Re-run final gates from the committed tree**

Run the complete command set from Task 8 plus:

```bash
test -z "$(git status --porcelain)"
git bundle create ../atlas-definitive-convergence-20260728.bundle codex/atlas-definitive-convergence-20260727-154020
git bundle verify ../atlas-definitive-convergence-20260728.bundle
sha256sum ../atlas-definitive-convergence-20260728.bundle > ../atlas-definitive-convergence-20260728.bundle.sha256
```

If generated delivery evidence makes the tree dirty, regenerate, commit once, and rerun the clean-tree assertion and validators.

- [ ] **Step 5: Create the documentary delivery ZIP**

Include only the six root canon documents, `docs/canon/**`, ADR-078, the approved spec, this plan, and `work/canon-compiler/delivery/**`. Exclude repository source, `.git`, dependencies, caches, runtime databases, logs, credentials, and the source corpus ZIP.

- [ ] **Step 6: Verify integration handoff**

Record base commit, final commit, branch, worktree, backup path, bundle path/SHA-256, documentary ZIP path/SHA-256, exact review commands, and a non-destructive integration sequence. Do not merge or push.

---

## Deferred Follow-on Cuts

- **Cut 1 — Engineering Review Plane:** define and implement `EngineeringFinding`, `ReviewCoordinator`, `DiagnosticCoordinator`, review/debug event contracts, receipts, approvals, and tests by composing existing Atlas verification, production, diagnosis, audit, Golden Route, Decider, EventBus, and Merkle components.
- **Cut 2 — Atlas Workbench Host:** design a complete professional product convergence over a pinned CodeOSS/VSCodium baseline, reusing the Void Atlas bridge and lifecycle, exposing Cut 1 contracts through ACP/bridge adapters, and assimilating relevant Zed capabilities and patterns. Its exact breadth is deliberately left for that cut's operator discussion; it is not presumed to be a bounded or minimal port.
- Neither cut may be reported as implemented by completion of this plan.

## Completion Criteria

- Original checkout and backup remain unchanged and verifiable.
- All local lineages have explicit authority and disposition.
- No disconnected precursor is blindly cherry-picked.
- Sentinel focused tests and full suite pass.
- Full mypy passes or every pre-existing failure is proven against the base commit.
- Canon validator, audit, reality, UI install/build/audit, and safe runtime checks are recorded.
- No `BLOCKING` or technically resolvable `MAJOR` finding remains.
- Candidate documents, code, tests, registries, ledger, and delivery reports agree.
- Local commits, bundle, SHA-256, documentary ZIP, and rollback instructions are complete.
