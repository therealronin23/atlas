# Atlas Canonical Decision Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Supersede ADR-082 without inventing a replacement stack, repair every structured claim that inherited its invalid conclusion, and apply the canonical change only through Golden Route and ColdUpdate.

**Architecture:** First extend the existing Golden Route with a reviewed, multi-file patch intake that still delegates validation, approval, apply, rollback, commit, and Merkle evidence to `ColdUpdateManager`. Then strengthen the generic canon validator so a `SUPERSEDED` decision cannot exist without a valid relationship. Finally build the ADR-083 change in a detached staging worktree, submit its exact diff through Golden Route, and execute the existing ColdUpdate ceremony.

**Tech Stack:** Python 3.11+, Click, pytest, Git unified patches/worktrees, JSONL/YAML canon registries, existing `ColdUpdateManager`, existing `MerkleLogger`.

## Global Constraints

- The operator's exact clarification is: `No, fue una sugerencia que yo acepte sin pensarlo mucho`. Preserve it without adding punctuation inside the quote and keep the separate inference explicit: it invalidates ADR-082 as an informed stack selection; it does not select another stack.
- ADR-082 remains as historical evidence and is marked `SUPERSEDED`; it is never deleted or rewritten as though it never existed.
- ADR-083 is a canon correction with `selected_stack: null`; Flutter, Compose, and Qt remain evidence, not winners.
- ADR-071's Android requirement and ADR-078's CodeOSS/VSCodium desktop-host claim remain pending factual operator confirmation. Documentary `accepted` labels are not proof of current intent.
- T2.1, T2.2, and T2.3 must not inherit Flutter or any other unconfirmed stack, and they must not be silently reopened as implementation work.
- Every canonical mutation goes through `atlas golden-route request`, then `atlas update validate`, `atlas update approve`, and `atlas update apply`. If any stage fails, stop and repair the route; never edit the canonical files directly in the implementation worktree.
- Do not run `atlas f26 run`. Only query `atlas f26 status --json`; final execution requires a separate explicit authorization after the last UI disposition.
- Do not modify `config/governance.json`, install dependencies, start `atlas-core.service`, or enable schedulers/providers/external effects.
- Preserve the operator's existing `.gitignore` modification and untracked `docs/fixtures/`; neither may enter staging or a commit.
- All new Python behavior starts with a test that fails for the intended reason. Existing green tests that do not reproduce the path are not RED evidence.
- Use only the existing standard library and dependencies already declared by the project.
- Execute the plan from the dedicated implementation worktree. Its ignored `.venv` symlink must point to `/home/ronin/proyectos/atlas-core/.venv`; therefore every command under `.venv/bin` below uses the already-verified shared environment while `PYTHONPATH=src` resolves code from the worktree.

## File and interface map

- `src/atlas/core/cold_update_manager.py`: persist the exact paths validated and applied for each proposal, and admit only the six named canonical root documents needed by this correction.
- `src/atlas/missions/golden_route.py`: accept either an existing deterministic text plan or an operator-reviewable patch artifact; derive receipts from every touched path.
- `src/atlas/interfaces/cli.py`: expose `golden-route request --patch PATH --json TEXT` without changing the existing text-only command.
- `scripts/check_canon.py`: validate decision-to-supersession referential integrity generically.
- `tests/test_cold_update_patch_intake.py`, `tests/test_golden_route.py`, `tests/test_golden_route_wiring.py`, and `tests/acceptance/test_self_construction_golden_route.py`: behavioral coverage for the route.
- `tests/test_canon_integrity.py`: synthetic validator coverage.
- `tests/test_adr_082_disposition.py`: repository-level structured acceptance for this correction; it is delivered inside the governed canonical patch.
- Canonical patch: root authority projections, ecosystem map, ADR-071/078 annotations, ADR-082 annotation, ADR-078 dossier annotation, new ADR-083 and dossier, backlog, decision/evidence/supersession/conflict/open-question/lineage/component/capability/reality/implementation registries, and `docs/INDEX.yaml`.

---

### Task 1: Bind ColdUpdate to one checkout and make apply transactional

**Files:**
- Modify: `src/atlas/core/cold_update_manager.py:229-389`
- Modify: `tests/test_cold_update_patch_intake.py`
- Modify: `tests/test_cold_update_manager.py`
- Modify: `docs/decisions/adr/adr_025_cold_update_manager.md`

**Interfaces:**
- Produces persisted proposal identity: `target_root`, immutable
  `base_commit`, ordered `touched_paths`, `intake_profile`, `applied_commit`,
  and `apply_audit_ref`. Legacy rows load, but rows lacking checkout/path
  identity fail closed at validation/approval/apply and must be re-proposed.
- Defines two intake profiles. `standard` retains the existing generic scope;
  `reviewed_hitl` additionally admits exactly `ARCHITECTURE.md`, `ATLAS.md`,
  `PLAN.md`, `PROGRAMS.md`, `STATUS.md`, and `VISION.md`. `README.md` and
  `WORK_LEDGER.md` remain forbidden. The reviewed profile is legal only with
  `origin="manual"` and `risk in {"high", "critical"}`.
- Produces `_preflight_patch(...)`, `_assert_checkout_preconditions(...)`,
  `_commit_with_evidence(...) -> str`, and a checked rollback. Apply order is
  preconditions -> dry-run -> `cold_update.apply_prepared` -> mutation ->
  post-validation -> scoped commit -> `cold_update.applied` -> persisted
  terminal state. No earlier step may claim `applied`.
- Adds explicit terminal recovery vocabulary: `recovery_required` for a
  verified normal revert after a post-commit durability failure, and
  `rollback_failed` when compensation cannot be proven. Neither is `applied`.

- [ ] **Step 1: Write RED tests for immutable proposal identity and the HITL-only root profile**

Initialize every manager fixture as a real Git repository with an initial
commit; do not make commit behavior optional in tests. Add one patch that
modifies `docs/existing.md` and creates `docs/new.md`, then assert a proposal
persists all of the following across a second manager instance:

```python
assert proposal.target_root == str(repo.resolve())
assert proposal.base_commit == _git(repo, "rev-parse", "HEAD")
assert proposal.touched_paths == ["docs/existing.md", "docs/new.md"]
assert proposal.intake_profile == "standard"
assert proposal.applied_commit is None
assert proposal.apply_audit_ref is None
```

Add a legacy-ledger test proving missing new keys load with compatibility
defaults, followed by an apply test proving such a legacy row is rejected with
`unbound proposal; re-propose` rather than inferring identity from current
`HEAD` or reparsing a mutable patch.

Add parametrized scope tests with these boundaries:

- a direct/default `ColdUpdateManager.propose()` patch to any of the six root
  authority documents is rejected and allocates no proposal;
- `intake_profile="reviewed_hitl"`, `origin="manual"`, and `risk="high"`
  admits exactly those six files;
- the reviewed profile rejects low/medium risk, `self_audit`, and `swarm`;
- `README.md`, `WORK_LEDGER.md`, a root wildcard, a path escape, and
  `config/governance.json` are rejected under both profiles;
- `tier1_auto_apply()` rejects every proposal whose `touched_paths` contains a
  root file, including the already-standard `pyproject.toml`, before bwrap or
  validation is invoked.

The public `atlas update propose` command has no option for selecting
`reviewed_hitl`; Task 2's reviewed Golden Route is its sole CLI entry point.

- [ ] **Step 2: Run the tests and verify the intended RED**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_cold_update_patch_intake.py \
  tests/test_cold_update_manager.py -q \
  -k 'proposal_identity or legacy_unbound or reviewed_hitl or root_file or tier1'
```

Expected: new tests FAIL because proposal identity/profile fields do not exist
and there is no reviewed-HITL scope. If a new test passes before production
code changes, fix the test so it exercises the missing contract; do not count
the already-green baseline as RED.

- [ ] **Step 3: Bind proposal creation, validation, and approval to immutable state**

Add compatibility-defaulted fields:

```python
@dataclass
class ColdUpdateProposal:
    target_root: str = ""
    base_commit: str | None = None
    touched_paths: list[str] = field(default_factory=list)
    intake_profile: str = "standard"
    applied_commit: str | None = None
    apply_audit_ref: str | None = None
```

Place them after the current defaulted fields in dataclass-valid order. `_load()`
sets only compatibility defaults; it never fills identity from live state.

Change `propose()` to accept
`intake_profile: Literal["standard", "reviewed_hitl"] = "standard"`. Resolve
`target_root = str(self._root.resolve())` and resolve `base_ref` exactly once
with `git rev-parse --verify <base_ref>^{commit}` before allocating the
worktree. Persist that SHA as `base_commit`, create the detached worktree from
that SHA (not symbolic `HEAD`), assert its `HEAD` equals the SHA, copy/hash the
patch, validate it with the profile, preflight it, and capture the paths from
the stored digest-bound artifact:

```python
touched_paths = self._apply_patch(
    wt_dir,
    stored_patch,
    expected_sha256=patch_sha256,
    intake_profile=intake_profile,
)
```

Keep `pyproject.toml` in the standard root set. Define a separate reviewed set:

```python
_COLD_UPDATE_REVIEWED_HITL_ROOT_FILES = frozenset(
    {
        "ARCHITECTURE.md",
        "ATLAS.md",
        "PLAN.md",
        "PROGRAMS.md",
        "STATUS.md",
        "VISION.md",
    }
)
```

Make `_validate_patch_intake()` take the persisted profile and choose the exact
set internally. Enforce manual/high-or-critical for `reviewed_hitl` in
`propose()`; never derive this authority from `evidence`. `_require_intact_patch`
revalidates digest, profile, and exact path equality with persisted
`touched_paths` on validate, approve, apply, and rollback.

Add `_assert_checkout_preconditions(proposal)` and call it at validate,
approve, and apply. It requires the same canonical root, `HEAD == base_commit`,
the proposal worktree at the same base during validation, an empty index, and
no tracked/untracked changes at any touched path. Checkout drift is a
precondition rejection: preserve `validated`/`approved` state and make the
operator re-propose; do not label an unapplied patch `failed`.

- [ ] **Step 4: Write RED tests for preflight, fatal commit, and checked rollback**

Use a manager with a recording Merkle logger and a controllable subprocess
runner. Add these tests before changing `apply()`:

1. `test_apply_rejects_wrong_root_before_mutation`: copy the proposal ledger to
   another repository and assert apply rejects `target_root`; neither checkout
   changes and no `apply_prepared` event exists.
2. `test_apply_rejects_head_drift_without_consuming_approval`: create a commit
   after approval; assert the proposal remains `approved`, no touched file
   changes, and the operator must re-propose.
3. `test_apply_preflight_failure_does_not_mutate`: make `git apply --check`
   fail and assert no mutation, commit, terminal status, or prepared event.
4. `test_git_preflight_failure_never_falls_back_to_patch`: make `git apply
   --check` return non-zero in a Git repository and assert apply aborts without
   invoking `patch`. If non-Git fixture support is deliberately retained, add
   a separate helper-level test proving that only an explicitly non-Git target
   runs `patch --dry-run --batch -p1 ...` before `patch --batch -p1 ...`.
5. `test_commit_failure_is_fatal_and_restores_exact_paths`: fail `git commit`
   after mutation; assert apply raises, every touched path and the index equal
   `base_commit`, status is `failed`, no `cold_update.applied` event exists,
   and `cold_update.rollback` records success.
6. `test_rollback_failure_is_explicit_and_fatal`: fail both commit and restore;
   assert status `rollback_failed`, forensics contain the exact failed command,
   a `cold_update.rollback_failed` event is emitted, and apply raises a
   dedicated error rather than claiming ordinary failure.
7. `test_success_marks_applied_only_after_scoped_commit`: seed an unrelated
   untracked file, apply successfully, and assert the returned/persisted
   `applied_commit` is `HEAD`, only `touched_paths` are in that commit,
   `apply_audit_ref` is the final Merkle record hash, and event order is
   `apply_prepared` then `applied`.
8. `test_proposal_save_is_atomic`: inject a write/fsync/replace failure and
   prove the previous `proposals.json` remains parseable and unchanged; no
   truncated ledger is accepted on reload.

Also make `_rollback_patch()` unit tests assert non-zero exit is raised; the
current ignored return code is the intended RED.

- [ ] **Step 5: Run only the new transaction tests and observe RED**

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_cold_update_patch_intake.py \
  tests/test_cold_update_manager.py -q \
  -k 'wrong_root or head_drift or preflight or never_falls_back or non_git_fallback or commit_failure or rollback_failure or scoped_commit or save_is_atomic'
```

Expected: every named behavior fails for its own missing assertion. In
particular, the existing implementation currently writes `status="applied"`
and an applied audit event before a best-effort commit; that is the defect the
tests must expose.

- [ ] **Step 6: Implement one fail-closed apply transaction**

`_preflight_patch()` must validate digest/profile/path equality and run a
non-mutating check immediately before mutation. In a Git repository,
`git apply --check -- <patch>` returning non-zero is final: abort and never
fall through to `patch`, because that would turn a rejected/conflicting diff
into a fuzzier mutation. Only if explicitly supporting a non-Git target may
that branch use `patch --dry-run --batch -p1 -i <patch>` followed by the same
command without `--dry-run`. A failed dry-run aborts without an audit record
implying mutation.

After checkout preconditions and preflight pass, append
`cold_update.apply_prepared` with proposal ID, target root, base SHA, patch
digest, and exact paths. Then:

1. apply the already-preflighted stored patch;
2. assert the returned paths equal persisted `touched_paths` exactly;
3. run post-apply validation;
4. call `_commit_with_evidence(...) -> str`;
5. verify the returned SHA is `HEAD`, its first parent is `base_commit`, and
   `git diff-tree --name-only` equals `touched_paths` exactly;
6. append `cold_update.applied`, persist its `hash_self` as
   `apply_audit_ref`, persist the commit SHA, and only then set/save
   `status="applied"` and return them in the result.

Make `_save()` durable and atomic: write JSON to a same-directory temporary
regular file, flush and `fsync`, `os.replace` it over `proposals.json`, then
`fsync` the directory. Preserve the previous ledger on any pre-replace error.
Do not keep `_load()`'s current broad exception swallowing for malformed
state: surface a clear ledger-integrity error instead of starting with an
apparently empty proposal set.

Make `_commit_with_evidence` non-best-effort: require a Git checkout and a
non-empty persisted path set, run `git add -- <exact paths>`, reject any staged
path outside the set, and run a path-scoped commit (`git commit --only ... --
<exact paths>`). Any add/commit/verification failure raises. Never use
`git add -A`, never commit an unrelated staged path, and never catch an error
merely to put it in `forensics` while returning success.

For any failure after mutation and before terminal persistence, rollback only
the validated path set to `base_commit`: unstage those paths, restore paths
that existed at the base, remove only proposal paths proven absent at the
base, and then require both `git diff --quiet <base> -- <paths>` and an empty
`git status --porcelain -- <paths>`. Check every command. A verified rollback
sets `failed` and emits `cold_update.rollback`; an unverified rollback sets
`rollback_failed`, stores command/stdout/stderr in forensics, emits
`cold_update.rollback_failed`, and raises. Neither path emits
`cold_update.applied`.

If final Merkle append or proposal persistence fails after a commit, treat it
as transaction failure and enter `recovery_required`. Never move a ref
backwards, reset `HEAD`, amend, or rewrite history. If `HEAD` is still the
proposal commit, create a normal revert commit, verify its parent is the
proposal commit and its tree equals `base_commit`, then persist/audit
`recovery_required` with both SHAs for operator review. If `HEAD` changed, the
revert fails, or its tree does not restore the base, mark/audit
`rollback_failed` and stop. The implementation must never report `applied`
without its durable audit and ledger record.

Update `tier1_auto_apply()` before bwrap so any root-level touched path is
always HITL. Update ADR-025 with the checkout binding, intake profiles,
transaction ordering, scoped-commit rule, and explicit rollback-failure state.

- [ ] **Step 7: Run focused and adjacent tests**

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_cold_update_patch_intake.py \
  tests/test_cold_update_manager.py \
  tests/test_cold_update_batcher.py -q
MYPYPATH=src .venv/bin/python -m mypy src/atlas/core/cold_update_manager.py
```

Expected: PASS. Inspect at least one real fixture commit with
`git diff-tree --no-commit-id --name-only -r <sha>` and confirm its set equals
the persisted path list.

- [ ] **Step 8: Commit the transaction contract**

```bash
git add src/atlas/core/cold_update_manager.py \
  tests/test_cold_update_patch_intake.py tests/test_cold_update_manager.py \
  docs/decisions/adr/adr_025_cold_update_manager.md
git commit -m "feat(cold-update): make governed apply transactional"
```

---

### Task 2: Add reviewed multi-file patch intake to Golden Route

**Files:**
- Modify: `src/atlas/core/cold_update_manager.py`
- Modify: `src/atlas/missions/golden_route.py:41-476`
- Modify: `src/atlas/interfaces/cli.py:268-294`
- Modify: `src/atlas/api/missions.py:138-212`
- Modify: `src/atlas/api/server.py:428-452,630-665`
- Modify: `schemas/mission_receipt.schema.json`
- Modify: `tests/test_golden_route.py`
- Modify: `tests/test_golden_route_wiring.py`
- Modify: `tests/acceptance/test_self_construction_golden_route.py`
- Modify: `tests/test_os_missions.py`
- Modify: `docs/design/mission_layer_self_construction_spec.md`

**Interfaces:**
- Consumes: `ColdUpdateManager.propose -> ColdUpdateProposal` and `ColdUpdateProposal.touched_paths` from Task 1.
- Produces: `GoldenRoute.request(text: str, *, risk: str | None = None, patch_path: Path | None = None) -> GoldenRouteSession`.
- Produces: `GoldenRouteSession.plan: dict[str, Any]` with `action` and `paths`; deterministic single-file plans retain `path`, `line`, `old`, and `new` where applicable.
- Produces a stable, stateless receipt derived only from the persisted proposal:
  `files_touched` comes from `touched_paths`, and applied receipts include
  `applied_commit` and `apply_audit_ref`. `generated_at` uses persisted
  `updated_at`, so CLI and API return the same receipt after process restart.
- Produces CLI: `atlas golden-route request [--patch FILE] [--json] TEXT`.
- Extends `atlas update apply ID` to return
  `{proposal_id,status,validation,files_touched,applied_commit,apply_audit_ref,receipt}`.
  `/missions/{mission_id}` returns the identical receipt without a live
  `GoldenRouteSession`.

- [ ] **Step 1: Write failing unit tests for reviewed patches and path safety**

In `tests/acceptance/test_self_construction_golden_route.py`, extend
`fixture_repo` with `docs/a.md` containing `before\n` and committed
`ATLAS.md`/`VISION.md` fixtures. Define
`MULTI_DOC_PATCH` as a unified patch that replaces that line with `after` and
creates `docs/b.md` containing `new\n`. Add a `route` fixture using
`GoldenRoute.for_repo(fixture_repo, store_dir=tmp_path / "updates",
audit_dir=tmp_path / "audit", runner_factory=_SubprocessRunner)`. Exercise this
public route, not `ColdUpdateManager` directly:

```python
def test_request_accepts_reviewed_multi_file_patch(
    route: GoldenRoute, tmp_path: Path
) -> None:
    patch = tmp_path / "canon.patch"
    patch.write_text(MULTI_DOC_PATCH, encoding="utf-8")

    session = route.request(
        "supersede ADR-082 without selecting a replacement stack",
        patch_path=patch,
    )

    assert session.plan == {
        "action": "reviewed_patch",
        "paths": ["docs/a.md", "docs/b.md"],
    }
    assert session.diff == MULTI_DOC_PATCH
```

Add five named cases with these exact assertions:

- `test_reviewed_patch_defaults_to_high_risk`: request the valid two-file patch and assert `route._manager.get(session.proposal_id).risk == "high"`.
- `test_reviewed_patch_is_the_only_route_to_root_authority`: submit a patch
  touching `ATLAS.md` and `VISION.md` through `GoldenRoute.request`, assert its
  persisted profile is `reviewed_hitl`, then submit the same patch through a
  direct/default manager proposal and assert rejection.
- `test_reviewed_patch_rejects_governance_path_before_proposal`: submit a patch for `config/governance.json`, assert `UnsupportedRequestError` with `governance inmutable`, then assert `route._manager.list_proposals() == []`.
- `test_reviewed_patch_rejects_path_escape_before_proposal`: submit a patch whose destination is `b/docs/../outside.md`, assert `UnsupportedRequestError` with `segmento inseguro`, then assert the proposal list remains empty.
- `test_existing_append_plan_exposes_single_path_list`: use the current append grammar and assert `session.plan["paths"] == ["docs/a.md"]`.
- `test_existing_rename_plan_exposes_single_path_list`: use the current rename grammar against `src/demo_pkg/helper.py` and assert `session.plan["paths"] == ["src/demo_pkg/helper.py"]`.

Keep fixture state isolated per test; assertions may use the private manager only
to prove that rejection happened before proposal allocation, never to execute the
route.

Add `test_session_apply_uses_persisted_paths_not_mutable_plan`: approve a
fixture proposal, mutate `session.plan["paths"]` to an unrelated value, apply,
and assert the commit/result/receipt still use `proposal.touched_paths`. The
session plan is display metadata, never apply authority.

- [ ] **Step 2: Run the unit tests and verify RED**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_golden_route.py \
  tests/acceptance/test_self_construction_golden_route.py -q \
  -k 'reviewed_patch or exposes_single_path or persisted_paths'
```

Expected: FAIL because `GoldenRoute.request()` does not accept `patch_path` and existing plans have no `paths` list.

- [ ] **Step 3: Implement the reviewed-patch branch without reimplementing ColdUpdate**

Use the existing manager for intake, worktree creation, patch application,
digesting, and audit. Change the method signature exactly as follows:

```python
def request(
    self,
    text: str,
    *,
    risk: str | None = None,
    patch_path: Path | None = None,
) -> GoldenRouteSession:
```

At the start of the method, branch on `patch_path`. The reviewed branch is:

```python
    if patch_path is not None:
        resolved_risk = risk or "high"
        try:
            proposal = self._manager.propose(
                text,
                patch_path,
                origin="manual",
                risk=resolved_risk,
                intake_profile="reviewed_hitl",
                evidence={"golden_route": True, "plan_kind": "reviewed_patch"},
            )
        except PatchIntakeError as exc:
            raise UnsupportedRequestError(str(exc)) from exc
        plan: dict[str, Any] = {
            "action": "reviewed_patch",
            "paths": list(proposal.touched_paths),
        }
```

Move the current deterministic plan/target/read/temporary-patch/propose logic
under the `else` branch. In that branch use `resolved_risk = risk or "low"`,
add `plan["paths"] = [plan["path"]]` immediately after parsing, and pass
`risk=resolved_risk` to the existing proposal call. Leave temporary-patch
cleanup in its existing `finally`. After either branch, emit the existing
`golden_route.requested` event and return a session once.

Do not call `attach_evidence()` after creating a reviewed proposal. Its initial
evidence already contains `golden_route` and `plan_kind`, while the persisted
`touched_paths` reconstruct the display plan. Avoiding a second ledger write
also removes the crash window between proposal creation and evidence attach.

Import `PatchIntakeError`, change plan annotations in `GoldenRouteSession` and
this method from `dict[str, str]` to `dict[str, Any]`, and retain all current
Merkle fields. Never read or modify target files in the reviewed branch; the
patch is the exact review artifact.

Update `GoldenRouteSession.apply()` so it ignores mutable `self.plan` for
authority. Re-read the persisted proposal after manager apply and use only its
bound result:

```python
apply_result = self._manager.apply(self._proposal_id)
proposal = self._proposal()
paths = list(proposal.touched_paths)
receipt = mission_receipt(proposal.to_dict())
```

Replace the Merkle payload's singular `"path"` field with `"paths": paths`.
Include the persisted `applied_commit` and `apply_audit_ref`; do not keep both
singular and plural path fields. If a Golden Route-specific applied event is
retained, it is a presentation event after the authoritative ColdUpdate
transaction and its hash is not allowed to replace `proposal.apply_audit_ref`.

Before the acceptance test, make `mission_receipt()` stateless. Its default
path source is the ledger; a caller-supplied list is accepted only as a legacy
fallback when `touched_paths` is absent:

```python
paths = proposal.get("touched_paths")
if not isinstance(paths, list):
    paths = list(files_touched or [])
return {
    "receipt_id": f"rcp_{proposal_id}",
    "mission_id": _mission_id(proposal_id),
    "files_touched": list(paths),
    "applied_commit": proposal.get("applied_commit"),
    "apply_audit_ref": proposal.get("apply_audit_ref"),
    "generated_at": proposal.get("updated_at") or stable_legacy_timestamp,
```

Do not use `datetime.now()` for current proposal receipts: repeated CLI/API
reads must be byte-for-byte stable. For malformed legacy rows lacking
`updated_at`, use the existing persisted `created_at`; if both are absent,
emit `generated_at: null` and allow `null` in the backward-compatible schema
rather than inventing a time.

Extend receipt state handling for Task 1: `recovery_required` and
`rollback_failed` are not successful or silently closed. Their
`whats_missing` and `decision_needed` fields require operator recovery and cite
the proposal/forensics; `verifiable` must not imply successful application.
Add focused tests for both statuses.

Add `files_touched`, `applied_commit`, and `apply_audit_ref` to
`mission_receipt.schema.json`; keep the two new nullable fields optional so old
receipts remain valid. Add those keys with empty/null values to
`ecosystem_drift_receipt()` so every current producer emits one shape. Add
`assert receipt["files_touched"] == ["pyproject.toml"]` to
`test_mission_receipt_is_honest_and_verifiable`; both schema-conformance tests
must remain green, and add explicit empty/null assertions for the
ecosystem-drift receipt. For an applied fixture, assert commit/audit fields
match the persisted proposal and two calls return equal dicts.

- [ ] **Step 4: Write failing CLI tests, including the pre-existing rename-output bug**

Add tests that invoke:

```python
result = runner.invoke(
    cli,
    [
        "golden-route", "request", "--patch", str(patch), "--json",
        "supersede ADR-082 without selecting a replacement stack",
    ],
)
payload = json.loads(result.output)
assert result.exit_code == 0
assert payload["action"] == "reviewed_patch"
assert payload["paths"] == ["docs/a.md", "docs/b.md"]
assert payload["proposal_id"]
assert payload["target_root"] == str(fixture_repo.resolve())
assert payload["base_commit"] == _git(fixture_repo, "rev-parse", "HEAD")
```

In `tests/test_golden_route_wiring.py`, extend `mini_project` with
`src/atlas/demo.py` containing `old_name = 1\n`. Also invoke
`renombra old_name a new_name en src/atlas/demo.py` through the CLI and assert
exit code zero. This must fail before implementation because the current CLI
blindly reads `session.plan['line']`.

Then add a truly stateless lifecycle test. Invoke `golden-route request` with
one CLI/orchestrator instance, discard it, construct fresh instances over the
same repository/store/audit directories for `update validate`, `update
approve`, and `update apply`, and parse the final JSON. Assert:

```python
assert payload["status"] == "applied"
assert payload["files_touched"] == ["ATLAS.md", "VISION.md"]
assert payload["applied_commit"] == _git(repo, "rev-parse", "HEAD")
assert payload["apply_audit_ref"]
assert payload["receipt"]["files_touched"] == payload["files_touched"]
assert payload["receipt"]["applied_commit"] == payload["applied_commit"]
assert payload["receipt"]["apply_audit_ref"] == payload["apply_audit_ref"]
```

Construct yet another fresh app/API instance and request
`/missions/msn_<proposal_id>`. Assert its receipt equals the CLI receipt
byte-for-byte. Mutate/delete the original user-supplied patch after proposal
creation and prove both surfaces still use the stored proposal artifact and
persisted paths.

Add the legacy-only API test separately: when a fixture proposal genuinely
lacks `touched_paths`, `_proposal_files_touched()` may parse the stored patch;
when the key exists (including an empty list), it must never reparse and must
return the persisted value.

Run before changing CLI/API code:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_golden_route_wiring.py tests/test_os_missions.py \
  tests/acceptance/test_self_construction_golden_route.py -q \
  -k 'json or rename or stateless or process_boundaries or persisted_paths or legacy'
```

Expected: the rename-output test fails on the action-specific `line` lookup;
the lifecycle test fails because separate `update apply` emits no receipt;
and the API test fails because it reparses the patch even when bound paths are
persisted. Confirm each failure independently before Step 5.

- [ ] **Step 5: Implement generic human and JSON CLI output**

Add options using the existing Click dependency:

```python
@golden_route.command("request")
@click.option(
    "--patch",
    "patch_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--json", "as_json", is_flag=True)
@click.argument("text")
def golden_route_request(text: str, patch_path: Path | None, as_json: bool) -> None:
    from atlas.missions.golden_route import UnsupportedRequestError

    orch = get_orchestrator()
    try:
        session = orch.golden_route().request(text, patch_path=patch_path)
    except UnsupportedRequestError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc
    payload = {
        "proposal_id": session.proposal_id,
        "action": session.plan["action"],
        "paths": session.plan["paths"],
        "target_root": proposal.target_root,
        "base_commit": proposal.base_commit,
        "next_commands": [
            f"atlas update validate {session.proposal_id}",
            f"atlas update approve {session.proposal_id}",
            f"atlas update apply {session.proposal_id}",
        ],
    }
```

Retrieve `proposal = orch.cold_update().get(session.proposal_id)` immediately
before constructing the payload and fail if it disappeared. The request JSON
must expose the persisted `target_root` and immutable `base_commit`; Task 5
uses both as pre-apply assertions, not as caller authority.

When `as_json` is true, use `console.print_json(json.dumps(payload, ensure_ascii=False))`. Otherwise print `action` and `paths`; do not assume action-specific keys such as `line`.

Keep the request command proposal-only: it must not cache a session for later
commands and must not claim a receipt before apply. Adapt `update apply` to the
durable ColdUpdate result:

```python
result = orch.cold_update().apply(proposal_id)
proposal = orch.cold_update().get(proposal_id)
if proposal is None:  # defensive, cannot be a success
    raise RuntimeError(f"proposal disappeared after apply: {proposal_id}")
receipt = mission_receipt(proposal.to_dict())
payload = {**result, "receipt": receipt}
console.print_json(json.dumps(payload, ensure_ascii=False, default=str))
```

The manager result and proposal ledger are authoritative and must already
contain `files_touched`, `applied_commit`, and `apply_audit_ref` from Task 1;
the CLI does not reparse a patch and does not manufacture them from a session.

In `src/atlas/api/server.py`, change `_proposal_files_touched()` to return a
validated string copy of `proposal["touched_paths"]` whenever that key is
present. Only rows where the key is genuinely absent use the existing patch
parser as a named legacy fallback. `/missions` and `/missions/{mission_id}`
call `mission_receipt(proposal)` for current rows; do not pass a separately
reparsed list that could disagree with checkout-bound authority.

- [ ] **Step 6: Prove the reviewed route and receipt survive process boundaries**

Run the new lifecycle test first and keep it RED until every command rebuilds
state from `proposals.json`. The final assertions are:

```python
assert cli_payload["files_touched"] == ["ATLAS.md", "VISION.md"]
assert cli_payload["applied_commit"] == persisted["applied_commit"]
assert cli_payload["apply_audit_ref"] == persisted["apply_audit_ref"]
assert cli_payload["receipt"] == api_payload["receipt"]
assert cli_payload["receipt"] == mission_receipt(persisted)
assert (fixture_repo / "ATLAS.md").read_text(encoding="utf-8") == "after atlas\n"
assert (fixture_repo / "VISION.md").read_text(encoding="utf-8") == "after vision\n"
```

Also keep a direct-session compatibility test: `GoldenRouteSession.apply()`
fails before its in-memory human approval, then succeeds after approval, but
its receipt must equal the stateless ledger-derived receipt. This path is not
the operational CLI path and may not be the sole receipt producer.

Update `docs/design/mission_layer_self_construction_spec.md` to document the
reviewed-HITL root profile, the proposal-only request command, the stateless
validate/approve/apply lifecycle, and the persisted checkout/commit/audit
fields that make CLI and API receipts reproducible.

- [ ] **Step 7: Run the complete Golden Route regression**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_golden_route.py \
  tests/test_golden_route_wiring.py \
  tests/acceptance/test_self_construction_golden_route.py \
  tests/test_cold_update_patch_intake.py \
  tests/test_cold_update_manager.py \
  tests/test_os_missions.py -q
MYPYPATH=src .venv/bin/python -m mypy \
  src/atlas/missions/golden_route.py \
  src/atlas/api/missions.py \
  src/atlas/api/server.py \
  src/atlas/core/cold_update_manager.py \
  src/atlas/interfaces/cli.py
```

Expected: PASS with the original append/rename behaviors unchanged, root
authority reachable only through reviewed HITL, and CLI/API returning the same
durable receipt after restarts.

- [ ] **Step 8: Commit the governed multi-file route**

```bash
git add src/atlas/core/cold_update_manager.py \
  src/atlas/missions/golden_route.py src/atlas/interfaces/cli.py \
  src/atlas/api/missions.py src/atlas/api/server.py \
  schemas/mission_receipt.schema.json \
  tests/test_golden_route.py tests/test_golden_route_wiring.py \
  tests/acceptance/test_self_construction_golden_route.py \
  tests/test_os_missions.py docs/design/mission_layer_self_construction_spec.md
git commit -m "feat(golden-route): persist reviewed patch receipts"
```

---

### Task 3: Make supersession relationships machine-verifiable

**Files:**
- Modify: `scripts/check_canon.py:432-470,1284-1305`
- Modify: `tests/test_canon_integrity.py`

**Interfaces:**
- Consumes: decision rows from `decision_registry.jsonl` and relationship rows from `supersession_registry.jsonl`.
- Produces: `_validate_supersessions(root, supersessions, decisions, findings) -> None`.
- Produces findings: `UNKNOWN_SUPERSESSION_DECISION`, `MISSING_SUPERSESSION_LINK`, and `INVALID_SUPERSESSION_SOURCE`.
- Produces atomic-ID recognition with
  `^ADR-\d{3}(?:-[A-Z][A-Z0-9-]*)?$`: ordinary IDs plus real partition IDs
  such as `ADR-076-A` and `ADR-077-BOUNDARY` are referentially checked, while
  historical prose labels containing spaces remain non-atomic labels.

- [ ] **Step 1: Write failing synthetic relationship tests**

First make the candidate's existing relationship atomic and valid: create
`docs/decisions/adr/adr_002_test.md`, add an `ADR-002` decision row with the
same ordinary fixture metadata as `ADR-001`, and make `SUPERSESSION-TEST`
`relation: SUPERSEDES`, `previous: ADR-001`, `new: ADR-002`, and
`source_path: docs/decisions/adr/adr_002_test.md`.

Create three fixture mutations from `_make_candidate(tmp_path)`:

```python
def test_supersession_rejects_unknown_decision_endpoint(tmp_path: Path) -> None:
    root = _make_candidate(tmp_path)
    rows = _read_jsonl(root / "docs/canon/supersession_registry.jsonl")
    rows[0]["new"] = "ADR-999"
    _write_jsonl(root / "docs/canon/supersession_registry.jsonl", rows)
    result = _run(root)
    assert result.returncode == 1
    assert "UNKNOWN_SUPERSESSION_DECISION" in result.stdout

def test_superseded_decision_requires_matching_relationship(tmp_path: Path) -> None:
    root = _make_candidate(tmp_path)
    decisions = _read_jsonl(root / "docs/canon/decision_registry.jsonl")
    decisions[0]["status"] = "SUPERSEDED"
    decisions[0]["supersession"] = ["ADR-002"]
    _write_jsonl(root / "docs/canon/decision_registry.jsonl", decisions)
    _write_jsonl(root / "docs/canon/supersession_registry.jsonl", [])
    result = _run(root)
    assert result.returncode == 1
    assert "MISSING_SUPERSESSION_LINK" in result.stdout

def test_supersession_source_path_must_exist(tmp_path: Path) -> None:
    root = _make_candidate(tmp_path)
    rows = _read_jsonl(root / "docs/canon/supersession_registry.jsonl")
    rows[0]["source_path"] = "docs/decisions/adr/missing.md"
    _write_jsonl(root / "docs/canon/supersession_registry.jsonl", rows)
    result = _run(root)
    assert result.returncode == 1
    assert "INVALID_SUPERSESSION_SOURCE" in result.stdout
```

Add a local `_read_jsonl(path)` test helper returning parsed rows. The unchanged
candidate must still pass.

Add two positive controls before implementation:

- `test_supersession_accepts_hyphenated_atomic_decision_ids` creates decision
  rows and relationships for `ADR-076-A` and `ADR-077-BOUNDARY` and expects the
  candidate to pass;
- `test_supersession_ignores_historical_composite_labels` uses
  `ADR-076 A and B` and `ADR-071 shell-selection placeholder`, with valid
  source files, and proves those prose labels are not reported as missing
  decision rows.

- [ ] **Step 2: Run the relationship tests and verify RED**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_canon_integrity.py -q \
  -k 'supersession_rejects or superseded_decision or supersession_source or hyphenated_atomic or composite_labels'
```

Expected: FAIL because `_validate_supersessions()` currently checks only field presence.

- [ ] **Step 3: Implement generic referential validation**

Import `re` and compile
`_ATOMIC_ADR_ID = re.compile(r"^ADR-\d{3}(?:-[A-Z][A-Z0-9-]*)?$")` near the
other validator constants. This accepts live IDs such as `ADR-076-A` and
`ADR-077-BOUNDARY` while deliberately excluding historical composite labels
such as `ADR-032 and ADR-033`, `ADR-076 A and B`, and
`ADR-071 shell-selection placeholder`; those remain relationship labels rather
than decision identifiers.

Build `decisions_by_id`, validate only atomic ADR endpoints, and require that a
superseded decision's declared successor has a matching `SUPERSEDES` row:

```python
def _validate_supersessions(
    root: Path,
    rows: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    findings: list[Finding],
) -> None:
    path = "docs/canon/supersession_registry.jsonl"
    required = {
        "id", "relation", "previous", "new", "scope", "date", "authority",
        "preserved", "annulled", "source_path",
    }
    decisions_by_id = {
        str(row["id"]): row
        for row in decisions
        if _is_non_empty_string(row.get("id"))
    }
    relationships: set[tuple[str, str]] = set()

    for row in rows:
        record_id = str(row.get("id", "unknown"))
        missing = sorted(key for key in required if key not in row)
        if missing:
            findings.append(Finding(
                "INCOMPLETE_SUPERSESSION", path,
                f"{record_id} missing: {', '.join(missing)}",
            ))
        previous = row.get("previous")
        successor = row.get("new")
        if _is_non_empty_string(previous) and _is_non_empty_string(successor):
            if row.get("relation") == "SUPERSEDES":
                relationships.add((previous, successor))
            for endpoint in (previous, successor):
                if _ATOMIC_ADR_ID.fullmatch(endpoint) and endpoint not in decisions_by_id:
                    findings.append(Finding(
                        "UNKNOWN_SUPERSESSION_DECISION", path,
                        f"{record_id} references unknown decision {endpoint}",
                    ))
        if not _safe_existing_relative_file(root, row.get("source_path")):
            findings.append(Finding(
                "INVALID_SUPERSESSION_SOURCE", path,
                f"{record_id} source_path is not an existing safe file",
            ))

    for decision_id, decision in decisions_by_id.items():
        if decision.get("status") != "SUPERSEDED":
            continue
        successors = decision.get("supersession")
        if not _is_non_empty_string_list(successors):
            findings.append(Finding(
                "MISSING_SUPERSESSION_LINK", path,
                f"{decision_id} is SUPERSEDED without successor ids",
            ))
            continue
        for successor in successors:
            if (decision_id, successor) not in relationships:
                findings.append(Finding(
                    "MISSING_SUPERSESSION_LINK", path,
                    f"{decision_id} declares {successor} without a SUPERSEDES row",
                ))
```

Change the call site to pass `root`, supersession rows, decision rows, and
`findings` in that order. Do not require composite or non-ADR historical labels
to appear in the decision registry.

- [ ] **Step 4: Run the full canon validator test suite**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_canon_integrity.py -q
set -o pipefail
set +e
PYTHONPATH=src .venv/bin/python scripts/check_canon.py --root . \
  | tee .superpowers/sdd/2026-08-02-atlas-canonical-decision-repair/pre-adr083-canon.txt
canon_rc="$?"
set -e
test "$canon_rc" -eq 1
```

Expected: pytest PASS. The live check fails only for the already-observed
pre-correction set: ADR-082 lacks its disposition, atomic endpoint ADR-011 is
missing from `decision_registry.jsonl`, and
`SUP-ADR-026-ADR-011-IDENTITY.source_path` names the nonexistent
`docs/decisions/adr/adr_026_hermes_adapter.md`. Record the exact findings in the
SDD artifact. Any other finding is a blocker. Task 4 repairs all three through
the one governed patch; do not add a validator exception for them.

- [ ] **Step 5: Commit the structural gate**

```bash
git add scripts/check_canon.py tests/test_canon_integrity.py
git commit -m "test(canon): enforce supersession relationships"
```

---

### Task 4: Build the exact ADR-083 canonical change in detached staging

**Files:**
- Modify in detached staging only: `ATLAS.md`
- Modify in detached staging only: `VISION.md`
- Modify in detached staging only: `ARCHITECTURE.md`
- Modify in detached staging only: `PROGRAMS.md`
- Modify in detached staging only: `PLAN.md`
- Modify in detached staging only: `STATUS.md`
- Modify in detached staging only: `docs/design/atlas_ecosystem_map.md`
- Modify in detached staging only: `docs/decisions/adr/adr_071_dedicated_apps_supersede_web_first_ux.md`
- Modify in detached staging only: `docs/decisions/adr/adr_078_atlas_workbench_lineage_convergence.md`
- Modify in detached staging only: `docs/decisions/adr/adr_082_mission_console_native_stack_selection.md`
- Create in detached staging only: `docs/decisions/adr/adr_083_supersede_uninformed_ui_stack_selection.md`
- Modify in detached staging only: `docs/canon/decision_dossiers/EDR-ADR-078-workbench-lineage.md`
- Create in detached staging only: `docs/canon/decision_dossiers/EDR-ADR-083-ui-canon-correction.md`
- Modify in detached staging only: `docs/backlog.yaml`
- Modify in detached staging only: `docs/canon/decision_registry.jsonl`
- Modify in detached staging only: `docs/canon/supersession_registry.jsonl`
- Modify in detached staging only: `docs/canon/conflict_registry.jsonl`
- Modify in detached staging only: `docs/canon/evidence_registry.jsonl`
- Modify in detached staging only: `docs/canon/decision_evidence_matrix.jsonl`
- Modify in detached staging only: `docs/canon/open_questions.jsonl`
- Modify in detached staging only: `docs/canon/product_lineage_registry.jsonl`
- Modify in detached staging only: `docs/canon/implementation_registry.yaml`
- Modify in detached staging only: `docs/canon/component_registry.jsonl`
- Modify in detached staging only: `docs/canon/capability_registry.jsonl`
- Modify in detached staging only: `docs/canon/component_reality_matrix.jsonl`
- Modify in detached staging only: `docs/INDEX.yaml`
- Create in detached staging only: `tests/test_adr_082_disposition.py`

**Interfaces:**
- Consumes: the reviewed-patch route from Task 2 and generic canon gate from Task 3.
- Produces: a single unified patch artifact containing the complete canonical disposition.
- Produces structured decision IDs `ADR-082` and `ADR-083`, relation ID `SUP-ADR-083-ADR-082`, evidence ID `EVD-LOCAL-ADR-083-CORRECTION`, and matrix ID `DEM-ADR-083-UI-CANON-CORRECTION`.

- [ ] **Step 1: Create detached staging without changing the implementation worktree**

Use the current branch HEAD, and keep the generated patch in this plan's SDD workspace:

```bash
plan_workspace=.superpowers/sdd/2026-08-02-atlas-canonical-decision-repair
staging_path="$plan_workspace/canon-staging"
patch_path="$plan_workspace/adr-083-canonical-disposition.patch"
git worktree add --detach "$staging_path" HEAD
```

Verify `git status --short` in the implementation worktree still contains no canonical doc changes.

- [ ] **Step 2: Write the complete repository acceptance test and prove RED before mutation**

Before editing any canonical document, create the complete
`tests/test_adr_082_disposition.py` shown in Step 9 below. Step 9 is its later
audit checklist, not permission to delay the test. Add assertions there for
the exact component/capability status map, the ADR-011 historical row, the
corrected ADR-026 source path, the recovery-spec evidence locator, and each U0
topology evidence branch described below. Run from staging:

```bash
PYTHONPATH="$PWD/src" /home/ronin/proyectos/atlas-core/.venv/bin/python -m pytest \
  tests/test_adr_082_disposition.py -q
```

Expected: FAIL on current ADR-082 status/stack, absent ADR-083/relation/evidence,
accepted component/capability claims, unresolved topology branches, missing
ADR-011 registry row, and the nonexistent ADR-026 relationship source. Save
the output under the ignored SDD workspace. If a required assertion is already
green, keep it as regression coverage but do not count it as RED.

- [ ] **Step 3: Correct every current human-facing authority projection**

Use `apply_patch` against staging. In `ATLAS.md`, `VISION.md`,
`ARCHITECTURE.md`, `PROGRAMS.md`, `PLAN.md`, and `STATUS.md`, replace each
current-tense claim that ADR-078/operator authority selected Atlas Engineering
Workbench, CodeOSS/VSCodium, or Android with a concise current-state statement:

```markdown
ADR-083 deja sin stack seleccionado la línea UI. ADR-078 y ADR-071 se conservan
como decisiones históricas pendientes de confirmación factual U0 sobre el host
desktop, el primer producto, Android y la topología de Mission Console. No hay
trabajo de construcción UI autorizado mientras U0 siga abierto.
```

Preserve factual descriptions of existing browser harnesses, source checkouts,
prototype code, measurements, and already-wired non-UI foundation. In `PLAN.md`
keep the R2 section but mark it `BLOCKED_BY_U0`; do not delete roadmap history.
In `STATUS.md`, render Workbench, CodeOSS/VSCodium, and Android as
`PROPOSED / REQUIRES_OPERATOR_CONFIRMATION`, not `ACCEPTED_DESIGN`.

In `docs/design/atlas_ecosystem_map.md`, keep the CodeOSS/VSCodium, Void, and
Zed rows as observed external sources, replace accepted-host/port authority
with `RESEARCH / U0_PENDING`, link ADR-083, and make the next action U0 rather
than Cut-2 implementation. Add the same historical-authority banner used for
ADR-078 to `EDR-ADR-078-workbench-lineage.md`; its evidence remains intact but
its recommendation is not current authority.

- [ ] **Step 4: Add minimal verification annotations to ADR-071, ADR-078, and ADR-082 in staging**

Use `apply_patch` against the staging paths. The annotations must say, without rewriting historical body text:

```markdown
> **Estado de autoridad desde ADR-083 (2026-08-02):** este documento se
> conserva como registro histórico. La vigencia actual del requisito Android
> requiere confirmación factual del operador; no se infiere de la etiqueta
> «aceptado» de este fichero.
```

For ADR-078, replace `requisito Android` with `elección CodeOSS/VSCodium como host desktop y su alcance`.

At the top of ADR-082 use:

```markdown
> **SUPERSEDED por ADR-083 (2026-08-02).** Este documento no constituye una
> selección vigente de stack. Se conserva como evidencia de una conclusión
> cerrada sin la confirmación informada requerida. Sus mediciones y prototipos
> solo conservan el alcance que demuestran sus artefactos fuente.
```

Change its status line to `superseded por ADR-083; sin stack sucesor seleccionado` and leave the original decision body visibly historical.

- [ ] **Step 5: Create ADR-083 with the complete correction contract**

The ADR must contain these sections and facts verbatim:

```markdown
# ADR-083 — Supersesión de la selección no informada de stack UI

- **Estado**: aceptado como corrección de canon; no selecciona stack
- **Fecha**: 2026-08-02
- **Supersede**: ADR-082, únicamente en su selección de Flutter y en las
  consecuencias que heredaban esa selección
- **No supersede automáticamente**: ADR-071, ADR-078, ADR-066 ni los work
  orders T2.1/T2.2/T2.3

## Evidencia de autoridad

Ante la pregunta de si la elección registrada por ADR-082 había sido una
decisión informada, el operador aclaró literalmente:

> «No, fue una sugerencia que yo acepte sin pensarlo mucho».

Hecho: la frase describe la aceptación que ADR-082 convirtió en selección de
stack. Inferencia limitada: esa aceptación no basta para fijar una decisión
tecnológica definitiva. La frase no selecciona Qt, Compose, Flutter,
CodeOSS/VSCodium ni otra alternativa, y tampoco confirma por sí sola Android.

## Decisión

1. ADR-082 queda `SUPERSEDED`; `selected_stack` vuelve a `null`.
2. Se conservan informes, prototipos y logs como evidencia con su alcance real.
3. La topología Workbench/Mission Console/Android y las plataformas vinculantes
   pasan a preguntas explícitas U0 antes de cualquier shortlist o build.
4. El baseline nulo —preservar las superficies existentes y no crear otra app—
   siempre forma parte de U0.
5. Si CodeOSS/VSCodium se confirma como desktop, no se repite una competición
   Flutter/Compose/Qt para desktop. Android se decide por separado.
6. Ningún trabajo T2.1/T2.2/T2.3 puede heredar un stack mientras U0 siga abierto.

## Corrección de evidencia

Las cifras comparables de los informes Linux son: Flutter 31.58 s de build,
aprox. 1.5 s de arranque y 186 MB RSS; Compose 89.8 s, aprox. 8.1 s y 282 MB;
Qt 3.68 s, aprox. 1.2 s y 134 MB. Son micro-PoC Linux con condiciones
documentadas, no evidencia de Android ni de producto completo. Qt requiere el
matiz de Qt 6.5+ para `MultiEffect`, no disponible en la prueba con Qt 6.4.2.

## Preguntas U0 pendientes

- ¿CodeOSS/VSCodium fue una elección consciente y sigue vigente?
- ¿Android es obligatorio, posterior o queda fuera?
- ¿Mission Console vive dentro del Workbench desktop, es proyección Android o
  constituye un producto adicional?
- ¿Qué flujos sin terminal, presupuestos y atributos visuales son vinculantes?

## Evidencia exigida según la disposición U0

- Si CodeOSS/VSCodium se confirma como host desktop, U0/U1 debe aportar una
  prueba de integración del host real, estrategia de empaquetado/actualización,
  matriz de extensiones y licencias, límites de aislamiento y un smoke del
  artefacto distribuible; un checkout o mock no basta.
- Si Android se confirma como producto o proyección, U0/U1 debe fijar el modo
  de emparejamiento, conducta offline/reconexión, frontera de permisos y
  secretos, y criterios de aceptación en al menos un dispositivo físico real;
  un PoC Linux no cuenta como evidencia Android.
- Si Mission Console se confirma como producto independiente, requiere su
  propia evaluación de alcance, journeys, presupuesto, accesibilidad,
  empaquetado y mantenimiento. No hereda automáticamente la decisión del host
  desktop ni la de Android.
- Si U0 elige el baseline nulo, la evidencia de cierre es una decisión explícita
  de preservar/diferir superficies y no se exige fabricar un prototipo nuevo.

## Consecuencias

- C1 corrige el canon; no autoriza construir UI.
- U0 puede terminar preservando o difiriendo superficies sin prototipos nuevos.
- F2.6 permanece pendiente y no se ejecuta hasta después de la última
  disposición UI y una autorización separada.
```

The ADR also links the three measurement reports and the approved recovery design spec.

- [ ] **Step 6: Create the evidence dossier and structured decision rows**

The dossier distinguishes `HECHO`, `INFERENCIA`, and `DESCONOCIDO`, lists the three report paths, and records the same Linux measurements and limitations.

Add/update decision rows with these exact semantic fields:

```json
{"id":"ADR-082","status":"SUPERSEDED","evidence_qualification":null,"selected_stack":null,"supersession":["ADR-083"],"authority":"HISTORICAL_REPOSITORY_ADR","proposed_disposition":"PRESERVE_AS_INVALIDATED_SELECTION_EVIDENCE"}
{"id":"ADR-083","status":"ACCEPTED_CANON_CORRECTION_NO_STACK_SELECTED","evidence_qualification":"PROVISIONAL","selected_stack":null,"supersession":[],"authority":"EXPLICIT_OPERATOR_CLARIFICATION","proposed_disposition":"RETAIN; RUN_U0_BEFORE_ANY_UI_STACK_DECISION"}
```

Each row retains all ordinary repository-ADR metadata and a `sources` entry pointing to its actual ADR file. Update ADR-078 to `status: OPERATOR_RECONFIRMATION_REQUIRED`, `authority: HISTORICAL_REPOSITORY_ADR_PENDING_CURRENT_CONFIRMATION`, and leave `evidence_qualification: PROVISIONAL`.

ADR-082 deliberately has `evidence_qualification: null`: `SUPERSEDED` is its
decision disposition, not a second evidence-matrix judgment. ADR-083 owns the
new `PROVISIONAL` evidence matrix.

Repair the two pre-existing Hermes referential defects in the same governed
patch, without fabricating a missing ADR file:

- add an `ADR-011` historical decision row with `date: 2026-05-23`,
  `status: RETIRED`, `authority: HISTORICAL_GATE_C_RECORD`,
  `implementation: RETIRED_BY_ADR_070`, and a source member
  `docs/decisions/gates/gate_c_seal.md` at the exact `ADR-011` locator. Compute
  that source file's SHA-256 from staging and bind its existing Git ref; do not
  reconstruct an `adr_011*.md` that never existed;
- change only `SUP-ADR-026-ADR-011-IDENTITY.source_path` to the live
  `docs/decisions/adr/adr_026_hermes_twin_architecture.md`. Preserve its
  relation semantics and other evidence.

The Step 2 acceptance test requires both repairs, and the post-patch generic
validator must report neither `UNKNOWN_SUPERSESSION_DECISION` nor
`INVALID_SUPERSESSION_SOURCE`.

Add the relation:

```json
{"id":"SUP-ADR-083-ADR-082","relation":"SUPERSEDES","previous":"ADR-082","new":"ADR-083","scope":"Flutter stack selection and every downstream claim that inherited it","date":"2026-08-02","authority":"explicit operator clarification approved through the Atlas integrity recovery design","preserved":["ADR-082 as historical evidence","all raw prototype code, logs and measured reports","independent scope of ADR-066, ADR-071 and ADR-078"],"annulled":["Flutter as definitive Atlas UI stack","Linux+Android single-codebase conclusion","automatic inheritance by T2.1, T2.2 or T2.3"],"source_path":"docs/decisions/adr/adr_083_supersede_uninformed_ui_stack_selection.md","source_ref":"GOLDEN_ROUTE_PROPOSAL"}
```

Add this exact evidence source:

```json
{"claim_scope":"The approved recovery design preserves the operator's exact clarification that ADR-082's acceptance was not an informed UI-stack selection; it does not identify a replacement stack or confirm Android. This is the durable local interaction record, not an independent reproduction of the conversation.","id":"EVD-LOCAL-ADR-083-CORRECTION","independence_key":"atlas-operator-clarification-20260802","kind":"LOCAL_CHECKOUT","locator":"docs/superpowers/specs/2026-08-02-atlas-integrity-recovery-program-design.md","program":"P08","retrieved_at":"2026-08-02","source_tier":1,"status":"ACTIVE","strength":"HIGH"}
```

ADR-083 is the decision that consumes this evidence and must not also be used
as its own evidence locator. The dossier calls out that limitation explicitly.

Mark `EVD-LOCAL-ADR-078` `HISTORICAL` and rewrite its claim scope to
`ADR-078 records CodeOSS/VSCodium as the Workbench host line; current informed operator confirmation and scope remain pending.` Keep its other provenance fields unchanged.

Change `DEM-ADR-078-WORKBENCH-LINEAGE.operator_decision_required` to `true`, keep it `PROVISIONAL`, and set its recommendation to `Reconfirm factually whether CodeOSS/VSCodium was an informed host choice and its current scope before implementation.` Add `DEM-ADR-083-UI-CANON-CORRECTION` with these exact semantics:

```json
{"alternatives":[{"disposition":"REJECTED","id":"PRESERVE_ADR_082","label":"Keep Flutter as the definitive stack despite the authority correction.","tradeoffs":["Would preserve continuity by treating an uninformed acceptance as binding."]},{"disposition":"REJECTED","id":"DELETE_ADR_082","label":"Delete ADR-082 and its evidence.","tradeoffs":["Would erase decision history and the provenance of inherited claims."]},{"disposition":"RECOMMENDED","id":"SUPERSEDE_WITHOUT_SELECTING_STACK","label":"Preserve ADR-082 historically, supersede its conclusion, and leave the stack unset.","tradeoffs":["Stops UI implementation until U0 resolves product topology and platform requirements."]}],"confidence":"HIGH","decision_id":"ADR-083","dossier":"docs/canon/decision_dossiers/EDR-ADR-083-ui-canon-correction.md","evidence_ids":["EVD-LOCAL-ADR-083-CORRECTION"],"falsifiers":["The operator corrects the quoted clarification or shows it did not refer to ADR-082's stack acceptance.","Primary evidence demonstrates a separate informed selection process before ADR-082 was accepted."],"id":"DEM-ADR-083-UI-CANON-CORRECTION","operator_decision_required":false,"program":"P08","recommendation":"Supersede ADR-082 without selecting a replacement stack; complete U0 before any UI implementation decision.","revisit_triggers":["The operator answers the U0 topology and platform questions.","New reproducible evidence changes the feasible UI alternatives."],"state":"PROVISIONAL"}
```

- [ ] **Step 7: Reopen authority questions and block inherited implementation claims**

Update the existing CodeOSS/product questions instead of creating duplicate
question IDs:

```json
{"id":"OPEN-OPERATOR-PRODUCT-SHELL","type":"operator_question","program":"P08","status":"REQUIRES_OPERATOR","question":"Was CodeOSS/VSCodium an informed desktop-host choice, and is it still current?","default_until_decided":"Preserve existing evidence and prototypes; do not implement or reject the host chain.","operator_decision_required":true,"blocking_work_order":"ADC-WO-101","available_after":[],"reopened_by":"ADR-083"}
{"id":"OPEN-OPERATOR-FIRST-PRODUCT","type":"operator_question","program":"P08","status":"REQUIRES_OPERATOR","question":"What, if anything, should be Atlas's first complete product target?","default_until_decided":"Preserve existing product lines without granting implementation priority to one of them.","operator_decision_required":true,"blocking_work_order":"ADC-WO-101","available_after":[],"reopened_by":"ADR-083"}
{"id":"OPEN-OPERATOR-MISSION-CONSOLE-TOPOLOGY","type":"operator_question","program":"P08","status":"REQUIRES_OPERATOR","question":"Is Mission Console part of the desktop Workbench, an Android projection, or an additional product?","default_until_decided":"Preserve current surfaces and build no additional application.","operator_decision_required":true,"blocking_work_order":"ADC-WO-101","available_after":[]}
```

Move the old `resolution`, `resolved_by`, and `resolved_at` values on the two
reopened rows to `historical_resolution`, `historical_resolved_by`, and
`historical_resolved_at`; history remains visible without masquerading as the
current answer. Change `OPEN-OPERATOR-ANDROID-WORKBENCH` to
`status: REQUIRES_OPERATOR`; its question first asks whether Android is
mandatory, later, or out of scope, and its default is preservation without
claiming a hard target.

Set `ADC-WO-101` to `REQUIRES_OPERATOR`, set
`operator_decision_required: true`, and describe CodeOSS/VSCodium, first-product
priority, and topology as unconfirmed. Keep `ADC-WO-109`, `ADC-WO-110`, and
`ADC-WO-111` blocked; set their operator-decision flags to true, add ADR-083 and
U0 confirmation to their dependencies, and remove claims that a host, product,
or Android target is already accepted.

In `docs/backlog.yaml`, set `t2-1-stack-decision-conclave` to `blocked` with ADR-083 as the reason, and make its acceptance U0 plus an explicit operator decision rather than a preselected contest. Set `t2-1-mission-console-dedicated-app` and `t2-2-knowledge-view-native` to `blocked` until U0 identifies their surface; keep `t2-3-visual-orchestrator-reopen-scope` pending/parked without a selected-stack dependency.

- [ ] **Step 8: Correct all derived product statuses**

In `conflict_registry.jsonl`, change `CONFLICT-P08-WORKBENCH-HOST`,
`CONFLICT-P08-FIRST-PRODUCT`, and `CONFLICT-P08-ANDROID-PROJECTION` to
`status: ELEVATED_TO_OPERATOR`, `resolution_status: ELEVATED_TO_OPERATOR`, and
`authority: ADR-083_PENDING_U0`. Their `resolution_note` must say the earlier
ADR-078/ADR-071 resolution is historical and name the corresponding U0
question; append ADR-083 to `evidence`.

In `product_lineage_registry.jsonl`, preserve every checkout/head/evidence
field. Change the two Void rows, CodeOSS row, and Zed row to
`disposition: RESEARCH_REFERENCE` and `target_cut: U0_PENDING`; append one
evidence string stating that ADR-083 preserves the checkout as evidence without
assigning a product role. The canonical Atlas lineages are untouched.

Apply this exact component/capability status map. These values already exist in
the respective registries; do not invent a new status vocabulary. Add
`operator_decision_required: true`, append an ADR-083 source, preserve research
and code evidence, and replace authority exactly as shown:

| ID | Status | Authority |
| --- | --- | --- |
| `CMP-ATLAS-IDE-VOID` | `OBSERVED_OR_UNKNOWN` | `REPOSITORY_EVIDENCE_ONLY_PENDING_U0` |
| `CMP-ZED-ACP` | `OBSERVED_OR_UNKNOWN` | `REPOSITORY_EVIDENCE_ONLY_PENDING_U0` |
| `CMP-CODEOSS-VSCODIUM-HOST` | `PROPOSED_DESIGN` | `HISTORICAL_ADR_078_PENDING_U0` |
| `CMP-ATLAS-ENGINEERING-WORKBENCH` | `PROPOSED_DESIGN` | `HISTORICAL_ADR_078_PENDING_U0` |
| `CMP-ANDROID-WORKBENCH` | `PROPOSED_DESIGN` | `HISTORICAL_ADR_071_PENDING_U0` |
| `CAP-ATLAS-WORKBENCH-PRODUCT` | `OBSERVED_OR_UNKNOWN` | `HISTORICAL_ADR_078_PENDING_U0` |
| `CAP-ANDROID-WORKBENCH-PROJECTION` | `OBSERVED_OR_UNKNOWN` | `HISTORICAL_ADR_071_PENDING_U0` |

Set each `proposed_disposition` to an explicit `RUN_U0_*` disposition matching
its subject; none may contain `ACCEPTED`, `IMPLEMENT`, or `BUILD_AFTER`.

In `component_reality_matrix.jsonl`, update the following exact UI-dependent
set. Remove `ACCEPTED_DESIGN`, preserve factual code/test/wiring states already
present, add `PROPOSED_DESIGN` and `CONTRADICTED`, include ADR-083 in
`decision`, and make `next_action` an exact U0 confirmation rather than a build
instruction:

```text
ATR-COMPONENT-1ED84824556D
ATR-COMPONENT-A38B63EDE712
ATR-COMPONENT-C496DDDB4517
CMP-PRESENCE-ENGINE
CMP-LIQUID-UI
CMP-ATLAS-IDE-VOID
CMP-ZED-ACP
CMP-CODEOSS-VSCODIUM-HOST
ATR-CAPABILITY-37936EC1A65F
ATR-CAPABILITY-54E8962DC0A3
ATR-CAPABILITY-F52440DE649B
CMP-ATLAS-ENGINEERING-WORKBENCH
CMP-ANDROID-WORKBENCH
CAP-ATLAS-WORKBENCH-PRODUCT
CAP-ANDROID-WORKBENCH-PROJECTION
```

Do not alter `CMP-ENGINEERING-FINDING-PLANE` or `CAP-ENGINEERING-FINDING`:
their code/test/wiring evidence is independent of selecting a UI product.
No row gains `CODE_PRESENT`, `WIRED`, `LIVE_VERIFIED`, or `PRODUCT_ACCEPTED`.

- [ ] **Step 9: Audit and complete the repository-level structured acceptance test**

The file was created RED in Step 2. Complete any assertions not already present;
it parses JSONL/YAML and asserts structure, not prose wording:

```python
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_STATUS_MAP = {
    "CMP-ATLAS-IDE-VOID": ("OBSERVED_OR_UNKNOWN", "REPOSITORY_EVIDENCE_ONLY_PENDING_U0"),
    "CMP-ZED-ACP": ("OBSERVED_OR_UNKNOWN", "REPOSITORY_EVIDENCE_ONLY_PENDING_U0"),
    "CMP-CODEOSS-VSCODIUM-HOST": ("PROPOSED_DESIGN", "HISTORICAL_ADR_078_PENDING_U0"),
    "CMP-ATLAS-ENGINEERING-WORKBENCH": ("PROPOSED_DESIGN", "HISTORICAL_ADR_078_PENDING_U0"),
    "CMP-ANDROID-WORKBENCH": ("PROPOSED_DESIGN", "HISTORICAL_ADR_071_PENDING_U0"),
    "CAP-ATLAS-WORKBENCH-PRODUCT": ("OBSERVED_OR_UNKNOWN", "HISTORICAL_ADR_078_PENDING_U0"),
    "CAP-ANDROID-WORKBENCH-PROJECTION": ("OBSERVED_OR_UNKNOWN", "HISTORICAL_ADR_071_PENDING_U0"),
}
UI_DEPENDENT_REALITY_IDS = {
    "ATR-COMPONENT-1ED84824556D",
    "ATR-COMPONENT-A38B63EDE712",
    "ATR-COMPONENT-C496DDDB4517",
    "CMP-PRESENCE-ENGINE",
    "CMP-LIQUID-UI",
    "CMP-ATLAS-IDE-VOID",
    "CMP-ZED-ACP",
    "CMP-CODEOSS-VSCODIUM-HOST",
    "ATR-CAPABILITY-37936EC1A65F",
    "ATR-CAPABILITY-54E8962DC0A3",
    "ATR-CAPABILITY-F52440DE649B",
    "CMP-ATLAS-ENGINEERING-WORKBENCH",
    "CMP-ANDROID-WORKBENCH",
    "CAP-ATLAS-WORKBENCH-PRODUCT",
    "CAP-ANDROID-WORKBENCH-PROJECTION",
}


def _jsonl(name: str) -> list[dict[str, object]]:
    path = ROOT / "docs" / "canon" / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _by_id(rows: list[dict[str, object]], record_id: str) -> dict[str, object]:
    return next(row for row in rows if row.get("id") == record_id)


def test_adr_082_is_superseded_without_a_replacement_stack() -> None:
    decisions = _jsonl("decision_registry.jsonl")
    adr_082 = _by_id(decisions, "ADR-082")
    adr_083 = _by_id(decisions, "ADR-083")
    assert adr_082["status"] == "SUPERSEDED"
    assert adr_082["selected_stack"] is None
    assert adr_082["supersession"] == ["ADR-083"]
    assert adr_083["selected_stack"] is None


def test_adr_082_supersession_is_structured() -> None:
    relation = _by_id(_jsonl("supersession_registry.jsonl"), "SUP-ADR-083-ADR-082")
    assert relation["previous"] == "ADR-082"
    assert relation["new"] == "ADR-083"
    assert relation["relation"] == "SUPERSEDES"


def test_preexisting_hermes_references_are_repaired_without_inventing_an_adr() -> None:
    decisions = _jsonl("decision_registry.jsonl")
    adr_011 = _by_id(decisions, "ADR-011")
    assert adr_011["status"] == "RETIRED"
    assert adr_011["sources"][0]["member"] == "docs/decisions/gates/gate_c_seal.md"
    relation = _by_id(
        _jsonl("supersession_registry.jsonl"),
        "SUP-ADR-026-ADR-011-IDENTITY",
    )
    assert relation["source_path"] == (
        "docs/decisions/adr/adr_026_hermes_twin_architecture.md"
    )


def test_operator_evidence_is_durable_and_not_circular() -> None:
    evidence = _by_id(
        _jsonl("evidence_registry.jsonl"),
        "EVD-LOCAL-ADR-083-CORRECTION",
    )
    assert evidence["locator"] == (
        "docs/superpowers/specs/"
        "2026-08-02-atlas-integrity-recovery-program-design.md"
    )
    assert "not an independent reproduction" in evidence["claim_scope"]


def test_component_and_capability_statuses_are_exactly_provisional() -> None:
    rows = _jsonl("component_registry.jsonl") + _jsonl("capability_registry.jsonl")
    for record_id, (status, authority) in REGISTRY_STATUS_MAP.items():
        row = _by_id(rows, record_id)
        assert (row["status"], row["authority"]) == (status, authority)
        assert row["operator_decision_required"] is True


def test_ui_work_orders_wait_for_operator_confirmation() -> None:
    registry = yaml.safe_load(
        (ROOT / "docs/canon/implementation_registry.yaml").read_text(encoding="utf-8")
    )
    work_orders = {row["id"]: row for row in registry["work_orders"]}
    assert work_orders["ADC-WO-101"]["status"] == "REQUIRES_OPERATOR"
    assert work_orders["ADC-WO-101"]["operator_decision_required"] is True
    assert work_orders["ADC-WO-109"]["status"] == "BLOCKED"
    assert work_orders["ADC-WO-110"]["status"] == "BLOCKED"
    assert work_orders["ADC-WO-111"]["status"] == "BLOCKED"


def test_ui_reality_rows_do_not_claim_accepted_design() -> None:
    rows = _jsonl("component_reality_matrix.jsonl")
    for record_id in UI_DEPENDENT_REALITY_IDS:
        row = _by_id(rows, record_id)
        assert "ACCEPTED_DESIGN" not in row["statuses"]
        assert "ADR-083" in row["decision"]


def test_ui_questions_and_conflicts_are_reopened() -> None:
    questions = _jsonl("open_questions.jsonl")
    for record_id in {
        "OPEN-OPERATOR-PRODUCT-SHELL",
        "OPEN-OPERATOR-FIRST-PRODUCT",
        "OPEN-OPERATOR-ANDROID-WORKBENCH",
        "OPEN-OPERATOR-MISSION-CONSOLE-TOPOLOGY",
    }:
        row = _by_id(questions, record_id)
        assert row["status"] == "REQUIRES_OPERATOR"
        assert row["operator_decision_required"] is True

    conflicts = _jsonl("conflict_registry.jsonl")
    for record_id in {
        "CONFLICT-P08-WORKBENCH-HOST",
        "CONFLICT-P08-FIRST-PRODUCT",
        "CONFLICT-P08-ANDROID-PROJECTION",
    }:
        row = _by_id(conflicts, record_id)
        assert row["resolution_status"] == "ELEVATED_TO_OPERATOR"


def test_ui_lineages_are_evidence_not_selected_roles() -> None:
    rows = _jsonl("product_lineage_registry.jsonl")
    for record_id in {
        "LINEAGE-VOID-BASELINE",
        "LINEAGE-VOID-FORWARD-PORT",
        "LINEAGE-CODEOSS-1-129-1",
        "LINEAGE-ZED",
    }:
        row = _by_id(rows, record_id)
        assert row["disposition"] == "RESEARCH_REFERENCE"
        assert row["target_cut"] == "U0_PENDING"


def test_root_authority_projections_link_adr_083() -> None:
    for name in {
        "ATLAS.md",
        "VISION.md",
        "ARCHITECTURE.md",
        "PROGRAMS.md",
        "PLAN.md",
        "STATUS.md",
    }:
        assert "ADR-083" in (ROOT / name).read_text(encoding="utf-8")


def test_adr_083_defines_evidence_for_every_u0_topology_branch() -> None:
    text = (
        ROOT / "docs/decisions/adr/"
        "adr_083_supersede_uninformed_ui_stack_selection.md"
    ).read_text(encoding="utf-8")
    for required in {
        "estrategia de empaquetado/actualización",
        "matriz de extensiones y licencias",
        "dispositivo físico real",
        "producto independiente",
        "baseline nulo",
    }:
        assert required in text
```

- [ ] **Step 10: Regenerate the docs index inside staging and verify the candidate**

Run from the detached staging worktree with the shared interpreter:

```bash
PYTHONPATH="$PWD/src" /home/ronin/proyectos/atlas-core/.venv/bin/python \
  scripts/docs_index_audit.py --write
PYTHONPATH="$PWD/src" /home/ronin/proyectos/atlas-core/.venv/bin/python -m pytest \
  tests/test_adr_082_disposition.py tests/test_canon_integrity.py \
  tests/test_docs_index_audit.py -q
PYTHONPATH="$PWD/src" /home/ronin/proyectos/atlas-core/.venv/bin/python \
  scripts/check_canon.py --root .
PYTHONPATH="$PWD/src" /home/ronin/proyectos/atlas-core/.venv/bin/python \
  scripts/docs_index_audit.py --strict
```

Expected: all commands PASS in staging. `docs/fixtures/` from the operator's main checkout is absent and must not be copied or indexed.

- [ ] **Step 11: Generate the immutable patch artifact mechanically**

Run from the implementation worktree:

```bash
git -C "$staging_path" add -N -- \
  docs/decisions/adr/adr_083_supersede_uninformed_ui_stack_selection.md \
  docs/canon/decision_dossiers/EDR-ADR-083-ui-canon-correction.md \
  tests/test_adr_082_disposition.py
git -C "$staging_path" diff --binary --output="$(pwd)/$patch_path" HEAD -- \
  ATLAS.md VISION.md ARCHITECTURE.md PROGRAMS.md PLAN.md STATUS.md \
  docs/decisions/adr docs/canon docs/backlog.yaml docs/INDEX.yaml \
  docs/design/atlas_ecosystem_map.md \
  tests/test_adr_082_disposition.py
test -s "$patch_path"
git apply --check "$patch_path"
```

`git add -N` is mandatory because `git diff` otherwise omits the three new
files. It records intent-to-add only inside disposable staging and does not put
their contents in any commit.

Review `git -C "$staging_path" diff --stat HEAD` and the full patch. Verify the
exact path set with `git -C "$staging_path" diff --name-only HEAD`; it may
contain only the files enumerated in this task. After `git apply --check`
succeeds and the artifact is preserved, remove disposable staging with
`git worktree remove --force "$staging_path"`. The force is scoped to that
detached worktree whose complete diff now exists in the immutable patch; retain
the patch in the ignored SDD workspace.

---

### Task 5: Submit, validate, approve, and apply ADR-083 through Golden Route

**Files:**
- Read generated artifact: `.superpowers/sdd/2026-08-02-atlas-canonical-decision-repair/adr-083-canonical-disposition.patch`
- Mutate only through existing ledgers under the configured Atlas/ColdUpdate state directories.
- Apply the governed patch to the implementation worktree through ColdUpdate.

**Interfaces:**
- Consumes CLI from Task 2.
- Produces a ColdUpdate proposal ID, validation report, approval record, applied commit, and Merkle receipts.

- [ ] **Step 1: Propose the exact patch and capture its runtime ID**

Use one persistent shell for Steps 1-4. Bind Atlas to this exact clean worktree
and an ignored, cut-local state directory before constructing any CLI object:

```bash
repo_root="$(git rev-parse --show-toplevel)"
test "$repo_root" = "$PWD"
test -z "$(git status --porcelain=v1 --untracked-files=all)"
expected_base="$(git rev-parse --verify HEAD^{commit})"
plan_workspace="$PWD/.superpowers/sdd/2026-08-02-atlas-canonical-decision-repair"
patch_path="$plan_workspace/adr-083-canonical-disposition.patch"
export ATLAS_CORE_ROOT="$PWD"
export ATLAS_HOME="$plan_workspace/atlas-home"
export PYTHONPATH="$PWD/src"

proposal_json="$(.venv/bin/atlas golden-route request \
  --patch "$patch_path" --json \
  'Supersede ADR-082 as an uninformed stack selection without selecting a replacement; preserve evidence and require U0 confirmation for CodeOSS, Android, and Mission Console topology.')"
proposal_id="$(printf '%s' "$proposal_json" | jq -er '.proposal_id')"
printf '%s\n' "$proposal_json"
printf 'proposal_id=%s\n' "$proposal_id"
test "$(printf '%s' "$proposal_json" | jq -er '.target_root')" = "$PWD"
test "$(printf '%s' "$proposal_json" | jq -er '.base_commit')" = "$expected_base"
test -z "$(git status --porcelain=v1 --untracked-files=all)"
```

Expected: JSON lists every canonical/test path, action `reviewed_patch`, the
exact root, and `base_commit == expected_base`. No commit or tracked/untracked
change may be introduced between request and apply. If HEAD changes for any
reason, reject/abandon this proposal and start again from a new clean base.

- [ ] **Step 2: Validate in ColdUpdate's isolated worktree**

In the same shell context, run and parse the persisted status from a fresh CLI
process:

```bash
.venv/bin/atlas update validate "$proposal_id"
validated_json="$(.venv/bin/atlas update status --id "$proposal_id")"
printf '%s\n' "$validated_json"
test "$(printf '%s' "$validated_json" | jq -er '.status')" = validated
test "$(printf '%s' "$validated_json" | jq -er '.base_commit')" = "$expected_base"
test "$(git rev-parse HEAD)" = "$expected_base"
```

Expected: proposal status `validated`, pytest and mypy pass, diff equals the reviewed patch. If validation fails, record the exact failure, reject or leave the proposal unapplied, repair the route/candidate, and create a new proposal. Never alter the stored patch after validation.

- [ ] **Step 3: Exercise the human gate using the operator's explicit execution authorization**

The operator approved the integrity-recovery design and explicitly said `Sí y ejecútala`. With the exact diff already reviewed and validation green, run:

```bash
.venv/bin/atlas update approve "$proposal_id"
approved_json="$(.venv/bin/atlas update status --id "$proposal_id")"
printf '%s\n' "$approved_json"
test "$(printf '%s' "$approved_json" | jq -er '.status')" = approved
test "$(git rev-parse HEAD)" = "$expected_base"
```

Expected: `approved`; no repository files changed yet.

- [ ] **Step 4: Apply through ColdUpdate and verify its scoped commit**

Run:

```bash
test "$(git rev-parse HEAD)" = "$expected_base"
apply_json="$(.venv/bin/atlas update apply "$proposal_id")"
printf '%s\n' "$apply_json"
applied_commit="$(printf '%s' "$apply_json" | jq -er '.applied_commit')"
apply_audit_ref="$(printf '%s' "$apply_json" | jq -er '.apply_audit_ref')"
test -n "$apply_audit_ref"
test "$applied_commit" = "$(git rev-parse HEAD)"
test "$(git rev-parse "$applied_commit^")" = "$expected_base"
test "$(printf '%s' "$apply_json" | jq -er '.status')" = applied
test "$(printf '%s' "$apply_json" | jq -er '.receipt.applied_commit')" = "$applied_commit"
test "$(printf '%s' "$apply_json" | jq -er '.receipt.apply_audit_ref')" = "$apply_audit_ref"
diff -u \
  <(printf '%s' "$apply_json" | jq -r '.files_touched[]' | sort) \
  <(git diff-tree --no-commit-id --name-only -r "$applied_commit" | sort)
test -z "$(git diff-tree --no-commit-id --name-only -r "$applied_commit" | rg '^(\.gitignore|docs/fixtures(?:/|$))' || true)"
git diff --check "$expected_base" "$applied_commit"
git show --stat --oneline --decorate --no-renames "$applied_commit"
```

Expected: ColdUpdate applies and commits only the persisted proposal paths;
the receipt, commit and Merkle reference agree across a fresh process.
`.gitignore` and `docs/fixtures/` remain absent. Any precondition, validation,
commit, audit, persistence, compensation or rollback failure stops the task;
`recovery_required`/`rollback_failed` is never reported as success and requires
manual recovery before any new proposal.

- [ ] **Step 5: Record the proposal and commit in the SDD report**

Record the runtime proposal ID, `expected_base`, applied SHA, validation
summary, Merkle audit reference, exact committed path list, and stable receipt
in the ignored SDD task report. Do not copy secrets or full environment values.
Remove only the cut-local `ATLAS_HOME` after all verification and only if no
proposal is in `recovery_required`/`rollback_failed`.

---

### Task 6: Verify C1 and record the operational correction

**Files:**
- Modify: `WORK_LEDGER.md` with a new top correction entry only; do not rewrite historical entries.
- Modify: `MEMORY.md` with one concise authority/provenance lesson.
- Modify: `docs/superpowers/specs/2026-08-02-atlas-integrity-recovery-program-design.md` with the dynamic C1 proposal/commit/audit evidence and remaining U0/F2.6 gates.
- Read: canonical files applied by Task 5.

**Interfaces:**
- Consumes: applied ADR-083 commit.
- Produces: fresh C1 verification evidence and the still-pending F2.6 notification.

- [ ] **Step 1: Add an operational correction entry without treating the ledger as authority**

Use `apply_patch` to add a dated top entry that says:

```markdown
- **2026-08-02 (C1 — corrección canónica ADR-082):** ADR-083 supersede la
  selección Flutter de ADR-082 sin elegir sustituto. La frase histórica que
  afirmaba una decisión definitiva no es autoridad vigente. CodeOSS/VSCodium,
  Android y la topología de Mission Console esperan confirmación U0; el daemon
  continúa detenido y F2.6 no se ha ejecutado.
```

Add one `MEMORY.md` line: an accepted suggestion is not evidence of an informed
technology choice; preserve the exact primary statement, separate inference,
and require factual confirmation before promoting inherited authority. Append
a C1 execution-evidence note to the approved recovery design containing the
proposal ID, base/applied SHAs, exact receipt path set and Merkle reference,
plus the honest statement that U0 and final F2.6 remain pending.

This is session/closure evidence, not part of the human canonical mutation.
The canonical effect must be its own ColdUpdate-created commit because its
dynamic receipt does not exist until after apply; this immediately following
closure commit binds the ledger/design/memory together without amending or
rewriting the governed commit:

```bash
git add WORK_LEDGER.md MEMORY.md \
  docs/superpowers/specs/2026-08-02-atlas-integrity-recovery-program-design.md
git diff --cached --check
git commit -m "docs(ops): record ADR-082 canonical correction"
```

- [ ] **Step 2: Run focused acceptance and canonical checks**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_adr_082_disposition.py \
  tests/test_canon_integrity.py \
  tests/test_docs_index_audit.py \
  tests/test_golden_route.py \
  tests/test_golden_route_wiring.py \
  tests/acceptance/test_self_construction_golden_route.py \
  tests/test_cold_update_patch_intake.py \
  tests/test_cold_update_manager.py -q
PYTHONPATH=src .venv/bin/python scripts/check_canon.py --root .
PYTHONPATH=src .venv/bin/python scripts/docs_index_audit.py --strict
MYPYPATH=src .venv/bin/python -m mypy \
  src/atlas/missions/golden_route.py \
  src/atlas/api/missions.py \
  src/atlas/api/server.py \
  src/atlas/core/cold_update_manager.py \
  src/atlas/interfaces/cli.py
```

Expected: all PASS.

- [ ] **Step 3: Search for stale active acceptance claims**

Run:

```bash
rg -n -i 'ADR-082|Flutter.*(definitiv|ganador|elegid|adopta)|stack.*Flutter|cónclave.*cerrado' \
  --glob '!docs/archive/**' --glob '!docs/fixtures/**' \
  --glob '!docs/superpowers/**' --glob '!work/**' --glob '!memory/**' \
  ATLAS.md VISION.md ARCHITECTURE.md PROGRAMS.md PLAN.md STATUS.md \
  docs/backlog.yaml docs/design docs/canon docs/decisions/adr
rg -n -i 'operator selected Atlas Engineering Workbench|accepted Workbench|accepted desktop|CURRENT_OPERATOR_DECISION.*(Code.?OSS|VSCodium)|ACCEPTED_DESIGN.*(Workbench|Code.?OSS|Android)' \
  ATLAS.md VISION.md ARCHITECTURE.md PROGRAMS.md PLAN.md STATUS.md \
  docs/backlog.yaml docs/design/atlas_ecosystem_map.md docs/canon
```

Classify every remaining match. Historical text is allowed only when the same
document visibly links ADR-083 or labels the resolution historical. No root
authority doc, backlog item, work order, question, conflict, decision,
capability, component, lineage, or UI-dependent reality row may present
Flutter, CodeOSS/VSCodium, Workbench priority, or Android scope as current
operator-confirmed authority.

- [ ] **Step 4: Query the expensive succession gate without running it**

Run:

```bash
PYTHONPATH=src .venv/bin/atlas f26 status --json | jq \
  '{status,last_run_sha,new_adrs_since,notification}'
```

Expected: `due`, with ADR-083 among new ADRs. Preserve and report the exact `notification`. Do not execute `atlas f26 run`; if `spawn_task` remains unavailable in the host, record that tool limitation explicitly.

- [ ] **Step 5: Confirm branch cleanliness and C1 completion state**

Run:

```bash
git status --short --branch
git log --oneline --decorate -8
git diff --check "$(git merge-base main HEAD)" HEAD
```

Expected: no uncommitted C1 files. Record `engineering_complete` for C1 only; `operator_gate_complete` remains false while U0 and final F2.6 are pending.
