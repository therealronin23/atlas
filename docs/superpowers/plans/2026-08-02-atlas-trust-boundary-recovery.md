# Atlas Trust-Boundary Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Recover Atlas's governance and permission trust boundaries through G1 and P1-P3 so an environmental data root cannot replace policy, ambiguous legacy permissions remain denied, every effective decision carries provenance, and invalid authorization state blocks every non-diagnostic effect.

**Architecture:** Package resources beside the imported atlas package are the trust anchor. A verified workspace governance snapshot and a strict local permission overlay are separate runtime artifacts. Digest-bound, no-follow migrations create their Merkle evidence before applying atomic writes. PermissionProfile evaluates one typed rule model with fixed precedence. AuthorizationStateProvider revalidates governance, permissions, migration markers, and the Merkle chain at effect time; AuthorizationGate is injected into the capability issuer and every public effect gateway. A checked-in executable inventory prevents new direct effects from bypassing classification.

**Tech Stack:** Python 3.11+, stdlib importlib.resources/hashlib/json/os/stat/tempfile/ast, Pydantic v2, PyYAML, Click, pytest, mypy strict, setuptools/uv, existing MerkleLogger.

## Global Constraints

- Implement only G1 and P1-P3 from docs/superpowers/specs/2026-08-02-atlas-integrity-recovery-program-design.md. Gate A, daemon reactivation, ADR/F2.6 work, UI selection, and all other cuts remain out of scope.
- Starting structural evidence is graph_commit=head=server_started_head=780b37a896f1673bd97ba214281c9b8a43f58186 with freshness=FRESH and source_tree_dirty=false. Before each task that changes production code, rebuild/query the graph and stop if those three SHAs do not equal the then-current HEAD.
- The requested graph name atlas.core.runtime_paths is not a live module. Its three required queries returned empty. The actual module is atlas.runtime_paths; its importers are atlas.api.server, atlas.core.orchestrator, atlas.interfaces.cli, and atlas.tools.editor.
- Preserve the operator's pre-existing .gitignore modification and untracked docs/fixtures directory. Never stage, edit, delete, or include them in a commit.
- Do not change the normative bytes of config/governance.json. Its inspected SHA-256 is d11c0926958b49cd153a7650472d5c557b47dc3445d5d0e1ef99db8ccf0355a8. A package resource may be an exact byte-for-byte copy and CI must enforce equality.
- ATLAS_CORE_ROOT, ATLAS_HOME, cwd, sysconfig data paths, and workspace files may select data, never a constitutional baseline.
- Do not add dependencies. Use importlib.resources and existing Pydantic/PyYAML.
- Never silently overwrite a DIVERGED or INVALID governance snapshot. Never auto-promote a legacy_unknown permission.
- Every mutation performed by a migration must use lstat/no-follow checks, expected owner, explicit 0700 directories and 0600 local files, a same-directory temporary, file fsync, os.replace, and directory fsync.
- Verify the existing Merkle chain before a migration effect. If the chain is empty, append a migration-genesis record before writing a governed artifact. A failed verification is a hard stop.
- All RED tests must fail for the named behavioral reason before production code changes. Run the stated GREEN command immediately after the minimum implementation.
- Keep commits scoped exactly as listed. Do not commit from this planning session; the commit commands below are for the implementing worker.
- Do not start atlas-core.service and do not run live provider, Telegram, MCP, browser, or external-network smokes in this plan.
- A task is not complete with skipped or xfailed acceptance tests. No P3 family may remain pending.
- A health check at a long-running public entrypoint is not a lease. Revalidate
  immediately before every direct external sink; a multi-effect operation
  checks each family at its corresponding sink. Only cleanup of resources
  acquired by an already-authorized transaction may proceed without a new
  check, and that exemption must be explicit in the inventory.

## Structural Evidence and Blast Radius

The graph-first preflight produced the following implementation boundary:

| Module queried | Direct importers | Transitive blast radius |
| --- | --- | --- |
| atlas.governance.permission_profile | atlas.core.orchestrator; atlas.core.orchestrator_parts.approvals; atlas.security.capabilities; atlas.security.executor; atlas.tools.editor | approvals; service_runner; capabilities; agentic_executor; editor; atlas_coder; incremental_coder; gate_f_executor; CLI; executor; orchestrator; maintenance_facade; pipeline_runner; parallel_coder; f26_agentic_dispatch; self_build_runner; dashboard; tool_coder |
| atlas.security.capabilities | atlas.core.orchestrator; atlas.core.orchestrator_parts.pipeline_runner; atlas.security.executor; atlas.tools.editor | orchestrator; maintenance_facade; pipeline_runner; parallel_coder; f26_agentic_dispatch; self_build_runner; dashboard; tool_coder; agentic_executor; service_runner; atlas_coder; incremental_coder; gate_f_executor; CLI; executor; editor |
| atlas.core.runtime_paths | none; node does not exist | none; node does not exist |
| atlas.runtime_paths | atlas.api.server; atlas.core.orchestrator; atlas.interfaces.cli; atlas.tools.editor | service_runner; editor; atlas_coder; incremental_coder; gate_f_executor; CLI; API server; agentic_executor; orchestrator; maintenance_facade; pipeline_runner; parallel_coder; f26_agentic_dispatch; self_build_runner; dashboard; tool_coder |
| atlas.core.orchestrator | agentic_executor; maintenance_facade; pipeline_runner; f26_agentic_dispatch; CLI; dashboard; service_runner | tool_coder; service_runner; atlas_coder; incremental_coder; CLI; code_cycle; agentic_executor; orchestrator; maintenance_facade; pipeline_runner; parallel_coder; f26_agentic_dispatch; self_build_runner; dashboard |

The implementation must use this set as the minimum P3 inventory surface, then augment it with AST-discovered direct sinks across src/atlas.

---

## G1 — Package-Owned Governance Root

### Task 1: Package the constitutional baseline beside imported code

**Files:**

- Create: src/atlas/governance/resources/__init__.py
- Create: src/atlas/governance/resources/governance-v1.0.0.json
- Create: src/atlas/governance/resources/manifest.json
- Create: src/atlas/governance/trust_root.py
- Modify: pyproject.toml
- Test: tests/test_governance_trust_root.py

**Interfaces**

- Consumes: importlib.resources.files("atlas.governance.resources"), exact config/governance.json bytes.
- Produces:

~~~python
@dataclass(frozen=True)
class GovernanceBaseline:
    version: str
    sha256: str
    resource: str
    source: str
    raw: bytes

def load_governance_baseline() -> GovernanceBaseline:
    """Load and digest the manifest-selected package resource."""
~~~

- manifest.json is exactly:

~~~json
{
  "schema_version": 1,
  "governance": {
    "current": {
      "version": "1.0.0",
      "resource": "governance-v1.0.0.json",
      "sha256": "d11c0926958b49cd153a7650472d5c557b47dc3445d5d0e1ef99db8ccf0355a8"
    },
    "history": []
  }
}
~~~

- [ ] Write tests proving the resource digest is exact, the resource bytes equal config/governance.json, and ATLAS_CORE_ROOT pointing at an adversarial governance.json does not change load_governance_baseline().

~~~python
def test_environmental_data_root_cannot_replace_governance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hostile = tmp_path / "hostile"
    (hostile / "config").mkdir(parents=True)
    (hostile / "config" / "governance.json").write_text('{"version":"evil"}')
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(hostile))

    baseline = load_governance_baseline()

    assert baseline.version == "1.0.0"
    assert baseline.sha256 == "d11c0926958b49cd153a7650472d5c557b47dc3445d5d0e1ef99db8ccf0355a8"
    assert b'"data_sovereignty"' in baseline.raw
~~~

- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_governance_trust_root.py -q
~~~

Expected: collection fails because atlas.governance.trust_root and its package resources do not exist.

- [ ] Copy config/governance.json byte-for-byte to the resource, add manifest.json, and add this package-data declaration:

~~~toml
[tool.setuptools.package-data]
"atlas.interfaces" = ["templates/*.html"]
"atlas.governance.resources" = ["*.json", "*.yaml"]
~~~

- [ ] Implement load_governance_baseline() so it rejects a missing resource, malformed manifest, digest mismatch, or governance schema mismatch with GovernanceBaselineError. It must never consult atlas_data_root().
- [ ] Read manifest.json and its selected package resource through importlib.resources.as_file(); lstat each before opening, reject links/non-regular files, require st_uid in {0, os.geteuid()} and mode & 0o022 == 0, and open with O_RDONLY | O_NOFOLLOW. Editable installs and ordinary unpacked wheel installs must take the same path.
- [ ] Run GREEN:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_governance_trust_root.py -q
~~~

- [ ] Commit:

~~~bash
git add src/atlas/governance/resources src/atlas/governance/trust_root.py pyproject.toml tests/test_governance_trust_root.py
git commit -m "security: anchor governance in package resources"
~~~

### Task 2: Classify the workspace snapshot without following links

**Files:**

- Modify: src/atlas/governance/trust_root.py
- Test: tests/test_governance_trust_root.py

**Interfaces**

~~~python
class GovernanceSnapshotStatus(str, Enum):
    ABSENT = "absent"
    CURRENT = "current"
    DIVERGED = "diverged"
    INVALID = "invalid"

@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int
    mode: int
    uid: int
    gid: int

@dataclass(frozen=True)
class GovernanceSnapshot:
    status: GovernanceSnapshotStatus
    path: Path
    baseline_version: str
    baseline_sha256: str
    snapshot_version: str | None
    snapshot_sha256: str | None
    identity: FileIdentity | None
    reason: str

def inspect_governance_snapshot(
    path: Path,
    baseline: GovernanceBaseline,
    *,
    expected_uid: int | None = None,
) -> GovernanceSnapshot:
    """Inspect parent and snapshot with lstat/O_NOFOLLOW and validate JSON."""
~~~

- Parent directory policy: regular directory, not symlink, owner expected_uid or os.geteuid(), exact mode 0700.
- Snapshot policy when present: regular file, not symlink, same owner, exact mode 0600, bounded to 1 MiB, opened with O_RDONLY | O_NOFOLLOW.
- A safe, parseable, schema-valid snapshot with a different digest is DIVERGED. Unsafe topology, ownership, mode, malformed JSON, missing required keys, or unknown top-level keys is INVALID.

- [ ] Add one parametrized RED test for ABSENT, CURRENT, DIVERGED, malformed JSON, mode 0644, foreign-owner result via injected expected_uid, snapshot symlink, and symlinked config directory.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_governance_trust_root.py -q -k snapshot
~~~

Expected: GovernanceSnapshotStatus and inspect_governance_snapshot are missing.

- [ ] Implement the enum, immutable records, strict GovernanceDocument Pydantic model, and no-follow reader. Do not call Path.resolve() before lstat because that would erase symlink evidence.
- [ ] Run GREEN:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_governance_trust_root.py -q -k snapshot
~~~

- [ ] Commit:

~~~bash
git add src/atlas/governance/trust_root.py tests/test_governance_trust_root.py
git commit -m "security: classify governance snapshots fail closed"
~~~

### Task 3: Create digest-bound dry-run plans and atomic migration

**Files:**

- Create: src/atlas/governance/secure_files.py
- Create: src/atlas/governance/governance_migration.py
- Modify: src/atlas/governance/trust_root.py
- Modify: src/atlas/logging/merkle_logger.py
- Test: tests/test_governance_migration.py

**Interfaces**

~~~python
class GovernanceMigrationAction(str, Enum):
    BOOTSTRAP = "bootstrap"
    UPGRADE = "upgrade"
    REFUSE = "refuse"

@dataclass(frozen=True)
class GovernanceMigrationPlan:
    action: GovernanceMigrationAction
    snapshot_path: Path
    backup_path: Path | None
    marker_path: Path
    before_version: str | None
    before_sha256: str | None
    before_identity: FileIdentity | None
    after_version: str
    after_sha256: str
    package_source: str
    reason: str
    plan_sha256: str

@dataclass(frozen=True)
class GovernanceMigrationReceipt:
    action: GovernanceMigrationAction
    snapshot_path: str
    backup_path: str | None
    before_version: str | None
    before_sha256: str | None
    after_version: str
    after_sha256: str
    package_source: str
    validation: str
    intent_audit_hash: str
    outcome_audit_hash: str

def plan_governance_migration(
    snapshot: GovernanceSnapshot,
    baseline: GovernanceBaseline,
    *,
    known_history: Mapping[str, str],
) -> GovernanceMigrationPlan:
    """Permit ABSENT or a digest in known_history; refuse unknown divergence."""

def apply_governance_migration(
    plan: GovernanceMigrationPlan,
    *,
    baseline: GovernanceBaseline,
    merkle: MerkleLogger,
    expected_uid: int | None = None,
) -> GovernanceMigrationReceipt:
    """Reverify plan inputs and Merkle, then backup/write/fsync/rename/audit."""

def recover_governance_migration(
    workspace: Path,
    *,
    action: Literal["finish", "rollback"],
    expected_plan_sha256: str,
    merkle: MerkleLogger,
) -> GovernanceSnapshot:
    """Finish verified artifacts or restore the exact pre-migration backup."""

def atomic_write_private(path: Path, data: bytes, *, expected_uid: int) -> None:
    """Same-directory 0600 temporary, fsync file, os.replace, fsync parent."""

def open_secure_merkle_logger(
    log_dir: Path,
    *,
    create: bool,
    expected_uid: int | None = None,
) -> MerkleLogger:
    """Open/create a 0700 no-follow audit root before MerkleLogger touches it."""
~~~

- [ ] Write RED tests for: empty-chain genesis precedes snapshot write; corrupt Merkle blocks before write; a `governance.migration.planned` record precedes the first marker/backup/snapshot mutation; known historical digest upgrades with a 0600 backup; unknown DIVERGED refuses; changed inode/digest between plan and apply refuses; destination/backup/marker/audit-directory symlink refuses before mkdir/chmod/open; foreign-owned or group/world-writable audit roots refuse without mutation; injected failure before os.replace preserves the original; interruption after os.replace but before the applied audit leaves a detectable marker and blocks boot; finish and rollback recovery each audit intent before their first mutation; receipt contains old/new version/digest/source/validation and both audit hashes.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_governance_migration.py -q
~~~

Expected: governance_migration and secure_files modules are missing.

- [ ] Add governance.migration.genesis, governance.migration.planned, governance.migration.applied, governance.migration.recovery_planned, governance.migration.finished, and governance.migration.rolled_back to AUDIT_ACTIONS. Implement open_secure_merkle_logger() with component-by-component lstat, expected ownership, O_NOFOLLOW directory/file opens, exact 0700/0600 modes, and no mutation of an existing unsafe object; migration and recovery callers must not construct MerkleLogger directly.
- [ ] Implement canonical JSON hashing for plan_sha256. apply_governance_migration() must reload and digest the package baseline, re-inspect the snapshot, compare FileIdentity and digest to the plan, call merkle.verify_chain(), append genesis when record_count == 0, and append a redacted `governance.migration.planned` record bound to `plan_sha256` **before** atomically writing config/.governance-migration.pending or any backup/snapshot byte. Store that intent hash in the marker. After the effect, append the applied outcome, then unlink the marker and fsync config/; the initial intent covers that transaction cleanup.
- [ ] Name backups governance.json.backup-<full-before-sha256>. A pre-existing backup is accepted only when it is a secure regular 0600 file with exactly the planned digest.
- [ ] inspect_governance_snapshot() maps a present secure marker to INVALID with reason incomplete governance migration. recover_governance_migration() binds to marker plan_sha256, verifies Merkle, appends a redacted `governance.migration.recovery_planned` intent before its first mutation, and either verifies/completes the new snapshot and outcome receipt or atomically restores the exact backup; it never accepts a caller-supplied replacement payload.
- [ ] Make rollback semantics action-specific and digest-bound: BOOTSTRAP has no backup, so rollback must lstat the destination, require its digest/identity to match the marker's planned post-image, append recovery intent, unlink only that newly installed snapshot, fsync config/, append the rollback outcome, and remove the marker; UPGRADE must instead verify the exact 0600 backup named in the marker, append recovery intent, atomically restore it, append the outcome, and remove the marker. Every marker removal is part of the already-audited transaction and its parent directory is fsynced.
- [ ] Run GREEN:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_governance_migration.py -q
~~~

- [ ] Commit:

~~~bash
git add src/atlas/governance/secure_files.py src/atlas/governance/governance_migration.py src/atlas/governance/trust_root.py src/atlas/logging/merkle_logger.py tests/test_governance_migration.py
git commit -m "security: add audited governance migration"
~~~

### Task 4: Expose recovery CLI without constructing Orchestrator

**Files:**

- Modify: src/atlas/interfaces/cli.py
- Test: tests/test_governance_cli.py

**Interfaces**

~~~text
atlas governance status --workspace PATH --json
atlas governance migrate --workspace PATH --json
atlas governance migrate --workspace PATH --apply --expected-plan-sha256 SHA256 --json
atlas governance recover --finish|--rollback --workspace PATH --expected-plan-sha256 SHA256 --json
~~~

- [ ] Write CliRunner RED tests proving status and dry-run work against DIVERGED/INVALID snapshots without get_orchestrator(), apply rejects a missing or stale expected-plan-sha256, recover binds to the marker digest for finish/rollback, an audit-root symlink/foreign owner/unsafe mode is rejected before mutation, and output identifies package:atlas.governance.resources/governance-v1.0.0.json without exposing raw policy bytes.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_governance_cli.py -q
~~~

Expected: no such command governance.

- [ ] Implement the Click group. status and dry-run are read-only. Apply/recover call `open_secure_merkle_logger(workspace / "memory" / "audit", create=True)`—never `MerkleLogger(...)` directly—require the exact plan digest printed by dry-run or stored in the marker, and pass that verified logger to apply_governance_migration()/recover_governance_migration().
- [ ] Run GREEN:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_governance_cli.py -q
~~~

- [ ] Commit:

~~~bash
git add src/atlas/interfaces/cli.py tests/test_governance_cli.py
git commit -m "feat: expose governance recovery commands"
~~~

### Task 5: Reorder Orchestrator bootstrap and remove environmental governance copy

**Files:**

- Modify: src/atlas/core/orchestrator.py
- Modify: src/atlas/governance/governance_l0.py
- Modify: src/atlas/logging/merkle_logger.py
- Modify: src/atlas/runtime_paths.py
- Replace: tests/test_orchestrator_permissions_sync.py
- Modify: tests/test_atlas_core.py

**Interfaces**

~~~python
@classmethod
def initialize(
    cls,
    *,
    baseline: GovernanceBaseline,
    snapshot_path: Path,
) -> GovernanceL0:
    """Initialize immutable in-memory state from trusted baseline bytes."""
~~~

- [ ] Replace the obsolete overwrite test with RED tests proving: Orchestrator creates Merkle before an ABSENT bootstrap; adversarial ATLAS_CORE_ROOT does not affect the snapshot; DIVERGED and INVALID are never overwritten; GovernanceL0 state comes from baseline.raw; check_file_integrity compares the runtime snapshot to baseline.sha256.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_orchestrator_permissions_sync.py tests/test_atlas_core.py -q -k "governance or bootstrap"
~~~

Expected: current _copy_defaults overwrites the hostile/diverged snapshot and initializes GovernanceL0 before Merkle verification.

- [ ] Split bootstrap into phases. First open only the minimal audit root with `open_secure_merkle_logger(create=True)` and verify the chain; do not construct ObservabilityStack, WAL, MicroLedger, schedulers, transports, or other collaborators yet. Load the package baseline, inspect governance, and automatically apply only ABSENT bootstrap through its audited migration. Initialize GovernanceL0 from baseline bytes only after the snapshot becomes CURRENT. In this G1 commit, append a `runtime.bootstrap.planned` record before constructing the still-legacy downstream components; Task 12 replaces permission loading and Task 21 moves the final downstream-construction boundary behind combined VALID authorization.
- [ ] Replace broad `_init_dirs()` with a minimal no-follow bootstrap. It may create the workspace plus `memory/audit` before a logger exists only through the narrowly inventoried `open_secure_merkle_logger` trust primitive; the first record states whether those roots were created. Existing symlink, foreign-owned, or group/world-writable components fail without chmod/mutation. `config/` and every non-audit runtime directory are created only after an audit intent exists, at exact 0700, and are re-lstatted before use.
- [ ] Add `audit.root_bootstrapped` and `runtime.bootstrap.planned` to `AUDIT_ACTIONS`; in this G1 task tests assert no Observability/WAL/MicroLedger path exists when governance is DIVERGED/INVALID. Permission INVALID/UNMIGRATED does not exist until Tasks 8-12 and is covered when Task 21 finalizes the combined bootstrap boundary.
- [ ] Remove governance copying and _write_default_governance(). Rename atlas_data_root() documentation to state that it resolves non-constitutional data only; do not change its fixture behavior in this task.
- [ ] A DIVERGED or INVALID snapshot raises GovernanceBootstrapRequired with the exact dry-run CLI command. Do not catch it as a warning.
- [ ] Run GREEN:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_orchestrator_permissions_sync.py tests/test_atlas_core.py -q
~~~

- [ ] Commit:

~~~bash
git add src/atlas/core/orchestrator.py src/atlas/governance/governance_l0.py \
  src/atlas/logging/merkle_logger.py src/atlas/runtime_paths.py \
  tests/test_orchestrator_permissions_sync.py tests/test_atlas_core.py
git commit -m "security: bootstrap governance before runtime components"
~~~

### Task 6: Verify editable and installed-wheel trust roots

**Files:**

- Modify: .github/workflows/ci.yml
- Modify: tests/test_audit_runner_and_ci.py
- Modify: pyproject.toml
- Test: tests/test_governance_wheel_contract.py

- [ ] Write RED tests that inspect pyproject package-data and CI, requiring the wheel smoke to call load_governance_baseline(), compare the embedded digest, unset ATLAS_CORE_ROOT/ATLAS_HOME/PYTHONPATH, and bootstrap a temporary workspace with mode 0700.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_governance_wheel_contract.py tests/test_audit_runner_and_ci.py -q
~~~

Expected: CI still treats share/atlas-core/config/governance.json as the authority.

- [ ] Remove config/governance.json from tool.setuptools.data-files while retaining config/permissions.yaml temporarily for P1 legacy compatibility. Update wheel smoke to load the package resource and assert its exact digest/source.
- [ ] Add the isolated acceptance sequence:

~~~bash
uv build --wheel --out-dir dist
tmp_venv="$(mktemp -d)/venv"
uv venv "$tmp_venv" --python 3.11
uv pip install --python "$tmp_venv/bin/python" --no-deps dist/atlas_core-*.whl
env -u ATLAS_CORE_ROOT -u ATLAS_HOME -u PYTHONPATH "$tmp_venv/bin/python" -c "from atlas.governance.trust_root import load_governance_baseline; assert load_governance_baseline().sha256 == 'd11c0926958b49cd153a7650472d5c557b47dc3445d5d0e1ef99db8ccf0355a8'"
~~~

- [ ] Run GREEN:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_governance_wheel_contract.py tests/test_audit_runner_and_ci.py -q
~~~

- [ ] Commit:

~~~bash
git add .github/workflows/ci.yml pyproject.toml tests/test_audit_runner_and_ci.py tests/test_governance_wheel_contract.py
git commit -m "ci: verify wheel-owned governance baseline"
~~~

---

## P1 — Permission Schema and Migration

### Task 7: Define strict schema v2 and package-owned permission baseline

**Files:**

- Create: src/atlas/governance/permission_schema.py
- Create: src/atlas/governance/resources/permissions-v2.yaml
- Modify: src/atlas/governance/resources/manifest.json
- Modify: src/atlas/governance/permission_profile.py
- Test: tests/test_permission_schema_v2.py

**Interfaces**

~~~python
class PermissionLevel(str, Enum):
    AUTO = "auto"
    CONFIRM = "confirm"
    APPROVE = "approve"
    BLOCKED = "blocked"

class EffectKind(str, Enum):
    PATH_READ = "path_read"
    PATH_WRITE = "path_write"
    SHELL = "shell"
    NETWORK = "network"
    PROVIDER = "provider"
    MCP = "mcp"
    TRANSPORT = "transport"
    MESSAGING = "messaging"
    LOCAL_LISTENER = "local_listener"
    RECOVERY_DIAGNOSTIC = "recovery_diagnostic"

class MatchKind(str, Enum):
    WORKSPACE_PREFIX = "workspace_prefix"
    HOME_PREFIX = "home_prefix"
    ABSOLUTE_PREFIX = "absolute_prefix"
    COMMAND_EXACT = "command_exact"
    COMMAND_PREFIX = "command_prefix"
    REGEX = "regex"
    DOMAIN_EXACT = "domain_exact"
    NAME_EXACT = "name_exact"
    ANY = "any"

class PermissionRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    effects: tuple[EffectKind, ...]
    matcher: MatchKind
    target: str
    level: PermissionLevel

class GrantScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    effects: tuple[EffectKind, ...]
    matcher: MatchKind
    target: str
    maximum_level: PermissionLevel

class PermissionBaselineV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[2]
    policy_version: str
    hard_blocks: tuple[PermissionRule, ...]
    zones: tuple[PermissionRule, ...]
    grantable_allows: tuple[GrantScope, ...]
    mandatory_revocations: tuple[PermissionRule, ...]
    baseline_allows: tuple[PermissionRule, ...]
    recovery_diagnostics: tuple[PermissionRule, ...]

class TelegramLocalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    authorized_chat_ids: tuple[int, ...] = ()
    authorized_user_ids: tuple[int, ...] = ()
    require_passphrase_for_approve: bool = False
    passphrase_hash: str = ""

class LocalPermissionRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    effects: tuple[EffectKind, ...]
    matcher: MatchKind
    target: str
    level: PermissionLevel
    scope_id: str

class LocalDenyRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    effects: tuple[EffectKind, ...]
    matcher: MatchKind
    target: str
    level: Literal[PermissionLevel.BLOCKED] = PermissionLevel.BLOCKED

class LegacyUnknown(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    source_field: str
    canonical_value_json: str
    value_sha256: str
    status: Literal["denied"] = "denied"

class LocalPermissionsOverlayV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[2]
    created_against_policy_version: str
    grants: tuple[LocalPermissionRule, ...] = ()
    denies: tuple[LocalDenyRule, ...] = ()
    read_extended: tuple[str, ...] = ()
    telegram: TelegramLocalConfig = TelegramLocalConfig()
    legacy_unknown: tuple[LegacyUnknown, ...] = ()
~~~

**Exact permissions-v2.yaml resource**

~~~yaml
schema_version: 2
policy_version: "2.0.0"
hard_blocks:
  - id: hard.path.home.ssh
    effects: [path_read, path_write]
    matcher: home_prefix
    target: .ssh
    level: blocked
  - id: hard.path.home.gnupg
    effects: [path_read, path_write]
    matcher: home_prefix
    target: .gnupg
    level: blocked
  - id: hard.path.home.aws
    effects: [path_read, path_write]
    matcher: home_prefix
    target: .aws
    level: blocked
  - id: hard.path.etc
    effects: [path_read, path_write]
    matcher: absolute_prefix
    target: /etc
    level: blocked
  - id: hard.path.root
    effects: [path_read, path_write]
    matcher: absolute_prefix
    target: /root
    level: blocked
  - id: hard.path.boot
    effects: [path_read, path_write]
    matcher: absolute_prefix
    target: /boot
    level: blocked
  - id: hard.path.proc
    effects: [path_read, path_write]
    matcher: absolute_prefix
    target: /proc
    level: blocked
  - id: hard.path.dev
    effects: [path_read, path_write]
    matcher: absolute_prefix
    target: /dev
    level: blocked
  - id: hard.shell.chain
    effects: [shell]
    matcher: regex
    target: '(?:[;|]|&&|\|\||`|\$\(|\$\{|<\(|>\(|\n|\r)'
    level: blocked
zones:
  - id: zone.workspace.read
    effects: [path_read]
    matcher: workspace_prefix
    target: .
    level: auto
  - id: zone.workspace.tmp.write
    effects: [path_write]
    matcher: workspace_prefix
    target: tmp
    level: auto
  - id: zone.workspace.projects.write
    effects: [path_write]
    matcher: workspace_prefix
    target: projects
    level: confirm
  - id: zone.workspace.skills.write
    effects: [path_write]
    matcher: workspace_prefix
    target: skills
    level: confirm
  - id: zone.workspace.memory.write
    effects: [path_write]
    matcher: workspace_prefix
    target: memory
    level: confirm
grantable_allows:
  - id: scope.external.read
    effects: [path_read]
    matcher: absolute_prefix
    target: /
    maximum_level: confirm
  - id: scope.workspace.write
    effects: [path_write]
    matcher: workspace_prefix
    target: .
    maximum_level: approve
  - id: scope.shell.command
    effects: [shell]
    matcher: any
    target: "*"
    maximum_level: approve
mandatory_revocations:
  - id: revoke.governance.write
    effects: [path_write]
    matcher: workspace_prefix
    target: config/governance.json
    level: blocked
  - id: revoke.git.apply
    effects: [shell]
    matcher: command_prefix
    target: "git:apply:"
    level: blocked
  - id: revoke.git.push
    effects: [shell]
    matcher: command_prefix
    target: "git:push:"
    level: blocked
  - id: revoke.git.pull
    effects: [shell]
    matcher: command_prefix
    target: "git:pull:"
    level: blocked
  - id: revoke.git.fetch
    effects: [shell]
    matcher: command_prefix
    target: "git:fetch:"
    level: blocked
  - id: revoke.git.merge
    effects: [shell]
    matcher: command_prefix
    target: "git:merge:"
    level: blocked
  - id: revoke.git.rebase
    effects: [shell]
    matcher: command_prefix
    target: "git:rebase:"
    level: blocked
  - id: revoke.git.reset
    effects: [shell]
    matcher: command_prefix
    target: "git:reset:"
    level: blocked
  - id: revoke.git.checkout
    effects: [shell]
    matcher: command_prefix
    target: "git:checkout:"
    level: blocked
  - id: revoke.git.commit
    effects: [shell]
    matcher: command_prefix
    target: "git:commit:"
    level: blocked
  - id: revoke.git.am
    effects: [shell]
    matcher: command_prefix
    target: "git:am:"
    level: blocked
  - id: revoke.git.cherry-pick
    effects: [shell]
    matcher: command_prefix
    target: "git:cherry-pick:"
    level: blocked
  - id: revoke.git.revert
    effects: [shell]
    matcher: command_prefix
    target: "git:revert:"
    level: blocked
  - id: revoke.git.tag
    effects: [shell]
    matcher: command_prefix
    target: "git:tag:"
    level: blocked
  - id: revoke.git.stash
    effects: [shell]
    matcher: command_prefix
    target: "git:stash:"
    level: blocked
  - id: revoke.git.clone
    effects: [shell]
    matcher: command_prefix
    target: "git:clone:"
    level: blocked
  - id: revoke.git.remote
    effects: [shell]
    matcher: command_prefix
    target: "git:remote:"
    level: blocked
  - id: revoke.git.submodule
    effects: [shell]
    matcher: command_prefix
    target: "git:submodule:"
    level: blocked
  - id: revoke.git.worktree
    effects: [shell]
    matcher: command_prefix
    target: "git:worktree:"
    level: blocked
baseline_allows:
  - id: allow.system.hwmon.read
    effects: [path_read]
    matcher: absolute_prefix
    target: /sys/class/hwmon
    level: auto
  - id: allow.shell.echo
    effects: [shell]
    matcher: command_prefix
    target: echo
    level: confirm
  - id: allow.shell.cat
    effects: [shell]
    matcher: command_prefix
    target: cat
    level: confirm
  - id: allow.shell.ls
    effects: [shell]
    matcher: command_prefix
    target: ls
    level: confirm
  - id: allow.shell.find
    effects: [shell]
    matcher: command_prefix
    target: find
    level: confirm
  - id: allow.shell.pwd
    effects: [shell]
    matcher: command_exact
    target: pwd
    level: confirm
  - id: allow.shell.date
    effects: [shell]
    matcher: command_prefix
    target: date
    level: confirm
  - id: allow.shell.wc
    effects: [shell]
    matcher: command_prefix
    target: wc
    level: confirm
  - id: allow.shell.head
    effects: [shell]
    matcher: command_prefix
    target: head
    level: confirm
  - id: allow.shell.tail
    effects: [shell]
    matcher: command_prefix
    target: tail
    level: confirm
  - id: allow.shell.grep
    effects: [shell]
    matcher: command_prefix
    target: grep
    level: confirm
  - id: allow.shell.sort
    effects: [shell]
    matcher: command_prefix
    target: sort
    level: confirm
  - id: allow.shell.uniq
    effects: [shell]
    matcher: command_prefix
    target: uniq
    level: confirm
  - id: allow.shell.diff
    effects: [shell]
    matcher: command_prefix
    target: diff
    level: confirm
  - id: allow.shell.patch
    effects: [shell]
    matcher: command_prefix
    target: patch
    level: confirm
  - id: allow.shell.pytest
    effects: [shell]
    matcher: command_prefix
    target: "python3 -m pytest"
    level: confirm
  - id: allow.shell.mypy
    effects: [shell]
    matcher: command_prefix
    target: "python3 -m mypy"
    level: confirm
  - id: allow.shell.flake8
    effects: [shell]
    matcher: command_prefix
    target: "python3 -m flake8"
    level: confirm
  - id: allow.shell.node-version
    effects: [shell]
    matcher: command_exact
    target: "node --version"
    level: confirm
  - id: allow.shell.npm-test
    effects: [shell]
    matcher: command_prefix
    target: "npm test"
    level: confirm
  - id: allow.git.status
    effects: [shell]
    matcher: command_prefix
    target: "git:status:"
    level: auto
  - id: allow.git.log
    effects: [shell]
    matcher: command_prefix
    target: "git:log:"
    level: auto
  - id: allow.git.diff
    effects: [shell]
    matcher: command_prefix
    target: "git:diff:"
    level: auto
  - id: allow.git.show
    effects: [shell]
    matcher: command_prefix
    target: "git:show:"
    level: auto
  - id: allow.git.rev-parse
    effects: [shell]
    matcher: command_prefix
    target: "git:rev-parse:"
    level: auto
  - id: allow.git.branch
    effects: [shell]
    matcher: command_prefix
    target: "git:branch:"
    level: auto
  - id: allow.git.describe
    effects: [shell]
    matcher: command_prefix
    target: "git:describe:"
    level: auto
recovery_diagnostics:
  - id: recover.operation.governance-status
    effects: [recovery_diagnostic]
    matcher: name_exact
    target: governance.status
    level: auto
  - id: recover.operation.permissions-status
    effects: [recovery_diagnostic]
    matcher: name_exact
    target: permissions.status
    level: auto
  - id: recover.operation.reality-snapshot
    effects: [recovery_diagnostic]
    matcher: name_exact
    target: reality.snapshot
    level: auto
  - id: recover.operation.reality-daemon
    effects: [recovery_diagnostic]
    matcher: name_exact
    target: reality.daemon_state
    level: auto
  - id: recover.operation.reality-security
    effects: [recovery_diagnostic]
    matcher: name_exact
    target: reality.security_state
    level: auto
  - id: recover.operation.watchdog-service
    effects: [recovery_diagnostic]
    matcher: name_exact
    target: watchdog.service_probe
    level: auto
  - id: recover.operation.graph-commits
    effects: [recovery_diagnostic]
    matcher: name_exact
    target: graph.recent_commits
    level: auto
  - id: recover.operation.graph-head
    effects: [recovery_diagnostic]
    matcher: name_exact
    target: graph.head_sha
    level: auto
  - id: recover.operation.graph-freshness
    effects: [recovery_diagnostic]
    matcher: name_exact
    target: graph.freshness
    level: auto
  - id: recover.path.governance
    effects: [path_read]
    matcher: workspace_prefix
    target: config/governance.json
    level: auto
  - id: recover.path.governance-marker
    effects: [path_read]
    matcher: workspace_prefix
    target: config/.governance-migration.pending
    level: auto
  - id: recover.path.permissions-overlay
    effects: [path_read]
    matcher: workspace_prefix
    target: config/permissions.local.yaml
    level: auto
  - id: recover.path.permissions-legacy
    effects: [path_read]
    matcher: workspace_prefix
    target: config/permissions.yaml
    level: auto
  - id: recover.path.migration-marker
    effects: [path_read]
    matcher: workspace_prefix
    target: config/.permissions-migration.pending
    level: auto
  - id: recover.path.audit
    effects: [path_read]
    matcher: workspace_prefix
    target: memory/audit
    level: auto
~~~

- [ ] Write RED tests for extra="forbid" at every nesting level, duplicate rule IDs, blocked level required for hard_blocks/revocations/denies, non-blocked level required for allows/grants, regex allowed only in the package baseline, and secrets absent from the baseline resource.
- [ ] Treat autonomy as the privilege ordering APPROVE=1, CONFIRM=2, AUTO=3; BLOCKED=0 is a denial, not a grant level. A GrantScope.maximum_level accepts a requested grant only when its numeric privilege is less than or equal to that maximum.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_permission_schema_v2.py -q
~~~

Expected: permission_schema and permissions-v2.yaml do not exist.

- [ ] Implement validators and a load_permission_baseline() resource loader with manifest digest verification. Move PermissionLevel into permission_schema.py in this task and re-export the imported symbol from permission_profile.py so old imports remain type-identical.
- [ ] Extend manifest.json with permissions.current version 2.0.0, resource permissions-v2.yaml, SHA-256 f2f8a35cd5a79859b4e9cd12dbd8396ae799392643ba067bf8e3d188f281125d, and permissions.legacy_history version 1.0.0/digest 1b51202f12a5d8d699092cb0560e0d76ca945ec68691af4b2e574df0c481a46b. The test recalculates both resource digests and fails on drift.

~~~json
{
  "schema_version": 1,
  "governance": {
    "current": {
      "version": "1.0.0",
      "resource": "governance-v1.0.0.json",
      "sha256": "d11c0926958b49cd153a7650472d5c557b47dc3445d5d0e1ef99db8ccf0355a8"
    },
    "history": []
  },
  "permissions": {
    "current": {
      "version": "2.0.0",
      "resource": "permissions-v2.yaml",
      "sha256": "f2f8a35cd5a79859b4e9cd12dbd8396ae799392643ba067bf8e3d188f281125d"
    },
    "legacy_history": [
      {
        "version": "1.0.0",
        "sha256": "1b51202f12a5d8d699092cb0560e0d76ca945ec68691af4b2e574df0c481a46b"
      }
    ]
  }
}
~~~
- [ ] Encode the current effective constitutional rules in permissions-v2.yaml: home .ssh/.gnupg/.aws and /etc,/root,/boot,/proc,/dev hard blocks for read/write; shell-chain regex hard block; workspace read; tmp write AUTO; projects/skills/memory write CONFIRM; /sys/class/hwmon read AUTO; current non-Git shell commands; Git inspection commands; governance snapshot write revocation; all Git mutators including apply as mandatory revocations. The default outside these rules is deny.
- [ ] Define grant scopes exactly for external path read at CONFIRM maximum, workspace write at APPROVE maximum, and shell command at APPROVE maximum. Do not make network/provider/MCP/transport/messaging locally grantable in this cut.
- [ ] Define recovery_diagnostics with exact NAME_EXACT operations governance.status, permissions.status, reality.snapshot, reality.daemon_state, reality.security_state, watchdog.service_probe, graph.recent_commits, graph.head_sha, and graph.freshness; its runtime path rules are limited to the two config snapshots, the migration marker, and Merkle audit files. `OperatingTrunk.sanitation_audit` remains an ordinary healthy-state diagnostic because its current implementation executes mutable checkout scripts and traverses broad repository state. Dedicated G1/P1 migration commands inspect their own backup/source artifacts through secure_files.py rather than widening runtime diagnostic reads. No write, network, provider, MCP, transport, or messaging effect belongs here.
- [ ] Run GREEN:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_permission_schema_v2.py -q
~~~

- [ ] Commit:

~~~bash
git add src/atlas/governance/permission_schema.py src/atlas/governance/permission_profile.py src/atlas/governance/resources/permissions-v2.yaml src/atlas/governance/resources/manifest.json tests/test_permission_schema_v2.py
git commit -m "security: define strict permission schema v2"
~~~

### Task 8: Load or safely bootstrap the private local overlay

**Files:**

- Create: src/atlas/governance/permission_store.py
- Modify: src/atlas/logging/merkle_logger.py
- Test: tests/test_permission_store.py

**Interfaces**

~~~python
class PermissionDocumentStatus(str, Enum):
    ABSENT = "absent"
    VALID = "valid"
    INVALID = "invalid"
    UNMIGRATED = "unmigrated"

@dataclass(frozen=True)
class PermissionDocuments:
    status: PermissionDocumentStatus
    baseline: PermissionBaselineV2
    baseline_sha256: str
    overlay: LocalPermissionsOverlayV2 | None
    overlay_sha256: str | None
    overlay_identity: FileIdentity | None
    legacy_path: Path
    overlay_path: Path
    migration_marker: Path
    reason: str

def inspect_permission_documents(
    workspace: Path,
    *,
    expected_uid: int | None = None,
) -> PermissionDocuments:
    """Securely load baseline and local overlay and detect legacy/transaction state."""

def bootstrap_empty_overlay(
    documents: PermissionDocuments,
    *,
    merkle: MerkleLogger,
    expected_uid: int | None = None,
) -> PermissionDocuments:
    """Create only a zero-grant overlay when no legacy file exists."""
~~~

- [ ] Write RED tests for 0600 enforcement, symlink rejection, malformed YAML, scalar/list root, unknown key, missing overlay with no legacy, missing overlay with legacy permissions.yaml, migration marker present, empty-overlay bootstrap, and redacted status serialization.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_permission_store.py -q
~~~

Expected: permission_store does not exist.

- [ ] Implement no-follow bounded YAML reads. Map no overlay/no legacy to ABSENT, no overlay/legacy present or a marker to UNMIGRATED, strict valid overlay to VALID, and every unsafe/schema condition to INVALID.
- [ ] bootstrap_empty_overlay() must verify Merkle, append genesis if empty, append a redacted `permissions.overlay_bootstrap.planned` record before writing, write exactly schema_version/policy version/empty grants/denies/read_extended/legacy_unknown plus empty Telegram config, then append `permissions.overlay_bootstrap.applied`; the file is 0600 and no audit payload contains a secret.
- [ ] Add `permissions.migration.genesis`, `permissions.overlay_bootstrap.planned`, and `permissions.overlay_bootstrap.applied` to `AUDIT_ACTIONS` in this task so the first bootstrap caller never emits an undeclared action.
- [ ] Run GREEN:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_permission_store.py -q
~~~

- [ ] Commit:

~~~bash
git add src/atlas/governance/permission_store.py \
  src/atlas/logging/merkle_logger.py tests/test_permission_store.py
git commit -m "security: load private permission overlays fail closed"
~~~

### Task 9: Classify every legacy field without granting ambiguity

**Files:**

- Create: src/atlas/governance/permission_migration.py
- Test: tests/test_permission_migration.py

**Authority matrix**

| Legacy field | Unambiguous destination | Rule |
| --- | --- | --- |
| workspace.read_extended | overlay.read_extended | Preserve path values as local data, but evaluate them only as synthesized `CONFIRM` grants under `scope.external.read`; hard blocks still win and no AUTO authority is inherited. |
| telegram.authorized_chat_ids, authorized_user_ids, require_passphrase_for_approve, passphrase_hash | overlay.telegram | Preserve locally; redact all reports/audit. |
| workspace.auto_write, confirm_write, read_only | none | If full legacy digest is a known historical baseline, drop as baseline-owned; otherwise one denied legacy_unknown per value. |
| absolute_blocks, system_read_allowed | none | If full digest is known, drop as baseline-owned; otherwise denied legacy_unknown. Never turn into local authority. |
| shell_allowlist | none | If full digest is known, drop as baseline-owned; otherwise every value is denied legacy_unknown. |
| unknown top-level or nested key | legacy_unknown | Store canonical local value and digest; mark denied. |

**Interfaces**

~~~python
@dataclass(frozen=True)
class PermissionMigrationPlan:
    legacy_path: Path
    backup_path: Path
    overlay_path: Path
    marker_path: Path
    legacy_sha256: str
    legacy_identity: FileIdentity
    baseline_sha256: str
    overlay_yaml: bytes
    overlay_sha256: str
    legacy_unknown_count: int
    redacted_summary: Mapping[str, object]
    plan_sha256: str

def plan_permission_migration(
    documents: PermissionDocuments,
    *,
    known_legacy_digests: Mapping[str, str],
) -> PermissionMigrationPlan:
    """Convert unambiguous local fields and deny every ambiguous value."""
~~~

- [ ] Write RED tests for the complete matrix, including a custom shell entry that becomes legacy_unknown, a baseline-looking entry in an unrecognized file that still becomes legacy_unknown, exact historical digest recognition, unknown nested Telegram key, stable canonical plan digest, and no passphrase/chat IDs in redacted_summary.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_permission_migration.py -q -k plan
~~~

Expected: plan_permission_migration is missing.

- [ ] Implement canonical JSON for LegacyUnknown.value_sha256 and deterministic IDs legacy.<source-field>.<first-12-sha256>. Sort all output by source field then digest so repeated dry-runs are byte-identical.
- [ ] The generated overlay must retain legacy_unknown entries with status denied and contain zero explicit grants. `read_extended` remains a path tuple, but Task 16 gives it only the fixed `CONFIRM`/`scope.external.read` semantics; migration never converts it into AUTO authority.
- [ ] Run GREEN:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_permission_migration.py -q -k plan
~~~

- [ ] Commit:

~~~bash
git add src/atlas/governance/permission_migration.py tests/test_permission_migration.py
git commit -m "security: classify legacy permissions conservatively"
~~~

### Task 10: Apply, recover, restore, and audit permission migrations

**Files:**

- Modify: src/atlas/governance/permission_migration.py
- Modify: src/atlas/logging/merkle_logger.py
- Test: tests/test_permission_migration.py

**Interfaces**

~~~python
@dataclass(frozen=True)
class PermissionMigrationReceipt:
    legacy_sha256: str
    backup_sha256: str
    overlay_sha256: str
    baseline_sha256: str
    policy_version: str
    legacy_unknown_count: int
    validation: str
    intent_audit_hash: str
    outcome_audit_hash: str

def apply_permission_migration(
    plan: PermissionMigrationPlan,
    *,
    merkle: MerkleLogger,
    expected_uid: int | None = None,
) -> PermissionMigrationReceipt:
    """Recheck plan/source, mark transaction, backup, write overlay, audit, clear marker."""

def recover_permission_migration(
    workspace: Path,
    *,
    action: Literal["finish", "rollback"],
    expected_plan_sha256: str,
    merkle: MerkleLogger,
) -> PermissionDocuments:
    """Finish verified artifacts or restore the exact legacy backup."""
~~~

- [ ] Add RED tests for source TOCTOU, backup symlink, backup mode, interruption after marker/backup/overlay, finish, rollback, wrong plan digest, full-byte restoration, Merkle failure before effect, intent audit ordering before the first mutation, and receipt redaction.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_permission_migration.py -q -k "apply or recover or rollback"
~~~

Expected: apply/recover functions are missing.

- [ ] Add permissions.migration.planned, permissions.migration.applied, permissions.migration.recovery_planned, permissions.migration.finished, and permissions.migration.rolled_back audit actions; Task 8 already declared genesis and overlay-bootstrap actions.
- [ ] Verify Merkle and append a redacted `permissions.migration.planned` intent bound to `plan_sha256` before the first filesystem mutation. Then write .permissions-migration.pending with 0600 and fsync, create permissions.yaml.backup-<full-legacy-sha256>, write permissions.local.yaml atomically, append the applied receipt, unlink the marker, and fsync config/. Keep legacy permissions.yaml unchanged so rollback is exact and evidence remains available. Finish/rollback likewise append `permissions.migration.recovery_planned` before changing any artifact and append the terminal outcome afterwards.
- [ ] Make recovery digest-bound and non-destructive under concurrency. `finish` accepts only the exact planned legacy/backup/overlay digests. `rollback` first requires the untouched legacy file still has its planned identity/digest and the overlay matches the planned post-image; because apply never changed legacy, rollback removes only that exact overlay, leaves the verified backup as evidence, fsyncs the directory, and clears the marker after its outcome audit. Any source/overlay drift refuses rather than overwriting operator edits.
- [ ] On any incomplete sequence, inspect_permission_documents() remains UNMIGRATED and all effects remain denied until finish or rollback succeeds.
- [ ] Run GREEN:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_permission_migration.py -q
~~~

- [ ] Commit:

~~~bash
git add src/atlas/governance/permission_migration.py src/atlas/logging/merkle_logger.py tests/test_permission_migration.py
git commit -m "security: apply permission migrations transactionally"
~~~

### Task 11: Expose permission migration and explicit legacy classification CLI

**Files:**

- Modify: src/atlas/interfaces/cli.py
- Modify: src/atlas/governance/permission_migration.py
- Modify: src/atlas/logging/merkle_logger.py
- Test: tests/test_permission_cli.py

**Interfaces**

~~~text
atlas permissions status --workspace PATH --json
atlas permissions migrate --workspace PATH --json
atlas permissions migrate --workspace PATH --apply --expected-plan-sha256 SHA256 --json
atlas permissions classify LEGACY_ID --decision grant --effect EFFECT --matcher MATCHER --target TARGET --scope SCOPE_ID --level confirm|approve --workspace PATH --expected-overlay-sha256 SHA256 --json
atlas permissions classify LEGACY_ID --decision deny --effect EFFECT --matcher MATCHER --target TARGET --workspace PATH --expected-overlay-sha256 SHA256 --json
atlas permissions recover --finish|--rollback --expected-plan-sha256 SHA256 --workspace PATH --json
~~~

~~~python
def classify_legacy_permission(
    documents: PermissionDocuments,
    *,
    legacy_id: str,
    decision: Literal["grant", "deny"],
    replacement: LocalPermissionRule | LocalDenyRule,
    expected_overlay_sha256: str,
    merkle: MerkleLogger,
) -> PermissionDocuments:
    """Revalidate, audit intent, replace exactly one denied legacy item, audit outcome."""
~~~

- [ ] Write CliRunner RED tests for dry-run redaction, apply digest binding, one-at-a-time operator classification, grant scope validation, deny classification, stale overlay digest refusal, Merkle failure before mutation, unsafe audit-root rejection before mutation, intent audit ordering, overlay TOCTOU, and recovery.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_permission_cli.py -q
~~~

Expected: no such command permissions.

- [ ] Implement commands without constructing Orchestrator. Classification never infers effect, matcher, or target from the ambiguous legacy value: the operator supplies them explicitly. Every apply/classify/recover branch calls `open_secure_merkle_logger(workspace / "memory" / "audit", create=True)` and never constructs `MerkleLogger` directly. The CLI calls `classify_legacy_permission`; it does not write the overlay itself. The function re-lstats/re-digests the overlay and matches the caller's expected digest, verifies Merkle, appends `permissions.classification.planned` with only IDs/digests before the atomic write, removes exactly one matching legacy_unknown, adds either a scope-validated grant or deny, and appends `permissions.classification.applied` afterwards. It emits only IDs/digests/counts and never canonical legacy values.
- [ ] Add `permissions.classification.planned` and `permissions.classification.applied` to `AUDIT_ACTIONS`.
- [ ] Run GREEN:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_permission_cli.py -q
~~~

- [ ] Commit:

~~~bash
git add src/atlas/interfaces/cli.py src/atlas/governance/permission_migration.py \
  src/atlas/logging/merkle_logger.py tests/test_permission_cli.py
git commit -m "feat: add explicit permission recovery workflow"
~~~

### Task 12: Remove monotonic sync and wire schema v2 into runtime consumers

**Files:**

- Modify: src/atlas/core/orchestrator.py
- Modify: src/atlas/tools/editor.py
- Modify: src/atlas/interfaces/telegram_bot.py
- Modify: pyproject.toml
- Modify: tests/test_orchestrator_permissions_sync.py
- Modify: tests/test_editor.py
- Modify: tests/test_telegram_bot.py
- Modify: tests/test_capabilities.py
- Modify: tests/test_executor_http_transport.py
- Modify: tests/test_structured_exec_containment.py
- Modify: tests/test_atlas_core.py
- Modify: tests/test_dashboard.py
- Modify: tests/test_governance_wheel_contract.py
- Create: tests/permission_v2_helpers.py

**Interfaces**

~~~python
class PermissionProfile:
    def __init__(
        self,
        documents: PermissionDocuments,
        workspace: Path,
        git_inspect_root: Path | None = None,
    ) -> None:
        """Construct only from strict, VALID v2 documents."""

    @classmethod
    def from_workspace(
        cls,
        workspace: Path,
        *,
        git_inspect_root: Path | None = None,
    ) -> PermissionProfile:
        """Load strict documents and reject non-VALID state."""
~~~

- [ ] Add RED tests proving a removed baseline allow disappears, corrupt YAML raises PermissionConfigurationError, `PermissionProfile.from_workspace()` rejects ABSENT without writing, Orchestrator's already-audited bootstrap path creates only an empty overlay when no legacy exists, legacy input returns UNMIGRATED, EditorTool uses the workspace overlay rather than cwd/atlas_data_root, and the installed-wheel contract loads the permission baseline from `atlas.governance.resources` after `config/permissions.yaml` is removed from data-files.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_orchestrator_permissions_sync.py tests/test_editor.py tests/test_telegram_bot.py tests/test_capabilities.py tests/test_executor_http_transport.py tests/test_structured_exec_containment.py tests/test_atlas_core.py tests/test_dashboard.py tests/test_governance_wheel_contract.py -q
~~~

Expected: current union sync preserves removed allows and corrupt YAML falls back to an empty partial profile.

- [ ] Delete _sync_permissions_file(), _write_default_permissions(), permission copying from _copy_defaults(), and EditorTool._resolve_permissions_config(). Replace direct legacy fixtures with strict v2 helper fixtures.
- [ ] Keep `PermissionProfile.from_workspace()` load-only: it accepts only VALID documents and has no Merkle or bootstrap behavior. In this cut ABSENT bootstrap belongs exclusively to the Orchestrator initialization path, using `open_secure_merkle_logger()` and `bootstrap_empty_overlay()` before constructing the profile; the permission CLI exposes status/migrate/classify/recover but does not invent a second empty-bootstrap path.
- [ ] Put one exact test helper in tests/permission_v2_helpers.py: write_permission_overlay(workspace: Path, *, grants: tuple[LocalPermissionRule, ...] = (), denies: tuple[LocalDenyRule, ...] = (), read_extended: tuple[str, ...] = (), telegram: TelegramLocalConfig | None = None) -> PermissionDocuments. It writes config/permissions.local.yaml at 0600 and returns inspect_permission_documents(workspace); all listed tests use it instead of hand-written legacy YAML.
- [ ] Preserve TelegramAuthorizer's public behavior but source telegram_config only from LocalPermissionsOverlayV2.
- [ ] Remove config/permissions.yaml from tool.setuptools.data-files after wheel tests use the package permissions-v2.yaml resource.
- [ ] Run GREEN:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_orchestrator_permissions_sync.py tests/test_editor.py tests/test_telegram_bot.py tests/test_capabilities.py tests/test_executor_http_transport.py tests/test_structured_exec_containment.py tests/test_atlas_core.py tests/test_dashboard.py tests/test_governance_wheel_contract.py -q
~~~

- [ ] Commit:

~~~bash
git add src/atlas/core/orchestrator.py src/atlas/tools/editor.py \
  src/atlas/interfaces/telegram_bot.py pyproject.toml \
  tests/permission_v2_helpers.py tests/test_orchestrator_permissions_sync.py \
  tests/test_editor.py tests/test_telegram_bot.py tests/test_capabilities.py \
  tests/test_executor_http_transport.py tests/test_structured_exec_containment.py \
  tests/test_atlas_core.py tests/test_dashboard.py \
  tests/test_governance_wheel_contract.py
git commit -m "security: replace permission sync with strict overlay loading"
~~~

---

## P2 — Evaluation, Precedence, and Provenance

### Task 13: Introduce one typed request and provenance-rich decision contract

**Files:**

- Modify: src/atlas/governance/permission_schema.py
- Rewrite: src/atlas/governance/permission_profile.py
- Test: tests/test_permission_precedence.py

**Interfaces**

PermissionLevel already lives in permission_schema.py from Task 7 and permission_profile.py continues to re-export that same symbol, avoiding a schema/profile import cycle.

~~~python
class PermissionLevel(str, Enum):
    AUTO = "auto"
    CONFIRM = "confirm"
    APPROVE = "approve"
    BLOCKED = "blocked"

class DecisionSource(str, Enum):
    HARD_BLOCK = "hard_block"
    MANDATORY_REVOCATION = "mandatory_revocation"
    LOCAL_DENY = "local_deny"
    LOCAL_GRANT = "local_grant"
    BASELINE_ALLOW = "baseline_allow"
    DEFAULT_DENY = "default_deny"
    RECOVERY_DIAGNOSTIC = "recovery_diagnostic"

@dataclass(frozen=True)
class PermissionRequest:
    effect: EffectKind
    target: str

@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    level: PermissionLevel
    reason: str
    path: str
    source: DecisionSource
    policy_version: str
    rule_id: str
    precedence: int
    decision_sha256: str

class PermissionProfile:
    def evaluate(self, request: PermissionRequest) -> AccessDecision:
        """Evaluate all matching tiers in fixed precedence order."""
~~~

The numeric precedence is fixed: hard block 600, mandatory revocation 500, local deny 400, local grant 300, baseline allow including zones 200, default deny 100. Higher wins. Within one tier, choose longest normalized target, then lexicographically smallest rule ID. `decision_sha256` is canonical JSON over allowed, level, source, policy_version, rule_id, precedence, request effect, and the SHA-256 of the normalized target; it detects semantic drift without copying sensitive targets into audit payloads.

~~~python
_TIERS: tuple[tuple[int, DecisionSource, tuple[str, ...]], ...] = (
    (600, DecisionSource.HARD_BLOCK, ("hard_blocks",)),
    (500, DecisionSource.MANDATORY_REVOCATION, ("mandatory_revocations",)),
    (400, DecisionSource.LOCAL_DENY, ("denies",)),
    (300, DecisionSource.LOCAL_GRANT, ("grants",)),
    (200, DecisionSource.BASELINE_ALLOW, ("zones", "baseline_allows")),
)

RuleCandidate = PermissionRule | LocalPermissionRule | LocalDenyRule

def _select_rule(
    rules: Iterable[RuleCandidate],
    request: PermissionRequest,
) -> RuleCandidate | None:
    matches = [rule for rule in rules if _rule_matches(rule, request)]
    if not matches:
        return None
    return sorted(matches, key=lambda rule: (-len(rule.target), rule.id))[0]
~~~

- [ ] Write a RED contract test asserting all nine fields for a baseline workspace-read decision and a default deny, including the exact canonical `decision_sha256` inputs.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_permission_precedence.py -q -k contract
~~~

Expected: AccessDecision lacks source, policy_version, rule_id, and precedence.

- [ ] Implement PermissionRequest, DecisionSource, deterministic matcher normalization, and a single evaluate() skeleton that can return baseline/default decisions. Path matching must use resolved candidates but never allow an escaped symlink to retain its pre-resolution workspace prefix. Command matching must first reject NUL/newline, parse with `shlex.split`, and canonicalize tokens. `COMMAND_EXACT` compares the complete token tuple; `COMMAND_PREFIX` compares whole leading tokens (so `echoevil` cannot match `echo`), never raw `str.startswith`.
- [ ] Run GREEN:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_permission_precedence.py -q -k contract
~~~

- [ ] Commit:

~~~bash
git add src/atlas/governance/permission_schema.py src/atlas/governance/permission_profile.py tests/test_permission_precedence.py
git commit -m "refactor: unify permission decisions with provenance"
~~~

### Task 14: Make constitutional hard blocks the first evaluator tier

**Files:**

- Modify: src/atlas/governance/permission_profile.py
- Test: tests/test_permission_precedence.py
- Modify: tests/test_capabilities.py

- [ ] Add one RED table covering .ssh, .gnupg, .aws, /etc, /root, /boot, /proc, /dev, a symlink from workspace into /etc, shell semicolon/pipe/and-or/backticks/substitution/newline, and an overlay grant or baseline allow that targets the same resource.
- [ ] Assert every result has source HARD_BLOCK, precedence 600, policy version 2.0.0, and the package rule ID.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_permission_precedence.py tests/test_capabilities.py -q -k hard_block
~~~

Expected: current class constants have no provenance and are not sourced from the package baseline.

- [ ] Remove _ABSOLUTE_BLOCKS, _SYSTEM_READ_ALLOWED, and the shell-chain policy constant from PermissionProfile. Compile only trusted baseline regex rules with re.ASCII and reject invalid regex while loading the package baseline.
- [ ] Implement tier 600 before every other matcher.
- [ ] Run GREEN with the same command.
- [ ] Commit:

~~~bash
git add src/atlas/governance/permission_profile.py tests/test_permission_precedence.py tests/test_capabilities.py
git commit -m "security: enforce package hard blocks first"
~~~

### Task 15: Make mandatory revocations beat all local grants

**Files:**

- Modify: src/atlas/governance/permission_profile.py
- Test: tests/test_permission_precedence.py
- Modify: tests/test_capabilities.py

- [ ] Add RED cases where explicit local grants try to permit governance.json write, git apply, git push, git commit, and git -C <atlas-repo> apply.
- [ ] Assert source MANDATORY_REVOCATION, precedence 500, and the exact revocation rule ID in each decision.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_permission_precedence.py tests/test_capabilities.py -q -k mandatory_revocation
~~~

Expected: local grant evaluation does not exist and Git restrictions still live in hardcoded sets.

- [ ] Canonicalize Git into a semantic target git:<subcommand>:<resolved-C-root-or-workspace>. Reject unknown global switches. Match the package revocation before local rules; keep the existing read-only Git subcommand behavior as baseline allows.
- [ ] Delete _GIT_DENIED_SUBCOMMANDS after the resource rules and tests carry the authority.
- [ ] Run GREEN with the same command.
- [ ] Commit:

~~~bash
git add src/atlas/governance/permission_profile.py tests/test_permission_precedence.py tests/test_capabilities.py
git commit -m "security: make mandatory revocations override grants"
~~~

### Task 16: Make local denies beat local and baseline allows

**Files:**

- Modify: src/atlas/governance/permission_profile.py
- Test: tests/test_permission_precedence.py

- [ ] Add RED cases for: deny projects/private over the broader workspace-read baseline; deny echo over a baseline command; deny a read_extended path; and two matching denies where the most-specific rule wins deterministically.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_permission_precedence.py -q -k local_deny
~~~

Expected: overlay denies are not evaluated.

- [ ] Convert read_extended values into synthesized local grants only after secure path normalization. Each uses stable ID `local.read_extended.<first-12-normalized-path-sha256>`, effect PATH_READ, matcher ABSOLUTE_PREFIX, level CONFIRM, and scope_id `scope.external.read`; validate it through the same scope checks as an explicit grant. Evaluate explicit/synthesized local denies at tier 400 before grants and baseline.
- [ ] Run GREEN with the same command.
- [ ] Commit:

~~~bash
git add src/atlas/governance/permission_profile.py tests/test_permission_precedence.py
git commit -m "security: apply local denies before allows"
~~~

### Task 17: Validate grant scope before allowing a local grant

**Files:**

- Create: src/atlas/governance/permission_authority.py
- Modify: src/atlas/governance/permission_profile.py
- Modify: src/atlas/governance/permission_store.py
- Test: tests/test_permission_precedence.py
- Test: tests/test_permission_store.py

**Interfaces**

~~~python
def validate_overlay_authority(
    baseline: PermissionBaselineV2,
    overlay: LocalPermissionsOverlayV2,
) -> tuple[str, ...]:
    """Return stable errors for grants outside scope or above maximum level."""
~~~

`permission_authority.py` is the lower dependency: it imports only
`permission_schema.py`. Both `permission_store.py` and `permission_profile.py`
import `validate_overlay_authority()` from it; neither imports the other for
validation, so the task introduces no store/profile cycle.

- [ ] Add separate RED cases for unknown scope_id, effect outside scope, target outside scope, AUTO above a CONFIRM maximum, regex grant, network grant when no network scope exists, a read_extended value proving CONFIRM rather than AUTO and scope validation, and a valid explicit shell grant that survives an ordinary baseline update.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_permission_precedence.py tests/test_permission_store.py -q -k local_grant
~~~

Expected: unvalidated overlay grants can be loaded or there is no grant tier.

- [ ] Make any authority error set PermissionDocumentStatus.INVALID; do not skip only the bad grant. Evaluate valid grants at tier 300 and expose scope_id in reason while keeping rule_id as the local rule ID.
- [ ] A grant survives a baseline update when its named scope still exists and contains it. If a scope is removed/narrowed, health becomes INVALID until the operator reclassifies it; never widen automatically.
- [ ] Run GREEN with the same command.
- [ ] Commit:

~~~bash
git add src/atlas/governance/permission_authority.py \
  src/atlas/governance/permission_profile.py \
  src/atlas/governance/permission_store.py \
  tests/test_permission_precedence.py tests/test_permission_store.py
git commit -m "security: constrain local permission grants"
~~~

### Task 18: Complete baseline/default evaluation and compatibility wrappers

**Files:**

- Modify: src/atlas/governance/permission_profile.py
- Modify: src/atlas/security/capabilities.py
- Modify: src/atlas/security/executor.py
- Test: tests/test_permission_precedence.py
- Modify: tests/test_capabilities.py
- Modify: tests/test_structured_exec_containment.py

**Interfaces**

~~~python
@dataclass(frozen=True)
class DecisionProvenance:
    source: DecisionSource
    policy_version: str
    rule_id: str
    precedence: int
    decision_sha256: str

def evaluate_path(self, path: str, write: bool = False) -> AccessDecision:
    effect = EffectKind.PATH_WRITE if write else EffectKind.PATH_READ
    return self.evaluate(PermissionRequest(effect=effect, target=path))

def evaluate_shell_command(self, command: str) -> AccessDecision:
    return self.evaluate(PermissionRequest(effect=EffectKind.SHELL, target=command))
~~~

_BaseCapability gains permission: DecisionProvenance | None. ReadCapability,
WriteCapability, and ExecCapability carry the successful PermissionProfile
decision. NetworkCapability keeps permission=None in P2 because SSRFBridge is
not a permission-baseline rule; Task 20 adds the central authorization-state
digest without mislabeling SSRF provenance. AtlasExecutor includes available
permission provenance in Merkle success/failure payloads.

- [ ] Add RED tests for tier 200 baseline allows, tier 100 default deny, most-specific baseline rule, /sys/class/hwmon single authority, workspace zones, Git read-only commands, shell-chain regressions, absolute/symlink paths, and successful capability audit provenance.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_permission_precedence.py tests/test_capabilities.py tests/test_structured_exec_containment.py -q
~~~

Expected: compatibility wrappers and capability tokens do not expose the new provenance.

- [ ] Implement baseline tier then deny-by-default. Keep absolute_block_decision() as a narrow wrapper over evaluate() so EditorTool's pre-existence policy check remains intact.
- [ ] Revalidate the request at each AtlasExecutor sink and reject unless the newly computed `decision_sha256` equals the capability provenance digest. Comparing only source/rule/version is forbidden because a same-ID rule can change level, precedence, effect, or normalized target. Audit payloads carry the decision digest and non-secret provenance fields, never the raw target.
- [ ] Run GREEN:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_permission_precedence.py tests/test_capabilities.py tests/test_structured_exec_containment.py -q
~~~

- [ ] Run strict types for the completed permission cut:

~~~bash
MYPYPATH=src .venv/bin/python -m mypy src/atlas/governance src/atlas/security/capabilities.py src/atlas/security/executor.py
~~~

- [ ] Commit:

~~~bash
git add src/atlas/governance/permission_profile.py src/atlas/security/capabilities.py src/atlas/security/executor.py tests/test_permission_precedence.py tests/test_capabilities.py tests/test_structured_exec_containment.py
git commit -m "security: complete permission precedence and provenance"
~~~

---

## P3 — Central Health Gate and Effect Closure

### Task 19: Derive and dynamically revalidate authorization health

**Files:**

- Create: src/atlas/security/authorization_gate.py
- Modify: src/atlas/governance/trust_root.py
- Modify: src/atlas/governance/permission_store.py
- Modify: src/atlas/logging/merkle_logger.py
- Test: tests/test_authorization_gate.py

**Interfaces**

~~~python
class AuthorizationHealth(str, Enum):
    VALID = "valid"
    ABSENT = "absent"
    INVALID = "invalid"
    UNMIGRATED = "unmigrated"

@dataclass(frozen=True)
class AuthorizationState:
    health: AuthorizationHealth
    reason: str
    governance_status: GovernanceSnapshotStatus
    permission_status: PermissionDocumentStatus
    governance_version: str
    governance_sha256: str
    permission_policy_version: str
    permission_baseline_sha256: str
    permission_overlay_sha256: str | None
    governance_identity: FileIdentity | None
    permission_overlay_identity: FileIdentity | None
    governance_marker_identity: FileIdentity | None
    permission_marker_identity: FileIdentity | None
    merkle_valid: bool
    state_sha256: str

class AuthorizationStateProvider:
    def __init__(
        self,
        workspace: Path,
        *,
        expected_governance_sha256: str,
        expected_overlay_sha256: str | None,
        merkle: MerkleLogger,
    ) -> None:
        """Bind a running process to the exact securely loaded artifacts."""

    def current(self) -> AuthorizationState:
        """Re-lstat and re-digest changed artifacts; never trust cached bytes after identity drift."""

class AuthorizationDenied(RuntimeError):
    def __init__(self, state: AuthorizationState, effect: EffectKind, operation: str) -> None:
        super().__init__(f"authorization {state.health.value}: {effect.value}:{operation}")
        self.state = state
        self.effect = effect
        self.operation = operation

class AuthorizationGate:
    def __init__(
        self,
        state_provider: AuthorizationStateProvider,
        *,
        merkle: MerkleLogger,
        recovery_diagnostics: tuple[PermissionRule, ...],
    ) -> None:
        """Central fail-closed gate with immutable recovery-diagnostic policy."""

    def require_effect(self, effect: EffectKind, operation: str) -> AuthorizationState:
        """Return current VALID state or raise AuthorizationDenied."""

    def require_diagnostic_read(self, path: Path | str) -> AuthorizationState:
        """Allow only package-baseline diagnostic path rules while non-VALID."""

    def require_diagnostic_operation(self, operation: str) -> AuthorizationState:
        """Allow only an exact package-baseline recovery operation name."""
~~~

Health composition is exact and ordered INVALID, then UNMIGRATED, then ABSENT,
then VALID:

| Governance | Permissions | AuthorizationHealth |
| --- | --- | --- |
| INVALID, DIVERGED, or post-load digest/identity drift | any | INVALID |
| any non-invalid state | INVALID or post-load digest/identity drift | INVALID |
| CURRENT or ABSENT | UNMIGRATED or non-empty legacy_unknown | UNMIGRATED |
| ABSENT | VALID or ABSENT | ABSENT |
| CURRENT | ABSENT | ABSENT |
| CURRENT | VALID, no legacy_unknown | VALID |

Any `merkle.verify_chain()` false result or exception overrides the table and
produces INVALID. `state_sha256` is canonical JSON over both statuses, reasons,
policy versions, expected and observed digests, every `FileIdentity` field for
governance/overlay/markers, the presence of both migration markers, and
`merkle_valid`. It does not bind the mutable Merkle head hash, so a legitimate
audit append does not instantly stale every issued capability.

- [ ] Write RED tests for every row including ABSENT+UNMIGRATED, a post-start overlay rewrite, governance chmod, same-size rewrite with restored mtime, symlink swap, both migration-marker creations, non-empty legacy_unknown, corrupt/raising Merkle verification, a stable state_sha256 across a valid Merkle append, allowed audit/config diagnostic reads, and denied workspace/project reads while non-VALID.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_authorization_gate.py -q
~~~

Expected: authorization_gate does not exist.

- [ ] Implement health derivation. Cache policy parsing only while governance/overlay/marker lstat identities are unchanged; recompute with no-follow reads after any change. Call `merkle.verify_chain()` on every `current()`/effect-time decision in this correctness cut and fail closed on false/exception; do not cache a prior success. Never update expected digests in a running process.
- [ ] Add `authorization.effect_blocked` to `AUDIT_ACTIONS`. A blocked attempt appends that redacted record only when the just-computed state has `merkle_valid=True`; when verification is false or raises, deny without calling append or mutating any audit file. If an append on an otherwise valid chain fails, preserve the denial.
- [ ] Run GREEN:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_authorization_gate.py -q
~~~

- [ ] Commit:

~~~bash
git add src/atlas/security/authorization_gate.py \
  src/atlas/governance/trust_root.py src/atlas/governance/permission_store.py \
  src/atlas/logging/merkle_logger.py tests/test_authorization_gate.py
git commit -m "security: derive dynamic authorization health"
~~~

### Task 20: Put every capability family behind AuthorizationGate

**Files:**

- Modify: src/atlas/security/capabilities.py
- Modify: src/atlas/security/executor.py
- Modify: src/atlas/core/orchestrator.py
- Modify: src/atlas/tools/editor.py
- Modify: tests/test_capabilities.py
- Modify: tests/test_executor_http_transport.py
- Modify: tests/test_atlas_core.py
- Modify: tests/test_editor.py
- Modify: tests/test_structured_exec_containment.py

**Interfaces**

~~~python
class CapabilityIssuer:
    def __init__(
        self,
        profile: PermissionProfile,
        gate: AuthorizationGate,
        bridge: SSRFBridge | None = None,
    ) -> None:
        """Issue no capability without a current authorization decision."""
~~~

Call order is fixed:

- issue_read: require_effect(PATH_READ) for ordinary reads; if non-VALID, try require_diagnostic_read(path) and issue only a RECOVERY_DIAGNOSTIC read token.
- issue_write: require_effect(PATH_WRITE) before profile evaluation.
- issue_exec: require_effect(SHELL) before command or working-directory evaluation.
- issue_network: require_effect(NETWORK) before SSRFBridge.check().

- [ ] Add RED tests using the same valid/absent/invalid/unmigrated gate fixture for read, write, exec, and network. Include corrupt overlay denial for an SSRF-allowlisted URL and one permitted local diagnostic read.
- [ ] Add a regression test proving src/atlas contains no productive issue_network/execute_network caller yet; this documents that gating the unused method alone does not close network.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_capabilities.py tests/test_executor_http_transport.py tests/test_structured_exec_containment.py tests/test_atlas_core.py tests/test_editor.py -q -k authorization
~~~

Expected: network issuance still depends only on SSRFBridge and the issuer has no gate.

- [ ] Inject the gate, add state_sha256 to every immutable capability, and make AtlasExecutor reject tokens whose state no longer equals gate.current().state_sha256. Update both productive `CapabilityIssuer(...)` call sites (Orchestrator and EditorTool) plus all direct test fixtures in the same commit; no compatibility default may fabricate an always-valid gate.
- [ ] Run GREEN with the same command.
- [ ] Commit:

~~~bash
git add src/atlas/security/capabilities.py src/atlas/security/executor.py \
  src/atlas/core/orchestrator.py src/atlas/tools/editor.py \
  tests/test_capabilities.py tests/test_executor_http_transport.py \
  tests/test_structured_exec_containment.py tests/test_atlas_core.py \
  tests/test_editor.py
git commit -m "security: gate every capability family by health"
~~~

### Task 21: Refuse Orchestrator, Decider, and service effects when health is not valid

**Files:**

- Modify: src/atlas/core/decider/decider.py
- Modify: src/atlas/core/orchestrator.py
- Modify: src/atlas/core/orchestrator_parts/agentic_executor.py
- Modify: src/atlas/core/orchestrator_parts/pipeline_runner.py
- Modify: src/atlas/core/orchestrator_parts/approvals.py
- Modify: src/atlas/core/cold_update_manager.py
- Modify: src/atlas/hermes/kanban_bridge.py
- Modify: src/atlas/mcp/plugin_activator.py
- Modify: src/atlas/mcp/plugin_receipt_broker.py
- Modify: src/atlas/transparency/appeal.py
- Modify: src/atlas/runtime/service_runner.py
- Test: tests/test_orchestrator_authorization_health.py
- Modify: tests/test_decider.py
- Modify: tests/test_gate_i_service.py
- Modify: tests/test_agentic_executor.py
- Modify: tests/test_cold_update_decider.py
- Modify: tests/test_kanban_bridge.py
- Modify: tests/test_plugin_activator.py
- Modify: tests/test_plugin_receipt_broker.py
- Modify: tests/test_appeal.py

**Interfaces**

~~~python
@dataclass(frozen=True)
class DecisionAction:
    kind: str
    requires_approval: bool = False
    sensitivity: str = "normal"
    mutating: bool = False
    reversible: bool = False
    effects: tuple[EffectKind, ...] = ()
    reason: str = ""
    descriptor: str = ""

def require_runtime_authorization(
    self,
    effect: EffectKind,
    operation: str,
) -> AuthorizationState:
    return self._authorization_gate.require_effect(effect, operation)

def require_runtime_authorizations(
    self,
    effects: tuple[EffectKind, ...],
    operation: str,
) -> tuple[AuthorizationState, ...]:
    """Check each declared family; an empty tuple is never valid for mutation."""
    return tuple(self.require_runtime_authorization(e, operation) for e in effects)
~~~

- [ ] Write RED tests proving Orchestrator construction stops after trust bootstrap and before effectful collaborators when initial health is INVALID/UNMIGRATED; the exception points to governance/permissions recovery commands.
- [ ] Write RED tests proving post-start corruption makes _consult_decider() return Deny before calling the configured Decider for every mutating action or action with a non-empty effects tuple; an approved pending task is rechecked and blocked before on_execute; AtlasServiceRunner.start() refuses before Telegram/schedulers/dashboard/MCP. Cover every live DecisionAction producer: Orchestrator, PipelineRunner, AgenticExecutor, ColdUpdateManager, KanbanBridge, PluginActivator, PluginReceiptBroker, and FalsePositiveApealer.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_orchestrator_authorization_health.py tests/test_decider.py tests/test_gate_i_service.py tests/test_agentic_executor.py tests/test_cold_update_decider.py tests/test_kanban_bridge.py tests/test_plugin_activator.py tests/test_plugin_receipt_broker.py tests/test_appeal.py -q
~~~

Expected: Orchestrator and service runner have no central health check.

- [ ] Construct AuthorizationStateProvider/Gate immediately after G1/P1 loading. In this task inject it into the consumers changed here—Decider consultation, ApprovalManager, PipelineRunner, AtlasServiceRunner, and the CapabilityIssuer already migrated in Task 20. Tasks 24-27 add constructor parameters and injection for GateFExecutor, McpRegistry, InferenceHub, and optional transports in the same commits that make those consumers enforce the gate; do not introduce temporarily unused parameters here.
- [ ] Finalize the phased bootstrap begun in Task 5: secure Merkle + governance + permission documents + AuthorizationStateProvider come first; only VALID health may construct ObservabilityStack/WAL/MicroLedger and the remaining effectful collaborators/directories. INVALID/UNMIGRATED returns the typed recovery exception without those side effects. ABSENT may reach VALID only through the separately audited zero-authority bootstrap paths.
- [ ] Add the sorted, duplicate-free `effects` tuple to action_hash(). Update every live DecisionAction call site in the files above in this same commit. A mutating action with `effects=()` is a programming error converted to Deny. Multi-effect actions declare every family: plugin activation uses `(MCP, PATH_WRITE)`, Kanban correction `(TRANSPORT, NETWORK, PATH_WRITE)`, agentic tools map their concrete tool kind to PATH_WRITE/SHELL/NETWORK, and receipt persistence uses `(PATH_WRITE,)`; genuinely decision-only, non-effectful records keep `effects=()` and tests prove they never reach a sink.
- [ ] ApprovalManager must call gate.require_effect() after taking the task lock and immediately before on_execute/on_resume so a human approval cannot outlive policy health.
- [ ] Run GREEN with the same command.
- [ ] Commit:

~~~bash
git add src/atlas/core/decider/decider.py src/atlas/core/orchestrator.py \
  src/atlas/core/orchestrator_parts/agentic_executor.py \
  src/atlas/core/orchestrator_parts/pipeline_runner.py \
  src/atlas/core/orchestrator_parts/approvals.py \
  src/atlas/core/cold_update_manager.py src/atlas/hermes/kanban_bridge.py \
  src/atlas/mcp/plugin_activator.py src/atlas/mcp/plugin_receipt_broker.py \
  src/atlas/transparency/appeal.py src/atlas/runtime/service_runner.py \
  tests/test_orchestrator_authorization_health.py tests/test_decider.py \
  tests/test_gate_i_service.py tests/test_agentic_executor.py \
  tests/test_cold_update_decider.py tests/test_kanban_bridge.py \
  tests/test_plugin_activator.py tests/test_plugin_receipt_broker.py \
  tests/test_appeal.py
git commit -m "security: deny orchestrator effects on unhealthy authorization"
~~~

### Task 22: Check in an executable, AST-backed effect inventory

**Files:**

- Create: src/atlas/security/effect_inventory.py
- Create: config/effect_paths.json
- Create: tests/test_effect_inventory.py

**Interfaces**

~~~python
class EffectPathStatus(str, Enum):
    MIGRATED = "migrated"
    BLOCKED = "blocked"
    PENDING = "pending"

@dataclass(frozen=True)
class DiscoveredEffect:
    family: EffectKind
    caller: str
    sink: str

def discover_effects(source_root: Path) -> tuple[DiscoveredEffect, ...]:
    """AST-scan direct sinks and report stable module:function caller IDs."""

def validate_effect_inventory(
    source_root: Path,
    inventory_path: Path,
    *,
    forbid_pending: bool,
) -> tuple[str, ...]:
    """Require each (family, caller, sink) once, collected tests, and a real gate."""
~~~

The module CLI is exact:

~~~text
python -m atlas.security.effect_inventory --check [--forbid-pending] [--allow-pending-families CSV] INVENTORY
~~~

`--forbid-pending` and `--allow-pending-families` are mutually exclusive. The
latter permits pending rows only when every family on that row is present in
the supplied CSV; it exists solely for the family-by-family P3 commits. Task 28
and CI always use `--forbid-pending`.

The scanner recognizes these direct sink sets:

- filesystem read/metadata: Path.read_text/read_bytes/open/iterdir/glob/rglob/
  exists/is_file/is_dir/stat/lstat/readlink, builtins.open/os.open in read mode,
  os.read/pread/readlink/listdir/scandir/stat/lstat, and file-object read/readline/
  readlines created from a resolved open call;
- filesystem mutation: Path.write_text/write_bytes/touch/chmod/unlink/rename/
  replace/mkdir/rmdir/symlink_to/hardlink_to; os.replace/unlink/rename/mkdir/
  makedirs/chmod/chown/link/symlink; shutil.copy/copy2/copytree/move/rmtree;
  tempfile file/directory creators; builtins.open/os.open in a
  write/create/append mode; os.write/pwrite/ftruncate; file-object write/
  writelines/truncate created from a resolved open call; tarfile/zipfile/
  shutil archive extraction; shelve/dbm writes; and sqlite3/kuzu connections
  to non-memory paths plus mutating execute/executemany/executescript/commit;
- shell/process: subprocess.run/Popen/call/check_call/check_output,
  asyncio.create_subprocess_exec/create_subprocess_shell, os.system/os.popen,
  os.exec*/spawn*/posix_spawn*, and pty.spawn;
- network/provider: socket.create_connection/connect/getaddrinfo; urllib.request.urlopen;
  sync/async httpx and requests client/request methods; aiohttp client methods;
  LiteLLM completion/acompletion/embedding/aembedding; fal_client.subscribe;
  and Playwright launch/new_context/new_page/goto/fill/click/screenshot/
  evaluate/download/save_as calls;
- MCP/transport: transport.request/notify, McpRegistry.dispatch/start_all/add_server/remove_server;
- messaging: TelegramClient.send_message/answer_callback_query/get_updates and external KanbanBridge.run.
- local listeners: socket.bind/listen, socketserver/TCPServer/HTTPServer
  construction, asyncio.start_server, uvicorn.run, and equivalent imported
  aliases resolved by the scanner.

The 28 aggregate rows in the human table are the exact minimum taxonomy and
must be represented one-for-one in `effects`. They group related public roots;
they are not a substitute for sink-level enumeration. The AST scan generates
the exhaustive `direct_sinks` list, whose `caller` and `sink` values are stable,
fully-qualified symbols and whose `row_id` assigns each tuple to exactly one of
the 28 rows. Every aggregate row starts as pending because HEAD 780b37a has no
authorization-health gate, including rows that already use capabilities.
`current_gates` records only real fully-qualified symbols; `final_gate` is
updated only after that symbol exists and its denial test passes.

“partial” in the human table is an observation, not a gate name or coverage
claim. The JSON `current_gates` field contains only fully-qualified symbols
that really guard at least one listed path; each direct-sink record still shows
which paths bypass them.

| ID | Family | Public entrypoints or root caller | Current gate symbols | Final status |
| --- | --- | --- | --- | --- |
| filesystem.executor_io | path_read/path_write | AtlasExecutor.execute_read/execute_write; file handlers created by atlas.interfaces.exec_api.build_router | atlas.security.capabilities:CapabilityIssuer | migrated |
| filesystem.editor | path_read/path_write | EditorTool.read_file/write_file/apply_diff | atlas.security.capabilities:CapabilityIssuer | migrated |
| filesystem.codegen | path_write | AtlasCoder.code; ToolCoder.code; ParallelCoder.run/run_ensemble; IncrementalCoder.run | none | migrated |
| filesystem.cold_update | path_write | ColdUpdateManager.propose/validate/apply/rollback_applied/tier1_auto_apply/sweep_stale_worktrees; ColdUpdateBatcher.run_batch; GoldenRoute.request; GoldenRouteSession.execute/apply | none | migrated |
| filesystem.self_build | path_write | SelfBuildRunner.run_item/run_item_with_evolution/sweep_stale_worktrees/update_backlog_status | none | migrated |
| filesystem.external_artifacts | path_write | BrowserTool.__init__/screenshot; ImageGenTool.generate; VideoGenTool.generate; StirlingPdfTool.run_operation | partial ExternalFsBridge | migrated |
| filesystem.runtime_persistence | path_read/path_write | TaskPersistence persist/delete/quarantine/lock; ApprovalManager pending-state transitions; CheckpointStore; decision/revert/security-council registries; OperationalWAL.write; MicroLedger.ingest/trim; EventStore; exec_api nonce store | partial Merkle/locks | migrated |
| filesystem.memory_knowledge | path_read/path_write | ErrorRegistry/ApprovedPatternStore/TruthSnapshotStore/ProviderMetricsStore; BlockMemory; MemoryIndex; VectorStore; LessonStore/LessonIndex; GhostReplay; GateH artifacts; KnowledgeBase and graph exporters | partial write gates | migrated |
| filesystem.security_state | path_read/path_write | AuthorizationStore; PendingStore; PiiSurrogate; SentinelGate snapshots; supply-chain/third-party admission artifacts; transparency KeyStore; writer-lock state | partial owner/mode checks | migrated |
| filesystem.mcp_fabric_state | path_read/path_write | PluginReceiptBroker; MCP catalog/config/registry-seed/router-telemetry/tool-usage/workbench stores; Fabric AuthBroker/GateRegistry/ConnectorRegistry | partial Sentinel/Merkle checks | migrated |
| filesystem.business_product_state | path_read/path_write | BusinessCoreEngine store; conversation import; product routes; self-maintenance backlog/pause/research/SOTA state; immunity live-loop state | partial governance gates | migrated |
| shell.executor | shell | AtlasExecutor.execute_exec; PipelineRunner._run_via_executor; EditorTool.run_task/apply_diff; shell handler created by atlas.interfaces.exec_api.build_router | atlas.governance.permission_profile:PermissionProfile; atlas.security.capabilities:CapabilityIssuer | migrated |
| shell.host_tools | shell | EditorTool.detect_editor/open_project; CrawlerTool.crawl; ClaudeCodeTool.delegate | partial SSRFBridge | migrated |
| shell.codegen_update | shell | codegen/cold-update/self-build roots above; LessonRunner.run/run_and_promote; SelfAuditRunner.run/run_cycle | none | migrated |
| shell.repository_automation | shell/path_write | commit_changes/is_atlas_commit; GitCheckpointManager public methods; WorktreeManager create/teardown/session; SwarmCycle/worker/validator roots; handoff generation; bitemporal graph builders; CLI code repo-map | partial Merkle/decider guards | migrated |
| shell.engineering | shell | engineering hypothesis history, incremental review preparer, and reproduction public roots | none | migrated |
| shell.sandbox_runtime | shell | LayeredIsolationSandbox and BwrapJail execution roots | ASTGuard/capability callers only | migrated |
| shell.local_diagnostics | shell | minimal recovery projection of collect_reality with run_checks=False/include_browser=False; exact daemon_state/security_state/service_probe; bounded recent_commits; graph_head_sha; graph_freshness | none | migrated with allow_when_authorization_invalid=true |
| network.executor | network | CapabilityIssuer.issue_network; AtlasExecutor.execute_network | atlas.security.capabilities:CapabilityIssuer; atlas.security.ssrf_bridge:SSRFBridge | migrated |
| network.inference_embeddings | provider/network | InferenceHub.infer/infer_for_role/probe_provider; LiteLLMEmbedder.embed/embed_batch; FastEmbedEmbedder construction on process-cache miss; ShadowModel.respond | none | migrated |
| network.provider_observation | network/provider/shell | discover_available_models; check_provider_status; ProviderSmokeRunner.run; MaintenanceFacade provider smoke/discovery/status ticks | partial SSRFBridge | migrated |
| network.tools_sources_connectors | network | HttpApiSource.fetch; BrowserTool.launch/navigate/fill/click/extract/close; CrawlerTool.crawl; HomeAssistantTool list/get/call; GmailReadOnlyConnector.list_messages | partial SSRFBridge | migrated |
| network.media_pdf | network | ImageGenTool.generate; VideoGenTool.generate; StirlingPdfTool.run_operation | partial ExternalFsBridge | migrated |
| mcp.registry_transports | mcp/transport/network | McpRegistry start/ensure/add/remove/dispatch/revet_all; StdioTransport start/request/notify; HttpMcpTransport request/notify; run_stage2a_stdio/run_stage2b_http | partial SentinelGate/SSRFBridge | migrated |
| mcp.adoption | mcp/path_write/shell/network | download_and_verify; safe_extract; scan_source; SpawnTrial.probe_cmd/probe_entry; PluginMaterializer.materialize_local; PluginActivator.activate/approve_activation/revoke | partial SentinelGate/SSRFBridge | migrated |
| external_messaging.telegram | messaging/network | Orchestrator.start_telegram_bot; TelegramClient get_updates/send_message/answer_callback_query; TelegramBot.run_polling/notify_all; runtime.watchdog.run_once sender | atlas.interfaces.telegram_bot:TelegramAuthorizer | migrated |
| external_messaging.hermes_kanban | transport/network/path_write | HermesKanbanAdapter health/enqueue/result/status/cancel; KanbanBridge run/reachable/create/list/diagnostics/repair/propose/show/comment/complete/stats | atlas.hermes.kanban_bridge:ssh_destination_is_allowed | migrated |
| service.local_listeners | local_listener/network | AtlasServiceRunner.start; PrometheusExporter.start; atlas.interfaces.dashboard.serve; atlas.api.server.serve; atlas.api.coding_server.serve | loopback bind validation only | migrated |

The JSON schema is factual rather than aspirational:

~~~python
class EffectInventoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    family: tuple[EffectKind, ...]
    entrypoints: tuple[str, ...]
    current_gates: tuple[str, ...]
    final_gate: str | None
    uses_capability_executor: bool
    status: EffectPathStatus
    allow_when_authorization_invalid: bool
    tests: tuple[str, ...]

class DirectSinkRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    family: EffectKind
    caller: str
    sink: str
    row_id: str
    disposition: Literal["guarded_by_entrypoint", "gated_at_sink", "removed"]
    guard_symbol: str | None
    guard_operation: str | None
    tests: tuple[str, ...]

class InfrastructureExemption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    caller: str
    sink: str
    reason: str
    tests: tuple[str, ...]

class EffectInventoryDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    effects: tuple[EffectInventoryEntry, ...]
    direct_sinks: tuple[DirectSinkRecord, ...]
    infrastructure_exemptions: tuple[InfrastructureExemption, ...]
~~~

direct_sinks is the complete stable AST output, not an empty committed list:
each item contains family, module:function caller, normalized sink name, row_id,
disposition, the real fully-qualified guard symbol/operation, and collected
denial tests. `guard_symbol` and `guard_operation` are required for guarded or
gated records and forbidden for removed records. infrastructure_exemptions is allowed only for the migration
atomic writer, Merkle append/rotation, and cleanup of an already-authorized
transaction; each exemption names a test and rationale. No module/function
wildcard is valid.

Coverage identity is the complete `(family, caller, sink)` tuple. One caller
may appear several times when it performs filesystem + shell + network effects;
deduplicating by caller would conceal exactly the multi-effect bypasses this
inventory is intended to expose. A call whose receiver or import alias cannot
be resolved conservatively is an inventory error requiring explicit
disposition, not something the scanner silently ignores.

The scanner performs local data-flow for `Path(...)`, `/` path composition,
open-file handles, sqlite/kuzu connections, and import aliases. It also records
imports of subprocess, socket, HTTP/provider/browser, database, archive, MCP,
and listener libraries; an imported effect library with an unresolved call is
a validation error. String `.replace()` and unrelated `.connect()` methods are
not silently classified as effects: unresolved receiver types fail the check
until a narrow typed resolver or explicit tested disposition is added.

- [ ] Write RED tests that run discovery over src/atlas, resolve import/from-import aliases plus local Path/open/database receiver flow, require stable sorted output, and reject an unregistered temporary direct subprocess/urlopen/write_text/file-handle-write/sqlite-commit/archive-extract/Playwright-launch/uvicorn.run caller. Reject duplicate tuple coverage, unresolved effect-library calls, nonexistent collected tests/guard symbols, and report the known bypasses InferenceHub.infer, StdioTransport.start, TelegramClient._call, EditorTool.open_project, TaskPersistence.persist, MemoryIndex construction, PluginReceiptBroker._save, SentinelGate._save_snapshot, EngineeringIncrementalReviewPreparer._git, WorktreeManager.create, and every current local listener.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_effect_inventory.py -q
~~~

Expected: effect inventory module/config do not exist.

- [ ] Implement the scanner and commit every discovered current direct sink under one of the exact rows or a narrowly named infrastructure exemption. The current scan baseline contains at least 84 textual subprocess calls across 38 modules and 281 filesystem-mutation candidates before AST de-duplication; the checked-in AST result, not those textual counts, is authoritative. A public/protected callable may not use `guarded_by_entrypoint`: it must gate at its own sink/root or be removed. That disposition is allowed only for a private helper when AST callers are exhaustively resolved to one gated public root and the named denial test invokes that root. Set all rows pending now; this task's GREEN uses forbid_pending=False. The final task changes every row to migrated or blocked and uses forbid_pending=True.
- [ ] Run GREEN:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_effect_inventory.py -q -k "not activation"
~~~

- [ ] Commit:

~~~bash
git add src/atlas/security/effect_inventory.py config/effect_paths.json tests/test_effect_inventory.py
git commit -m "security: inventory direct effect paths"
~~~

### Task 23: Bind the only non-VALID recovery diagnostics

**Files:**

- Modify: src/atlas/security/authorization_gate.py
- Modify: src/atlas/logging/merkle_logger.py
- Modify: src/atlas/core/reality.py
- Modify: src/atlas/core/reality_live.py
- Modify: src/atlas/runtime/watchdog.py
- Modify: src/atlas/mcp/operating_trunk.py
- Modify: src/atlas/memory/project_graph.py
- Modify: config/effect_paths.json
- Test: tests/test_recovery_diagnostics.py
- Modify: tests/test_reality.py
- Modify: tests/test_reality_live.py
- Modify: tests/test_runtime_watchdog.py
- Modify: tests/test_mcp_operating_trunk.py
- Modify: tests/test_project_graph.py

Only these exact operations may run while health is non-VALID: the **minimal
recovery projection** of `collect_reality(run_checks=False,
include_browser=False)`; `daemon_state` for exact unit `atlas-core.service`;
`security_state` for the code root; `service_probe`; bounded `recent_commits`;
`graph_head_sha`; `graph_freshness`; and the G1/P1
status commands. Their exact argv/cwd/path/value constraints are package-owned
rules, not overlay grants. `generate_handoff`, graph rebuild,
`collect_reality(run_checks=True)`, `include_browser=True`, notifications,
repairs, arbitrary repo/unit/db paths, and writes are ordinary effects and
remain denied.

The minimal recovery projection is a separate code path: it reports
governance/permission/authorization status, read-only Merkle verification,
the exact daemon probe, and unavailable reasons for every omitted section. It
must not fall through to normal `collect_reality` helpers, construct
`MerkleLogger`, inspect provider configuration, read document bodies, load
Kuzu, or execute Git beyond the individually bound graph operations. Add
`verify_merkle_chain_readonly(log_dir)` which performs no mkdir/chmod/create;
missing or unsafe audit topology returns a typed unavailable/invalid result.

- [ ] Add RED tests for all four health states. Patch each underlying subprocess/read target and prove exact allowed diagnostics run under ABSENT/INVALID/UNMIGRATED, while one argument change in unit/repo/db/commit count, browser inclusion, live checks, graph rebuild, watchdog notification, and any write are rejected before the sink. Assert the minimal reality path neither constructs `MerkleLogger` nor reaches the normal provider/docs/Kuzu helpers, and an unsafe audit symlink is reported without mutation.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_recovery_diagnostics.py tests/test_reality.py tests/test_reality_live.py tests/test_runtime_watchdog.py tests/test_mcp_operating_trunk.py tests/test_project_graph.py -q -k authorization
~~~

Expected: local diagnostic subprocesses have no exact package-owned recovery gate.

- [ ] Require diagnostic operation first, then its diagnostic path rule where applicable. Bind fixed subprocess argv and cwd in code rather than accepting a caller-provided runner contract as authority. Explicitly prove `OperatingTrunk.sanitation_audit` is denied while non-VALID; it becomes available again only in VALID state. Record shell.local_diagnostics as allow_when_authorization_invalid=true and migrated; no other row may set that flag.
- [ ] Run GREEN with the same command and inventory validation with forbid_pending=False.
- [ ] Commit:

~~~bash
git add src/atlas/security/authorization_gate.py src/atlas/logging/merkle_logger.py \
  src/atlas/core/reality.py src/atlas/core/reality_live.py \
  src/atlas/runtime/watchdog.py src/atlas/mcp/operating_trunk.py \
  src/atlas/memory/project_graph.py config/effect_paths.json \
  tests/test_recovery_diagnostics.py tests/test_reality.py \
  tests/test_reality_live.py tests/test_runtime_watchdog.py \
  tests/test_mcp_operating_trunk.py tests/test_project_graph.py
git commit -m "security: bind recovery diagnostics to package policy"
~~~

### Task 24: Close filesystem and shell bypasses

**Files:**

- Modify: src/atlas/tools/editor.py
- Modify: src/atlas/core/atlas_coder.py
- Modify: src/atlas/core/incremental_coder.py
- Modify: src/atlas/core/parallel_coder.py
- Modify: src/atlas/core/tool_coder.py
- Modify: src/atlas/core/orchestrator_parts/gate_f_executor.py
- Modify: src/atlas/core/orchestrator_parts/approvals.py
- Modify: src/atlas/core/orchestrator_parts/maintenance_facade.py
- Modify: src/atlas/core/cold_update_manager.py
- Modify: src/atlas/core/cold_update_batcher.py
- Modify: src/atlas/missions/golden_route.py
- Modify: src/atlas/core/lesson_runner.py
- Modify: src/atlas/core/self_audit.py
- Modify: src/atlas/core/self_maintenance/f26_agentic_dispatch.py
- Modify: src/atlas/core/self_maintenance/f26_gate.py
- Modify: src/atlas/core/self_maintenance/benchmark_gate.py
- Modify: src/atlas/core/self_maintenance/preflight_gate.py
- Modify: src/atlas/core/self_maintenance/root_cause_classifier.py
- Modify: src/atlas/core/self_maintenance/self_build_runner.py
- Modify: src/atlas/core/git_autocommit.py
- Modify: src/atlas/core/git_checkpoint.py
- Modify: src/atlas/core/graphs.py
- Modify: src/atlas/core/handoff.py
- Modify: src/atlas/core/swarm_backend.py
- Modify: src/atlas/core/swarm_cycle.py
- Modify: src/atlas/core/swarm_validate.py
- Modify: src/atlas/engineering/hypotheses.py
- Modify: src/atlas/engineering/incremental.py
- Modify: src/atlas/engineering/reproduction.py
- Modify: src/atlas/security/sandbox.py
- Modify: src/atlas/security/bwrap_jail.py
- Modify: src/atlas/core/checkpoint.py
- Modify: src/atlas/core/decider/decision_record.py
- Modify: src/atlas/core/decider/revert_registry.py
- Modify: src/atlas/core/decider/security_council_registry.py
- Modify: src/atlas/core/orchestrator_parts/task_persistence.py
- Modify: src/atlas/events/store.py
- Modify: src/atlas/logging/operational_wal.py
- Modify: src/atlas/logging/microledger.py
- Modify: src/atlas/core/gate_h.py
- Modify: src/atlas/core/ghost_replay.py
- Modify: src/atlas/core/lesson_store.py
- Modify: src/atlas/knowledge/base.py
- Modify: src/atlas/memory/block_memory.py
- Modify: src/atlas/memory/callgraph_to_kuzu.py
- Modify: src/atlas/memory/lesson_index.py
- Modify: src/atlas/memory/memory_index.py
- Modify: src/atlas/memory/memory_system.py
- Modify: src/atlas/memory/obsidian_to_kuzu.py
- Modify: src/atlas/memory/vector_store.py
- Modify: src/atlas/security/authorization.py
- Modify: src/atlas/security/pending_store.py
- Modify: src/atlas/security/pii_surrogate.py
- Modify: src/atlas/security/sentinel_gate.py
- Modify: src/atlas/security/supply_chain.py
- Modify: src/atlas/security/third_party_admission.py
- Modify: src/atlas/security/writer_lock.py
- Modify: src/atlas/transparency/key_store.py
- Modify: src/atlas/mcp/candidate_triage.py
- Modify: src/atlas/mcp/catalog.py
- Modify: src/atlas/mcp/config.py
- Modify: src/atlas/mcp/plugin_receipt_broker.py
- Modify: src/atlas/mcp/registry_seed.py
- Modify: src/atlas/mcp/router_telemetry.py
- Modify: src/atlas/mcp/tool_usage.py
- Modify: src/atlas/mcp/workbench_compliance.py
- Modify: src/atlas/mcp/workbench_resources.py
- Modify: src/atlas/fabric/auth_broker.py
- Modify: src/atlas/fabric/gates.py
- Modify: src/atlas/fabric/registry.py
- Modify: src/atlas/api/conversation_import.py
- Modify: src/atlas/api/product_routes.py
- Modify: src/atlas/business/core_engine.py
- Modify: src/atlas/core/self_maintenance/backlog.py
- Modify: src/atlas/core/self_maintenance/research_digest.py
- Modify: src/atlas/core/self_maintenance/self_build_pause.py
- Modify: src/atlas/core/self_maintenance/sota_snapshot.py
- Modify: src/atlas/immunity/live_loop.py
- Modify: src/atlas/api/server.py
- Modify: src/atlas/interfaces/exec_api.py
- Modify: src/atlas/interfaces/cli.py
- Modify: src/atlas/core/orchestrator.py
- Modify: src/atlas/tools/claude_code_tool.py
- Modify: config/effect_paths.json
- Modify: tests/test_effect_inventory.py
- Modify: tests/test_gate_f_executor_fs.py
- Modify: tests/test_exec_api.py
- Modify: tests/test_orchestrator_gate_f.py
- Modify: tests/test_editor.py
- Modify: tests/test_atlas_coder.py
- Modify: tests/test_incremental_coder.py
- Modify: tests/test_parallel_coder_sync.py
- Modify: tests/test_tool_coder.py
- Modify: tests/test_f26_agentic_dispatch.py
- Modify: tests/test_f26_gate.py
- Modify: tests/test_benchmark_gate.py
- Modify: tests/test_preflight_gate.py
- Modify: tests/test_root_cause_classifier.py
- Modify: tests/test_self_build_runner.py
- Modify: tests/test_cold_update_manager.py
- Modify: tests/test_cold_update_decider.py
- Modify: tests/test_cold_update_batcher.py
- Modify: tests/test_golden_route.py
- Modify: tests/test_claude_code_tool.py
- Modify: tests/test_lesson_runner.py
- Modify: tests/test_self_audit.py
- Modify: tests/test_maintenance_facade_research_report.py
- Modify: tests/test_git_autocommit.py
- Modify: tests/test_git_checkpoint.py
- Modify: tests/test_graphs.py
- Modify: tests/test_handoff.py
- Modify: tests/test_swarm_backend.py
- Modify: tests/test_swarm_cycle.py
- Modify: tests/test_swarm_validate.py
- Modify: tests/test_engineering_hypotheses.py
- Modify: tests/test_engineering_incremental.py
- Modify: tests/test_engineering_reproduction.py
- Modify: tests/test_sandbox.py
- Modify: tests/test_bwrap_jail.py
- Modify: tests/test_os_api.py
- Modify: tests/test_task_persistence_quarantine.py
- Modify: tests/test_task_persistence_recovery.py
- Modify: tests/test_operational_wal.py
- Modify: tests/test_os_event_store.py
- Modify: tests/test_gate_h.py
- Modify: tests/test_ghost_replay.py
- Modify: tests/test_lesson_store.py
- Modify: tests/test_knowledge_base.py
- Modify: tests/test_block_memory.py
- Modify: tests/test_memory_index.py
- Modify: tests/test_vector_store.py
- Modify: tests/test_authorization.py
- Modify: tests/test_pii_surrogate.py
- Modify: tests/test_sentinel_gate.py
- Modify: tests/test_supply_chain_scan.py
- Modify: tests/test_third_party_admission.py
- Modify: tests/test_plugin_receipt_broker.py
- Modify: tests/test_mcp_catalog_structured.py
- Modify: tests/test_mcp_registry_seed.py
- Modify: tests/test_router_telemetry.py
- Modify: tests/test_os_fabric.py
- Modify: tests/test_os_memory_import.py
- Modify: tests/test_os_product_api.py
- Modify: tests/test_os_business.py
- Modify: tests/test_self_maintenance_backlog.py
- Modify: tests/test_research_digest.py
- Modify: tests/test_self_build_pause.py
- Create: tests/test_authorization_runtime_persistence.py
- Create: tests/test_authorization_memory_persistence.py
- Create: tests/test_authorization_security_persistence.py
- Create: tests/test_authorization_mcp_fabric_persistence.py
- Create: tests/test_authorization_business_persistence.py

**Interface rule**

Every listed public root receives AuthorizationGate in its constructor or
function arguments and calls `require_effect(PATH_WRITE|SHELL,
stable-operation-ID)` immediately before **each** matching direct sink, not
only once before a long workflow. This includes ColdUpdateManager
propose/validate/apply/rollback_applied/tier1_auto_apply/sweep_stale_worktrees,
ColdUpdateBatcher.run_batch, GoldenRoute.request, GoldenRouteSession
execute/apply, LessonRunner run/run_and_promote, SelfAuditRunner run/run_cycle,
all repository/swarm/engineering/sandbox roots assigned by Task 22, the API
approval subprocess, the CLI repo-map subprocess, and ClaudeCodeTool.delegate.
Private cleanup after a started, authorized transaction may complete on
failure only with an inventory exemption bound to that acquired transaction;
starting a new cleanup sweep requires a fresh gate check.

#### Task 24a: Gate editor, Gate F, and exec API sinks

**Slice files:** `src/atlas/tools/editor.py`,
`src/atlas/core/orchestrator_parts/gate_f_executor.py`,
`src/atlas/interfaces/exec_api.py`, `src/atlas/api/server.py`,
`src/atlas/core/orchestrator.py`, `config/effect_paths.json`,
`tests/test_editor.py`, `tests/test_gate_f_executor_fs.py`,
`tests/test_exec_api.py`, `tests/test_orchestrator_gate_f.py`, and
`tests/test_effect_inventory.py`.

- [ ] Add RED tests for INVALID/UNMIGRATED editor read/write/run/apply/open,
  Gate F filesystem/desktop actions, nonce-store writes, and exec API
  shell/file handlers. Patch each raw sink and assert zero calls.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_editor.py tests/test_gate_f_executor_fs.py tests/test_exec_api.py tests/test_orchestrator_gate_f.py -q -k authorization
~~~

- [ ] Inject the same Orchestrator gate through `build_router()` and
  GateFExecutor; revalidate PATH_READ/PATH_WRITE/SHELL immediately before each
  sink and migrate only `filesystem.executor_io`, `filesystem.editor`, and
  `shell.executor` tuples proven by these tests.
- [ ] Run GREEN with the same command and
  `PYTHONPATH=src .venv/bin/python -m pytest tests/test_effect_inventory.py -q`.
- [ ] Commit:

~~~bash
git add src/atlas/tools/editor.py src/atlas/core/orchestrator_parts/gate_f_executor.py src/atlas/interfaces/exec_api.py src/atlas/api/server.py src/atlas/core/orchestrator.py config/effect_paths.json tests/test_editor.py tests/test_gate_f_executor_fs.py tests/test_exec_api.py tests/test_orchestrator_gate_f.py tests/test_effect_inventory.py
git commit -m "security: gate editor and exec API effects"
~~~

#### Task 24b: Gate code-generation and host-tool sinks

**Slice files:** `src/atlas/core/atlas_coder.py`,
`src/atlas/core/incremental_coder.py`, `src/atlas/core/parallel_coder.py`,
`src/atlas/core/tool_coder.py`, `src/atlas/tools/claude_code_tool.py`,
`src/atlas/interfaces/cli.py`, `src/atlas/core/orchestrator.py`,
`config/effect_paths.json`, their five named test modules, and
`tests/test_effect_inventory.py`.

- [ ] Add RED denial and two-sink drift tests for every coder run/code root,
  ClaudeCodeTool.delegate, and CLI repo-map; assert the later
  subprocess/write is untouched.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_atlas_coder.py tests/test_incremental_coder.py tests/test_parallel_coder_sync.py tests/test_tool_coder.py tests/test_claude_code_tool.py -q -k authorization
~~~

- [ ] Inject/wire the gate at constructors and free-function call sites,
  revalidate PATH_WRITE and SHELL separately, then migrate
  `filesystem.codegen`, `shell.host_tools`, and the codegen portion of
  `shell.codegen_update`.
- [ ] Run GREEN with the same command plus the inventory test.
- [ ] Commit:

~~~bash
git add src/atlas/core/atlas_coder.py src/atlas/core/incremental_coder.py src/atlas/core/parallel_coder.py src/atlas/core/tool_coder.py src/atlas/tools/claude_code_tool.py src/atlas/interfaces/cli.py src/atlas/core/orchestrator.py config/effect_paths.json tests/test_atlas_coder.py tests/test_incremental_coder.py tests/test_parallel_coder_sync.py tests/test_tool_coder.py tests/test_claude_code_tool.py tests/test_effect_inventory.py
git commit -m "security: gate code-generation effects"
~~~

#### Task 24c: Gate ColdUpdate and Golden Route transactions

**Slice files:** `src/atlas/core/cold_update_manager.py`,
`src/atlas/core/cold_update_batcher.py`,
`src/atlas/missions/golden_route.py`, `src/atlas/core/orchestrator.py`,
`config/effect_paths.json`, `tests/test_cold_update_manager.py`,
`tests/test_cold_update_decider.py`, `tests/test_cold_update_batcher.py`,
`tests/test_golden_route.py`, and `tests/test_effect_inventory.py`.

- [ ] Add RED denial tests for every named public transaction root and a drift
  test between worktree creation, patch write, validation subprocess, and
  apply. Only cleanup of the transaction-owned worktree may run after drift.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_cold_update_manager.py tests/test_cold_update_decider.py tests/test_cold_update_batcher.py tests/test_golden_route.py -q -k authorization
~~~

- [ ] Gate each PATH_WRITE/SHELL sink, record the acquired-worktree cleanup
  exemption with its denial test, and migrate `filesystem.cold_update` only
  when all assigned tuples are green.
- [ ] Run GREEN with the same command plus the inventory test.
- [ ] Commit:

~~~bash
git add src/atlas/core/cold_update_manager.py src/atlas/core/cold_update_batcher.py src/atlas/missions/golden_route.py src/atlas/core/orchestrator.py config/effect_paths.json tests/test_cold_update_manager.py tests/test_cold_update_decider.py tests/test_cold_update_batcher.py tests/test_golden_route.py tests/test_effect_inventory.py
git commit -m "security: gate cold-update transactions"
~~~

#### Task 24d: Gate self-maintenance and self-build sinks

**Slice files:** maintenance_facade, lesson_runner, self_audit, all five listed
self_maintenance gate/dispatch modules, self_build_runner, Orchestrator,
`config/effect_paths.json`, and their tests declared in the Task 24 file list.

- [ ] Add RED denial tests for every F2.6/preflight/benchmark/root-cause,
  LessonRunner, SelfAudit, maintenance, and SelfBuild entrypoint plus drift
  between two self-build sinks.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_f26_agentic_dispatch.py tests/test_f26_gate.py tests/test_benchmark_gate.py tests/test_preflight_gate.py tests/test_root_cause_classifier.py tests/test_self_build_runner.py tests/test_lesson_runner.py tests/test_self_audit.py tests/test_maintenance_facade_research_report.py -q -k authorization
~~~

- [ ] Gate every PATH_WRITE/SHELL sink and migrate
  `filesystem.self_build` plus the remaining
  `shell.codegen_update` tuples.
- [ ] Run GREEN with the same command plus the inventory test.
- [ ] Commit only the exact production/test paths named by this slice and
  `config/effect_paths.json`:

~~~bash
git add src/atlas/core/orchestrator_parts/maintenance_facade.py src/atlas/core/lesson_runner.py src/atlas/core/self_audit.py src/atlas/core/self_maintenance/f26_agentic_dispatch.py src/atlas/core/self_maintenance/f26_gate.py src/atlas/core/self_maintenance/benchmark_gate.py src/atlas/core/self_maintenance/preflight_gate.py src/atlas/core/self_maintenance/root_cause_classifier.py src/atlas/core/self_maintenance/self_build_runner.py src/atlas/core/orchestrator.py config/effect_paths.json tests/test_f26_agentic_dispatch.py tests/test_f26_gate.py tests/test_benchmark_gate.py tests/test_preflight_gate.py tests/test_root_cause_classifier.py tests/test_self_build_runner.py tests/test_lesson_runner.py tests/test_self_audit.py tests/test_maintenance_facade_research_report.py tests/test_effect_inventory.py
git commit -m "security: gate self-maintenance effects"
~~~

#### Task 24e: Gate repository and swarm automation

**Slice files:** git_autocommit, git_checkpoint, graphs, handoff,
swarm_backend, swarm_cycle, swarm_validate, CLI,
`config/effect_paths.json`, and their seven declared tests.

- [ ] Add RED denial tests for every public Git/worktree/graph/handoff/swarm
  root and drift after the first worktree/subprocess sink.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_git_autocommit.py tests/test_git_checkpoint.py tests/test_graphs.py tests/test_handoff.py tests/test_swarm_backend.py tests/test_swarm_cycle.py tests/test_swarm_validate.py -q -k authorization
~~~

- [ ] Gate PATH_WRITE/SHELL at each sink and migrate
  `shell.repository_automation` only after its complete tuple set passes.
- [ ] Run GREEN with the same command plus the inventory test.
- [ ] Commit:

~~~bash
git add src/atlas/core/git_autocommit.py src/atlas/core/git_checkpoint.py src/atlas/core/graphs.py src/atlas/core/handoff.py src/atlas/core/swarm_backend.py src/atlas/core/swarm_cycle.py src/atlas/core/swarm_validate.py src/atlas/interfaces/cli.py config/effect_paths.json tests/test_git_autocommit.py tests/test_git_checkpoint.py tests/test_graphs.py tests/test_handoff.py tests/test_swarm_backend.py tests/test_swarm_cycle.py tests/test_swarm_validate.py tests/test_effect_inventory.py
git commit -m "security: gate repository automation effects"
~~~

#### Task 24f: Gate engineering and sandbox execution

**Slice files:** engineering hypotheses/incremental/reproduction,
LayeredIsolationSandbox, BwrapJail, Orchestrator, EditorTool,
`config/effect_paths.json`, and their five declared tests.

- [ ] Add RED denial tests for every engineering reproduction/review history
  sink and sandbox/Bwrap execution; prove Orchestrator and Editor pass the
  required gate and no compatibility default creates an always-valid gate.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_engineering_hypotheses.py tests/test_engineering_incremental.py tests/test_engineering_reproduction.py tests/test_sandbox.py tests/test_bwrap_jail.py -q -k authorization
~~~

- [ ] Gate each SHELL/PATH_WRITE sink and migrate `shell.engineering` and
  `shell.sandbox_runtime`.
- [ ] Run GREEN with the same command plus the inventory test.
- [ ] Commit:

~~~bash
git add src/atlas/engineering/hypotheses.py src/atlas/engineering/incremental.py src/atlas/engineering/reproduction.py src/atlas/security/sandbox.py src/atlas/security/bwrap_jail.py src/atlas/core/orchestrator.py src/atlas/tools/editor.py config/effect_paths.json tests/test_engineering_hypotheses.py tests/test_engineering_incremental.py tests/test_engineering_reproduction.py tests/test_sandbox.py tests/test_bwrap_jail.py tests/test_effect_inventory.py
git commit -m "security: gate engineering and sandbox effects"
~~~

#### Task 24g: Gate runtime persistence

**Slice files:** checkpoint, decision_record, revert_registry,
security_council_registry, approvals, task_persistence, EventStore,
OperationalWAL, MicroLedger, Orchestrator, the new
`tests/test_authorization_runtime_persistence.py`, and the inventory.

- [ ] In the new parametrized RED suite call every public persist/delete/write/
  ingest/trim/checkpoint root under INVALID and UNMIGRATED; add one post-start
  drift case and assert every file/SQLite sink is untouched.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_authorization_runtime_persistence.py tests/test_task_persistence_quarantine.py tests/test_task_persistence_recovery.py tests/test_operational_wal.py tests/test_os_event_store.py -q
~~~

- [ ] Inject or pass the shared gate at the public store boundary immediately
  enclosing each raw sink and migrate `filesystem.runtime_persistence`.
- [ ] Run GREEN with the same command plus the inventory test.
- [ ] Commit:

~~~bash
git add src/atlas/core/checkpoint.py src/atlas/core/decider/decision_record.py src/atlas/core/decider/revert_registry.py src/atlas/core/decider/security_council_registry.py src/atlas/core/orchestrator_parts/approvals.py src/atlas/core/orchestrator_parts/task_persistence.py src/atlas/events/store.py src/atlas/logging/operational_wal.py src/atlas/logging/microledger.py src/atlas/core/orchestrator.py config/effect_paths.json tests/test_authorization_runtime_persistence.py tests/test_task_persistence_quarantine.py tests/test_task_persistence_recovery.py tests/test_operational_wal.py tests/test_os_event_store.py tests/test_effect_inventory.py
git commit -m "security: gate runtime persistence"
~~~

#### Task 24h: Gate memory and knowledge persistence

**Slice files:** GateH, GhostReplay, LessonStore, KnowledgeBase, BlockMemory,
callgraph/Obsidian Kuzu exporters, LessonIndex, MemoryIndex, MemorySystem,
VectorStore, Orchestrator, the new memory-persistence test, and the inventory.

- [ ] Add RED INVALID/UNMIGRATED and drift tests for every public add/record/
  write/delete/rebuild/export root, including sqlite/kuzu commit and vector
  directory deletion.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_authorization_memory_persistence.py tests/test_gate_h.py tests/test_ghost_replay.py tests/test_lesson_store.py tests/test_knowledge_base.py tests/test_block_memory.py tests/test_memory_index.py tests/test_vector_store.py -q
~~~

- [ ] Gate every PATH_WRITE/database sink and migrate
  `filesystem.memory_knowledge`; read-only queries use PATH_READ and remain
  unavailable while health is non-VALID unless Task 23 explicitly listed them.
- [ ] Run GREEN with the same command plus the inventory test.
- [ ] Commit:

~~~bash
git add src/atlas/core/gate_h.py src/atlas/core/ghost_replay.py src/atlas/core/lesson_store.py src/atlas/knowledge/base.py src/atlas/memory/block_memory.py src/atlas/memory/callgraph_to_kuzu.py src/atlas/memory/lesson_index.py src/atlas/memory/memory_index.py src/atlas/memory/memory_system.py src/atlas/memory/obsidian_to_kuzu.py src/atlas/memory/vector_store.py src/atlas/core/orchestrator.py config/effect_paths.json tests/test_authorization_memory_persistence.py tests/test_gate_h.py tests/test_ghost_replay.py tests/test_lesson_store.py tests/test_knowledge_base.py tests/test_block_memory.py tests/test_memory_index.py tests/test_vector_store.py tests/test_effect_inventory.py
git commit -m "security: gate memory persistence"
~~~

#### Task 24i: Gate security-state persistence

**Slice files:** authorization, PendingStore, PiiSurrogate, SentinelGate,
supply_chain, third_party_admission, writer_lock, transparency KeyStore,
Orchestrator, the new security-persistence test, and the inventory.

- [ ] Add RED denial/drift cases for each token/pending/surrogate/snapshot/
  report/key/lock write and prove Merkle/migration primitives are the only
  infrastructure exemptions.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_authorization_security_persistence.py tests/test_authorization.py tests/test_pii_surrogate.py tests/test_sentinel_gate.py tests/test_supply_chain_scan.py tests/test_third_party_admission.py -q
~~~

- [ ] Gate every non-exempt PATH_WRITE sink and migrate
  `filesystem.security_state`.
- [ ] Run GREEN with the same command plus the inventory test.
- [ ] Commit:

~~~bash
git add src/atlas/security/authorization.py src/atlas/security/pending_store.py src/atlas/security/pii_surrogate.py src/atlas/security/sentinel_gate.py src/atlas/security/supply_chain.py src/atlas/security/third_party_admission.py src/atlas/security/writer_lock.py src/atlas/transparency/key_store.py src/atlas/core/orchestrator.py config/effect_paths.json tests/test_authorization_security_persistence.py tests/test_authorization.py tests/test_pii_surrogate.py tests/test_sentinel_gate.py tests/test_supply_chain_scan.py tests/test_third_party_admission.py tests/test_effect_inventory.py
git commit -m "security: gate security-state persistence"
~~~

#### Task 24j: Gate MCP and Fabric persistence

**Slice files:** candidate_triage, catalog, config, PluginReceiptBroker,
registry_seed, router_telemetry, tool_usage, workbench compliance/resources,
Fabric AuthBroker/GateRegistry/ConnectorRegistry, Orchestrator, the new
MCP/Fabric persistence test, and the inventory.

- [ ] Add RED denial/drift cases for every catalog/receipt/config/seed/
  telemetry/usage/workbench/credential/gate/connector write; raw values and
  credentials never enter denial audit payloads.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_authorization_mcp_fabric_persistence.py tests/test_plugin_receipt_broker.py tests/test_mcp_catalog_structured.py tests/test_mcp_registry_seed.py tests/test_router_telemetry.py tests/test_os_fabric.py -q
~~~

- [ ] Gate every PATH_WRITE sink and migrate
  `filesystem.mcp_fabric_state`; Task 26 separately gates transport/adoption
  network and process effects.
- [ ] Run GREEN with the same command plus the inventory test.
- [ ] Commit:

~~~bash
git add src/atlas/mcp/candidate_triage.py src/atlas/mcp/catalog.py src/atlas/mcp/config.py src/atlas/mcp/plugin_receipt_broker.py src/atlas/mcp/registry_seed.py src/atlas/mcp/router_telemetry.py src/atlas/mcp/tool_usage.py src/atlas/mcp/workbench_compliance.py src/atlas/mcp/workbench_resources.py src/atlas/fabric/auth_broker.py src/atlas/fabric/gates.py src/atlas/fabric/registry.py src/atlas/core/orchestrator.py config/effect_paths.json tests/test_authorization_mcp_fabric_persistence.py tests/test_plugin_receipt_broker.py tests/test_mcp_catalog_structured.py tests/test_mcp_registry_seed.py tests/test_router_telemetry.py tests/test_os_fabric.py tests/test_effect_inventory.py
git commit -m "security: gate MCP and Fabric persistence"
~~~

#### Task 24k: Gate business and maintenance-state persistence

**Slice files:** conversation_import, product_routes, BusinessCoreEngine,
self-maintenance backlog/research_digest/self_build_pause/sota_snapshot,
immunity live_loop, Orchestrator, the new business-persistence test, and the
inventory.

- [ ] Add RED denial/drift cases for import/product/business mutations and
  every backlog/pause/research/SOTA/live-loop state write.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_authorization_business_persistence.py tests/test_os_memory_import.py tests/test_os_product_api.py tests/test_os_business.py tests/test_self_maintenance_backlog.py tests/test_research_digest.py tests/test_self_build_pause.py -q
~~~

- [ ] Gate every PATH_WRITE sink and migrate
  `filesystem.business_product_state`.
- [ ] Run GREEN with the same command plus the inventory test.
- [ ] Commit:

~~~bash
git add src/atlas/api/conversation_import.py src/atlas/api/product_routes.py src/atlas/business/core_engine.py src/atlas/core/self_maintenance/backlog.py src/atlas/core/self_maintenance/research_digest.py src/atlas/core/self_maintenance/self_build_pause.py src/atlas/core/self_maintenance/sota_snapshot.py src/atlas/immunity/live_loop.py src/atlas/core/orchestrator.py config/effect_paths.json tests/test_authorization_business_persistence.py tests/test_os_memory_import.py tests/test_os_product_api.py tests/test_os_business.py tests/test_self_maintenance_backlog.py tests/test_research_digest.py tests/test_self_build_pause.py tests/test_effect_inventory.py
git commit -m "security: gate business persistence"
~~~

- [ ] After all 24a-24k commits, run the aggregate filesystem/shell inventory;
  it must report zero pending tuples in those families and no wildcard or
  uncollected-test disposition:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_effect_inventory.py -q
PYTHONPATH=src .venv/bin/python -m atlas.security.effect_inventory --check --allow-pending-families network,provider,mcp,transport,messaging,local_listener config/effect_paths.json
~~~

### Task 25: Close network, provider, browser, and connector bypasses

**Files:**

- Modify: src/atlas/core/inference_hub.py
- Modify: src/atlas/core/orchestrator.py
- Modify: src/atlas/acp/server.py
- Modify: src/atlas/api/coding_server.py
- Modify: src/atlas/core/deliberation_council.py
- Modify: src/atlas/core/parallel_coder.py
- Modify: src/atlas/core/self_maintenance/f26_agentic_dispatch.py
- Modify: src/atlas/interfaces/cli.py
- Modify: src/atlas/core/provider_discovery.py
- Modify: src/atlas/core/provider_status.py
- Modify: src/atlas/core/self_maintenance/provider_smoke.py
- Modify: src/atlas/core/orchestrator_parts/maintenance_facade.py
- Modify: src/atlas/memory/embeddings.py
- Modify: src/atlas/security/shadow_model.py
- Modify: src/atlas/tools/browser.py
- Modify: src/atlas/tools/crawler.py
- Modify: src/atlas/tools/image_gen_tool.py
- Modify: src/atlas/tools/video_gen_tool.py
- Modify: src/atlas/tools/stirling_pdf_tool.py
- Modify: src/atlas/tools/home_assistant_tool.py
- Modify: src/atlas/fabric/connectors/gmail.py
- Modify: src/atlas/knowledge/sources.py
- Modify: config/effect_paths.json
- Modify: tests/test_inference_hub_real.py
- Create: tests/test_inference_gate_wiring.py
- Modify: tests/test_atlas_core.py
- Modify: tests/test_acp_server.py
- Modify: tests/test_deliberation_council.py
- Modify: tests/test_parallel_coder_sync.py
- Modify: tests/test_f26_agentic_dispatch.py
- Modify: tests/test_embeddings.py
- Modify: tests/test_shadow_model.py
- Modify: tests/test_provider_discovery.py
- Modify: tests/test_provider_status.py
- Modify: tests/test_provider_smoke.py
- Modify: tests/test_maintenance_provider_discovery_tick.py
- Modify: tests/test_maintenance_provider_status_tick.py
- Modify: tests/test_self_improvement_wiring.py
- Modify: tests/test_browser.py
- Modify: tests/test_crawler.py
- Modify: tests/test_image_gen_tool.py
- Modify: tests/test_video_gen_tool.py
- Modify: tests/test_stirling_pdf_tool.py
- Modify: tests/test_home_assistant_tool.py
- Modify: tests/test_os_gmail_connector.py
- Modify: tests/test_knowledge_sources.py

**Interface rule**

- InferenceHub requires gate: AuthorizationGate. infer(), infer_for_role(), and probe_provider() call require_effect(PROVIDER, operation) before provider selection; stub-only inference is allowed only when no provider/network/subprocess is invoked and is inventoried as blocked-from-effect.
- Network helpers take gate: AuthorizationGate as an explicit keyword-only argument. Fakes in tests do not bypass the gate; the gate runs before the injected fetcher.
- Browser screenshot/fill/click/extract require NETWORK because they affect an external browser session; screenshot also requires PATH_WRITE before saving.
- LiteLLMEmbedder checks NETWORK before each hosted embedding call. FastEmbedEmbedder checks NETWORK before constructing TextEmbedding on a process-cache miss because that constructor may download; a process-cache hit is local and has a dedicated no-network test. ShadowModel.respond checks PROVIDER before its LiteLLM backend.

#### Task 25a: Require AuthorizationGate at every InferenceHub construction

**Slice files:** inference_hub, Orchestrator, ACP server, coding server,
DeliberationCouncil, ParallelCoder, F2.6 agentic dispatch, CLI,
MaintenanceFacade, `tests/test_inference_gate_wiring.py`, their existing
wiring tests, and the inventory.

- [ ] Add RED tests that instantiate each productive InferenceHub call site
  with no gate and require a type/runtime failure, then prove INVALID and
  UNMIGRATED stop infer/infer_for_role/probe_provider before provider
  selection. No optional/default gate is permitted; stub-only mode has a
  separate zero-effect test.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_inference_hub_real.py tests/test_inference_gate_wiring.py tests/test_atlas_core.py tests/test_acp_server.py tests/test_deliberation_council.py tests/test_parallel_coder_sync.py tests/test_f26_agentic_dispatch.py tests/test_maintenance_provider_discovery_tick.py -q -k authorization
~~~

- [ ] Make `gate: AuthorizationGate` required and keyword-only, update every
  source/test constructor in this slice, and gate PROVIDER immediately before
  each provider call. Mark only the proven
  `network.inference_embeddings` InferenceHub tuples migrated.
- [ ] Run GREEN with the same command plus the inventory test.
- [ ] Commit:

~~~bash
git add src/atlas/core/inference_hub.py src/atlas/core/orchestrator.py src/atlas/acp/server.py src/atlas/api/coding_server.py src/atlas/core/deliberation_council.py src/atlas/core/parallel_coder.py src/atlas/core/self_maintenance/f26_agentic_dispatch.py src/atlas/interfaces/cli.py src/atlas/core/orchestrator_parts/maintenance_facade.py config/effect_paths.json tests/test_inference_hub_real.py tests/test_inference_gate_wiring.py tests/test_atlas_core.py tests/test_acp_server.py tests/test_deliberation_council.py tests/test_parallel_coder_sync.py tests/test_f26_agentic_dispatch.py tests/test_maintenance_provider_discovery_tick.py tests/test_effect_inventory.py
git commit -m "security: require gated inference wiring"
~~~

#### Task 25b: Gate provider discovery, status, and smoke

**Slice files:** provider_discovery, provider_status, provider_smoke,
MaintenanceFacade, Orchestrator, their five provider tests, and the inventory.

- [ ] Add RED INVALID/UNMIGRATED and mid-probe drift cases for discovery,
  status, smoke, and all three maintenance ticks; patch HTTP/provider/
  subprocess sinks and assert zero calls after denial.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_provider_discovery.py tests/test_provider_status.py tests/test_provider_smoke.py tests/test_maintenance_provider_discovery_tick.py tests/test_maintenance_provider_status_tick.py -q -k authorization
~~~

- [ ] Require PROVIDER/NETWORK/SHELL at their respective immediate sinks,
  preserve SSRFBridge after health where a URL exists, and migrate
  `network.provider_observation`.
- [ ] Run GREEN with the same command plus the inventory test.
- [ ] Commit:

~~~bash
git add src/atlas/core/provider_discovery.py src/atlas/core/provider_status.py src/atlas/core/self_maintenance/provider_smoke.py src/atlas/core/orchestrator_parts/maintenance_facade.py src/atlas/core/orchestrator.py config/effect_paths.json tests/test_provider_discovery.py tests/test_provider_status.py tests/test_provider_smoke.py tests/test_maintenance_provider_discovery_tick.py tests/test_maintenance_provider_status_tick.py tests/test_effect_inventory.py
git commit -m "security: gate provider observation"
~~~

#### Task 25c: Gate hosted embeddings and shadow inference

**Slice files:** embeddings, ShadowModel, their tests,
`tests/test_self_improvement_wiring.py`, Orchestrator, and the inventory.

- [ ] Add RED tests for LiteLLM embed/embed_batch, FastEmbed cache miss, and
  ShadowModel.respond under INVALID/UNMIGRATED. A cache hit performs no effect;
  a miss checks NETWORK before TextEmbedding construction.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_embeddings.py tests/test_shadow_model.py tests/test_self_improvement_wiring.py -q -k authorization
~~~

- [ ] Gate every NETWORK/PROVIDER sink and finish the
  `network.inference_embeddings` row only after both InferenceHub and
  embedding/shadow tuple sets are green.
- [ ] Run GREEN with the same command plus the inventory test.
- [ ] Commit:

~~~bash
git add src/atlas/memory/embeddings.py src/atlas/security/shadow_model.py src/atlas/core/orchestrator.py config/effect_paths.json tests/test_embeddings.py tests/test_shadow_model.py tests/test_self_improvement_wiring.py tests/test_effect_inventory.py
git commit -m "security: gate embedding and shadow effects"
~~~

#### Task 25d: Gate browser, crawler, sources, and connectors

**Slice files:** BrowserTool, CrawlerTool, HomeAssistantTool, Gmail connector,
knowledge sources, their tests, Orchestrator, and the inventory.

- [ ] Add RED tests for Browser launch/new-context/page/navigation/fill/click/
  extract/screenshot/download, Crawler subprocess+fetch, source fetch,
  HomeAssistant, and Gmail. Include drift between browser/crawler NETWORK,
  SHELL, download, and PATH_WRITE sinks.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_browser.py tests/test_crawler.py tests/test_home_assistant_tool.py tests/test_os_gmail_connector.py tests/test_knowledge_sources.py -q -k authorization
~~~

- [ ] Revalidate NETWORK/SHELL/PATH_WRITE at every sink, then apply SSRF/path
  checks. `_crawl4ai_worker` may be guarded by CrawlerTool only when AST proves
  it has no other productive caller. Migrate
  `network.tools_sources_connectors` and finish `shell.host_tools`.
- [ ] Run GREEN with the same command plus the inventory test.
- [ ] Commit:

~~~bash
git add src/atlas/tools/browser.py src/atlas/tools/crawler.py src/atlas/tools/home_assistant_tool.py src/atlas/fabric/connectors/gmail.py src/atlas/knowledge/sources.py src/atlas/core/orchestrator.py config/effect_paths.json tests/test_browser.py tests/test_crawler.py tests/test_home_assistant_tool.py tests/test_os_gmail_connector.py tests/test_knowledge_sources.py tests/test_effect_inventory.py
git commit -m "security: gate browser and connector effects"
~~~

#### Task 25e: Gate image, video, and PDF effects

**Slice files:** ImageGenTool, VideoGenTool, StirlingPdfTool, their tests,
Orchestrator, and the inventory.

- [ ] Add RED INVALID/UNMIGRATED tests and drift between hosted generation/
  conversion and artifact write; patch fal/HTTP/subprocess/write sinks.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_image_gen_tool.py tests/test_video_gen_tool.py tests/test_stirling_pdf_tool.py -q -k authorization
~~~

- [ ] Revalidate NETWORK or SHELL before generation/conversion and PATH_WRITE
  before each artifact sink; ExternalFsBridge remains a target check after
  health. Migrate `network.media_pdf` and
  `filesystem.external_artifacts`.
- [ ] Run GREEN with the same command plus the inventory test.
- [ ] Commit:

~~~bash
git add src/atlas/tools/image_gen_tool.py src/atlas/tools/video_gen_tool.py src/atlas/tools/stirling_pdf_tool.py src/atlas/core/orchestrator.py config/effect_paths.json tests/test_image_gen_tool.py tests/test_video_gen_tool.py tests/test_stirling_pdf_tool.py tests/test_effect_inventory.py
git commit -m "security: gate media and PDF effects"
~~~

- [ ] After Tasks 25a-25e, run:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_effect_inventory.py -q
PYTHONPATH=src .venv/bin/python -m atlas.security.effect_inventory --check --allow-pending-families mcp,transport,messaging,local_listener config/effect_paths.json
~~~

### Task 26: Close MCP and transport bypasses

**Files:**

- Modify: src/atlas/mcp/registry.py
- Modify: src/atlas/mcp/transport.py
- Modify: src/atlas/mcp/http_mcp_transport.py
- Modify: src/atlas/mcp/candidate_stage2.py
- Modify: src/atlas/mcp/candidate_fetch.py
- Modify: src/atlas/mcp/candidate_static_scan.py
- Modify: src/atlas/mcp/spawn_trial.py
- Modify: src/atlas/mcp/plugin_materializer.py
- Modify: src/atlas/mcp/plugin_activator.py
- Modify: src/atlas/core/orchestrator.py
- Modify: config/effect_paths.json
- Modify: tests/test_mcp_client.py
- Modify: tests/test_mcp_registry_lazy.py
- Modify: tests/test_http_mcp_transport.py
- Modify: tests/test_candidate_stage2.py
- Modify: tests/test_candidate_fetch.py
- Modify: tests/test_candidate_static_scan.py
- Modify: tests/test_spawn_trial.py
- Modify: tests/test_plugin_materializer.py
- Modify: tests/test_plugin_activator.py
- Modify: tests/test_orchestrator_authorization_health.py

**Interfaces**

~~~python
class McpRegistry:
    def __init__(
        self,
        configs: list[McpServerConfig],
        *,
        gate: AuthorizationGate,
        transport_factory: Callable[[McpServerConfig], McpTransport] | None = None,
        merkle_log: Callable[..., Any] | None = None,
        sentinel: SentinelGate | None = None,
        persist_path: Path | str | None = None,
    ) -> None:
        """Require health before lifecycle, config mutation, re-vetting, or dispatch."""
~~~

- [ ] Add RED tests proving INVALID/UNMIGRATED blocks lazy spawn, eager start, dispatch including read_only tools, add/remove server, stdio Popen, HTTP fetch, Orchestrator desktop MCP dispatch, stage2 stdio/HTTP, candidate download/extract/scan, spawn trials, materialization, activation/approval/revocation before transport/Sentinel/filesystem side effects. Add drift-between-download/extract/materialize and drift-between-start/request tests; every later direct sink must revalidate and remain untouched after drift.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_mcp_client.py tests/test_mcp_registry_lazy.py tests/test_http_mcp_transport.py tests/test_candidate_stage2.py tests/test_candidate_fetch.py tests/test_candidate_static_scan.py tests/test_spawn_trial.py tests/test_plugin_materializer.py tests/test_plugin_activator.py tests/test_orchestrator_authorization_health.py -q -k authorization
~~~

Expected: Sentinel/SSRF exist, but no health gate prevents spawn or tools/call.

- [ ] Apply MCP for registry actions and TRANSPORT/NETWORK at concrete transports, revalidating immediately before every direct sink and checking every family in multi-effect adoption flows. `close_all()` may close only processes recorded as acquired by that registry transaction; it cannot start/re-vet/remove anything and is inventoried as narrowly scoped cleanup.
- [ ] Change mcp.registry_transports and mcp.adoption rows to migrated.
- [ ] Run GREEN with the same command, then inventory validation with forbid_pending=False.
- [ ] Commit:

~~~bash
git add src/atlas/mcp/registry.py src/atlas/mcp/transport.py src/atlas/mcp/http_mcp_transport.py src/atlas/mcp/candidate_stage2.py src/atlas/mcp/candidate_fetch.py src/atlas/mcp/candidate_static_scan.py src/atlas/mcp/spawn_trial.py src/atlas/mcp/plugin_materializer.py src/atlas/mcp/plugin_activator.py src/atlas/core/orchestrator.py config/effect_paths.json tests/test_mcp_client.py tests/test_mcp_registry_lazy.py tests/test_http_mcp_transport.py tests/test_candidate_stage2.py tests/test_candidate_fetch.py tests/test_candidate_static_scan.py tests/test_spawn_trial.py tests/test_plugin_materializer.py tests/test_plugin_activator.py tests/test_orchestrator_authorization_health.py
git commit -m "security: close MCP and transport effect bypasses"
~~~

### Task 27: Close messaging, Hermes/Kanban, and service-surface bypasses

**Files:**

- Modify: src/atlas/interfaces/telegram_bot.py
- Modify: src/atlas/hermes/kanban_bridge.py
- Modify: src/atlas/hermes/hermes.py
- Modify: src/atlas/runtime/watchdog.py
- Modify: src/atlas/runtime/service_runner.py
- Modify: src/atlas/monitoring/prometheus_exporter.py
- Modify: src/atlas/api/server.py
- Modify: src/atlas/api/coding_server.py
- Modify: src/atlas/interfaces/dashboard.py
- Modify: src/atlas/core/orchestrator.py
- Modify: config/effect_paths.json
- Modify: tests/test_telegram_bot.py
- Modify: tests/test_telegram_orchestrator.py
- Modify: tests/test_kanban_bridge.py
- Modify: tests/test_hermes_kanban_adapter.py
- Modify: tests/test_gate_i_service.py
- Modify: tests/test_prometheus_exporter.py
- Modify: tests/test_dashboard.py
- Modify: tests/test_os_api.py
- Modify: tests/test_os_product_api.py
- Create: tests/test_coding_server_authorization.py

- [ ] Add RED tests proving unhealthy authorization blocks Telegram polling/send/callbacks, runtime watchdog notifications, remote and local-mutating Kanban operations, MCP/Telegram starts, and AtlasServiceRunner/Prometheus/API/coding-API/dashboard listener startup. Assert network/subprocess/file/server targets were untouched. Add post-start policy-drift tests before a second poll/send/Kanban/listener sink; the later sink must not run, while closing an already-owned client/listener remains permitted cleanup.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_telegram_bot.py tests/test_telegram_orchestrator.py tests/test_kanban_bridge.py tests/test_hermes_kanban_adapter.py tests/test_gate_i_service.py tests/test_prometheus_exporter.py tests/test_dashboard.py tests/test_os_api.py tests/test_os_product_api.py tests/test_coding_server_authorization.py -q -k authorization
~~~

Expected: each surface has its own auth/SSRF checks but no shared authorization-health gate.

- [ ] Inject the same gate and revalidate immediately before each direct sink. TelegramAuthorizer still decides identity after health; Kanban SSH validation still decides destination after health. Local read-only Kanban diagnostics may use require_diagnostic_read(), while local writes remain blocked. Listener roots require `LOCAL_LISTENER` immediately before bind/uvicorn/HTTPServer construction; no loopback validation substitutes for health.
- [ ] Change telegram, hermes-kanban, and `service.local_listeners` rows to migrated only after every assigned sink/test is green.
- [ ] Run GREEN with the same command.
- [ ] Commit:

~~~bash
git add src/atlas/interfaces/telegram_bot.py src/atlas/hermes/kanban_bridge.py \
  src/atlas/hermes/hermes.py src/atlas/runtime/watchdog.py \
  src/atlas/runtime/service_runner.py src/atlas/monitoring/prometheus_exporter.py \
  src/atlas/api/server.py src/atlas/api/coding_server.py \
  src/atlas/interfaces/dashboard.py src/atlas/core/orchestrator.py \
  config/effect_paths.json tests/test_telegram_bot.py \
  tests/test_telegram_orchestrator.py tests/test_kanban_bridge.py \
  tests/test_hermes_kanban_adapter.py tests/test_gate_i_service.py \
  tests/test_prometheus_exporter.py tests/test_dashboard.py tests/test_os_api.py \
  tests/test_os_product_api.py tests/test_coding_server_authorization.py
git commit -m "security: close messaging and service effect bypasses"
~~~

### Task 28: Make zero-pending effect coverage a release and Gate A prerequisite

**Files:**

- Modify: config/effect_paths.json
- Modify: src/atlas/security/effect_inventory.py
- Modify: .github/workflows/ci.yml
- Modify: tests/test_effect_inventory.py
- Modify: tests/test_audit_runner_and_ci.py
- Modify: src/atlas/core/reality.py
- Modify: tests/test_reality.py
- Create: tests/test_authorization_fail_closed_matrix.py

**Interfaces**

~~~python
def effect_inventory_check() -> dict[str, object]:
    errors = validate_effect_inventory(
        project_root() / "src" / "atlas",
        project_root() / "config" / "effect_paths.json",
        forbid_pending=True,
    )
    return {
        "status": "ok" if not errors else "blocked",
        "pending": 0,
        "errors": list(errors),
    }
~~~

- [ ] Add the final RED test requiring forbid_pending=True, every discovered `(family, caller,sink)` covered exactly once, every row status migrated or blocked, every named test node present and collected, and reality to expose effect_inventory.status/pending/errors.
- [ ] Add an adversarial temporary module containing a new direct subprocess.run and urllib.request.urlopen; assert validation fails with both stable caller IDs.
- [ ] Add a parametrized fail-closed acceptance matrix for ABSENT, INVALID corrupt YAML, INVALID symlink/mode drift, corrupt Merkle, and UNMIGRATED legacy_unknown. For each state exercise a filesystem write, shell execution, direct InferenceHub network/provider call, StdioTransport start, watchdog Telegram send, and a local listener start; patch every sink and assert zero calls. Add the VALID control row using only injected local fakes.
- [ ] Run RED:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_effect_inventory.py tests/test_audit_runner_and_ci.py tests/test_reality.py tests/test_authorization_fail_closed_matrix.py -q
~~~

Expected: pending rows remain or CI/reality does not enforce the inventory.

- [ ] Resolve every remaining discovered caller as migrated through a gate or blocked by removal/unreachability with a test. Do not suppress or wildcard a sink to make the check green.
- [ ] Add this CI step to both supported Python test jobs:

~~~bash
PYTHONPATH=src python -m atlas.security.effect_inventory --check --forbid-pending config/effect_paths.json
~~~

- [ ] Run GREEN:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_effect_inventory.py tests/test_audit_runner_and_ci.py tests/test_reality.py tests/test_authorization_fail_closed_matrix.py -q
MYPYPATH=src .venv/bin/python -m mypy src/atlas/
~~~

- [ ] Commit:

~~~bash
git add config/effect_paths.json src/atlas/security/effect_inventory.py src/atlas/core/reality.py .github/workflows/ci.yml tests/test_effect_inventory.py tests/test_audit_runner_and_ci.py tests/test_reality.py tests/test_authorization_fail_closed_matrix.py
git commit -m "ci: require complete authorization effect coverage"
~~~

---

## Final Verification for G1/P1-P3

- [ ] Confirm the worktree excludes the operator's .gitignore and docs/fixtures changes from every implementation commit:

~~~bash
git status --short
git diff --cached --name-only
~~~

- [ ] Rebuild the structural graph and require graph_commit=head=server_started_head at the final implementation HEAD. Query graph_importers, graph_imports_of, and graph_blast_radius again for atlas.governance.permission_profile, atlas.security.capabilities, atlas.runtime_paths, and atlas.core.orchestrator.
- [ ] Run all focused trust-boundary tests:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_governance_trust_root.py tests/test_governance_migration.py tests/test_governance_cli.py tests/test_governance_wheel_contract.py tests/test_permission_schema_v2.py tests/test_permission_store.py tests/test_permission_migration.py tests/test_permission_cli.py tests/test_permission_precedence.py tests/test_authorization_gate.py tests/test_effect_inventory.py tests/test_capabilities.py tests/test_orchestrator_authorization_health.py tests/test_authorization_fail_closed_matrix.py -q
~~~

- [ ] Run the complete non-browser suite and strict types:

~~~bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -q
MYPYPATH=src .venv/bin/python -m mypy src/atlas/
~~~

- [ ] Verify Merkle integrity in an isolated temporary workspace; do not point one-shot CLI tests at the live workspace:

~~~bash
tmp_workspace="$(mktemp -d)"
chmod 700 "$tmp_workspace"
ATLAS_HOME="$tmp_workspace" PYTHONPATH=src .venv/bin/atlas audit --verify
~~~

- [ ] Build/install the wheel outside the checkout with ATLAS_CORE_ROOT, ATLAS_HOME, and PYTHONPATH unset; assert governance and permission baselines load from atlas.governance.resources and an adversarial data root cannot alter their digests.
- [ ] Run the executable inventory with pending forbidden:

~~~bash
PYTHONPATH=src .venv/bin/python -m atlas.security.effect_inventory --check --forbid-pending config/effect_paths.json
~~~

- [ ] Inspect every migration receipt and denial test for secret leakage. Telegram IDs, passphrase_hash, read_extended values, and legacy canonical values may exist only in 0600 local artifacts; reports and Merkle payloads contain IDs, counts, and digests.
- [ ] Confirm config/governance.json still hashes to d11c0926958b49cd153a7650472d5c557b47dc3445d5d0e1ef99db8ccf0355a8.
- [ ] Confirm atlas-core.service remains stopped. Completion of this plan establishes the trust prerequisite; it does not authorize Gate A or service activation.
