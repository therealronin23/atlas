# Atlas Runtime Recovery R1-R3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover `atlas-core.service` from the Prometheus port collision, give every boot a verifiable identity and readiness projection, make startup/rollback transactional, and prevent persistent failures from producing another systemd restart storm.

**Architecture:** R1 introduces a typed Prometheus configuration boundary, an instance-bound exporter, and an audit-first atomic service-status projection. R2 adds explicit ownership for every acquired component and unwinds that ownership in reverse order on failure or stop. R3 makes readiness compare systemd `MainPID`, the current boot `instance_id`, and enabled endpoints; systemd and the installer then require stable readiness instead of transient `active` state.

**Tech Stack:** Python 3.11+ standard library (`dataclasses`, `enum.StrEnum`, `http.server`, `json`, `os`, `socket`, `tempfile`, `urllib.request`, `uuid`), existing FastAPI/Uvicorn dashboard stack, Click CLI, pytest, mypy strict, Bash and user-level systemd.

## Global Constraints

- Implement only recovery cuts R1, R2, and R3 from `docs/superpowers/specs/2026-08-02-atlas-integrity-recovery-program-design.md`; controlled activation A remains a separate plan and gate.
- Keep `atlas-core.service` stopped throughout implementation. Unit tests use temporary workspaces, loopback sockets, fake clocks, and fake `systemctl`; they never run `atlas serve` against the live workspace.
- `ATLAS_PROMETHEUS_MODE=off|optional|required` is the authoritative mode. During migration, legacy `ATLAS_PROMETHEUS=1|true|yes` maps to `optional`, and absent or `0|false|no` maps to `off`.
- If both mode variables are present, they must resolve to the same mode; contradictory or unrecognized values raise `PrometheusConfigError` with the variable name and sanitized value.
- The Prometheus default is `127.0.0.1:9464`. Valid configured ports are inclusive `1..65535`. This cut rejects non-loopback hosts; external exposure needs a separate explicit security decision.
- An `optional` exporter start failure records a degraded component and leaves the core service running. A `required` exporter start failure audits, rolls back acquired components, and is re-raised.
- The status projection is `${ATLAS_HOME:-~/atlas}/runtime/service_status.json`, schema version `1`, mode `0600`, written by same-directory temporary file, file `fsync`, atomic `os.replace`, and directory `fsync`.
- Service states are exactly `starting | ready | degraded | failed | stopped`. Component states are exactly `disabled | starting | ready | degraded | failed | stopped`.
- Every state transition is Merkle-audited before the derived JSON projection is replaced. If the audit write fails, the new projection is not published. Filesystem failures before `os.replace` preserve the prior projection; a failure after a successful replace is reported as an indeterminate durability outcome and reconciles in-memory state with the bytes now visible instead of falsely claiming rollback.
- Every boot has a fresh UUID `instance_id`. Every enabled endpoint recorded in the projection carries that exact identity. `atlas_up 1` alone is not readiness evidence.
- `stop()` is idempotent and attempts every registered cleanup even when one cleanup fails. A failed cleanup retains both its callback and owner reference for a later retry, prevents a `stopped` projection, and raises a sanitized aggregate after all other cleanups were attempted. R is complete only when the final retry leaves no Atlas-owned thread, listener, subscription, scheduler, or monitor alive.
- Do not modify `config/governance.json`, `.env`, Prometheus scraper configuration, `.gitignore`, or `docs/fixtures/`.
- The R1 migration path is read-only: it renders a unified diff containing only validated `ATLAS_PROMETHEUS*` keys. It never prints unrelated environment values and never writes the dotenv file or scraper.
- Add no dependencies. Use only the standard library and already-declared FastAPI/Uvicorn/Click/pytest stack.
- Preserve the current operator changes (`M .gitignore`, `?? docs/fixtures/`) outside every `git add` command.
- Do not hand-maintain test counts. Record commands and outcomes without copying suite totals into canonical docs.
- Before each task, confirm `git status --short --branch`; stage only the paths named by that task.
- Execute from the dedicated implementation worktree. Its ignored `.venv` symlink points to `/home/ronin/proyectos/atlas-core/.venv`, so commands use the shared verified environment while `PYTHONPATH=src` resolves worktree code.

---

## Structural evidence and scope boundary

MCP Trunk was queried at HEAD `780b37a896f1673bd97ba214281c9b8a43f58186`. `graph_overview` reported `graph_commit_sha`, `head_sha`, and `server_started_head_sha` equal to that SHA, `freshness=FRESH`, and `source_tree_dirty=false`.

- `atlas.runtime.service_runner` has one direct importer: `atlas.interfaces.cli`. Its direct imports are `atlas.core.contracts`, `atlas.core.orchestrator`, `atlas.interfaces.dashboard`, `atlas.monitoring.prometheus_exporter`, and `atlas.thermal.watchdog`.
- `atlas.monitoring.prometheus_exporter` has one direct importer: `atlas.runtime.service_runner`, and imports only `atlas.logging.telemetry_bus`.
- `atlas.interfaces.dashboard` has blast radius limited to `atlas.interfaces.cli` and `atlas.runtime.service_runner`.
- `atlas.core.event_bus` has broader blast radius but needs one additive method, `unsubscribe`; no existing method changes signature.
- `atlas.core.orchestrator` and `atlas.core.contracts` are broad hubs. Contracts remain untouched; the orchestrator change is restricted to retaining/releasing exact Telegram handlers and preserving monitor owners until verified stop. All other lifecycle adaptation stays in the runner.
- `atlas.core.reality_live` has blast radius limited to `atlas.core.reality`, `atlas.api.server`, and `atlas.interfaces.cli`. R3 extends its daemon probe without changing existing `active` semantics.

## File map

### Create

- `src/atlas/runtime/prometheus_config.py` — authoritative parsing and validation for exporter mode, host, and port.
- `src/atlas/runtime/service_status.py` — typed boot/component/endpoint model and audit-first atomic projection store.
- `src/atlas/runtime/lifecycle.py` — reverse-order cleanup registry with failure aggregation.
- `src/atlas/runtime/readiness.py` — status loading plus PID and endpoint identity verification.
- `scripts/runtime_systemd_smoke.py` — explicit opt-in, safe-profile systemd smoke that restores the stopped state.
- `tests/test_prometheus_config.py`
- `tests/test_prometheus_exporter.py`
- `tests/test_service_status.py`
- `tests/test_service_runner_prometheus.py`
- `tests/test_cli_prometheus_migration.py`
- `tests/test_event_bus_lifecycle.py`
- `tests/test_runtime_lifecycle.py`
- `tests/test_runtime_component_shutdown.py`
- `tests/test_dashboard_runtime_server.py`
- `tests/test_service_runner_transactional.py`
- `tests/test_runtime_readiness.py`
- `tests/test_cli_service_readiness.py`
- `tests/test_install_atlas_systemd.py`
- `tests/test_runtime_systemd_smoke.py`

### Modify

- `src/atlas/monitoring/prometheus_exporter.py` — instance identity, ephemeral-port visibility, and idempotent close.
- `src/atlas/runtime/service_runner.py` — R1 policy/status wiring and R2 transactional ownership.
- `src/atlas/core/event_bus.py` — additive `unsubscribe(event_type, handler) -> bool`.
- `src/atlas/core/orchestrator.py` — retain and unwind exact Telegram subscription handlers; do not clear owners while their threads remain alive.
- `src/atlas/core/offline_monitor.py` — replace uninterruptible polling sleep with cooperative stop and verified ownership release.
- `src/atlas/thermal/watchdog.py` — replace uninterruptible polling sleep with cooperative stop and verified ownership release.
- `src/atlas/interfaces/dashboard.py` — controllable `DashboardServer` and health identity.
- `src/atlas/interfaces/cli.py` — `service-readiness` read-only command.
- `src/atlas/core/reality_live.py` — report `MainPID`, restart count, and identity-bound readiness.
- `src/atlas/core/reality.py` — pass the resolved workspace status path to the live daemon probe.
- `tests/test_reality_live.py` — preserve `active` behavior and cover new readiness fields.
- `tests/test_telegram_orchestrator.py` — prove exact Telegram handlers are removed on stop and partial wiring unwinds.
- `scripts/atlas-core.service` — finite restart burst.
- `scripts/install_atlas_systemd.sh` — backup/restore plus stable readiness loop.
- `scripts/gate_i_smoke.py` — isolate every optional subsystem from the caller environment.
- `tests/test_daemon_idle_guard.py` — assert unit hardening without replacing behavioral installer tests.
- `docs/operations/prometheus_setup.md` — current mode, port, endpoint, and migration instructions.
- `docs/superpowers/specs/2026-08-02-atlas-integrity-recovery-program-design.md` — append factual R1/R2/R3 verification notes after each cut closes.
- `WORK_LEDGER.md` — live cut status and next action only.
- `MEMORY.md` — one-line durable lesson after the complete R cut.

---

### Task 1: Parse the Prometheus configuration contract

**Files:**
- Create: `src/atlas/runtime/prometheus_config.py`
- Create: `tests/test_prometheus_config.py`

**Interfaces:**
- Consumes: a `collections.abc.Mapping[str, str]`, normally `os.environ`.
- Produces: `PrometheusMode`, `PrometheusConfig`, `PrometheusConfigError`, `load_prometheus_config(env: Mapping[str, str]) -> PrometheusConfig`, and `prometheus_migration_diff(env: Mapping[str, str]) -> str`.

- [ ] **Step 1: Write failing mode-migration tests**

```python
from __future__ import annotations

import pytest

from atlas.runtime.prometheus_config import (
    PrometheusConfigError,
    PrometheusMode,
    load_prometheus_config,
    prometheus_migration_diff,
)


@pytest.mark.parametrize("legacy", ["1", "true", "TRUE", "yes"])
def test_legacy_true_maps_to_optional(legacy: str) -> None:
    config = load_prometheus_config({"ATLAS_PROMETHEUS": legacy})
    assert config.mode is PrometheusMode.OPTIONAL


@pytest.mark.parametrize("legacy", ["0", "false", "FALSE", "no", ""])
def test_legacy_false_maps_to_off(legacy: str) -> None:
    config = load_prometheus_config({"ATLAS_PROMETHEUS": legacy})
    assert config.mode is PrometheusMode.OFF


def test_explicit_required_mode_is_preserved() -> None:
    config = load_prometheus_config({"ATLAS_PROMETHEUS_MODE": "required"})
    assert config.mode is PrometheusMode.REQUIRED


def test_contradictory_legacy_and_explicit_modes_fail() -> None:
    env = {
        "ATLAS_PROMETHEUS": "true",
        "ATLAS_PROMETHEUS_MODE": "required",
    }
    with pytest.raises(PrometheusConfigError, match="contradictory"):
        load_prometheus_config(env)


def test_invalid_explicit_mode_reports_sanitized_context() -> None:
    with pytest.raises(
        PrometheusConfigError,
        match=r"ATLAS_PROMETHEUS_MODE.*'sometimes\\nrequired'",
    ):
        load_prometheus_config(
            {"ATLAS_PROMETHEUS_MODE": "sometimes\nrequired"}
        )
```

- [ ] **Step 2: Run the mode tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_prometheus_config.py -q`

Expected: FAIL during collection because `atlas.runtime.prometheus_config` does not exist.

- [ ] **Step 3: Add failing validation tests**

```python
@pytest.mark.parametrize("port", ["0", "65536", "nine"])
def test_invalid_port_has_context(port: str) -> None:
    with pytest.raises(PrometheusConfigError, match="ATLAS_PROMETHEUS_PORT"):
        load_prometheus_config(
            {
                "ATLAS_PROMETHEUS_MODE": "optional",
                "ATLAS_PROMETHEUS_PORT": port,
            }
        )


def test_defaults_are_loopback_and_dedicated_port() -> None:
    config = load_prometheus_config({"ATLAS_PROMETHEUS_MODE": "optional"})
    assert config.host == "127.0.0.1"
    assert config.port == 9464


def test_non_loopback_host_is_rejected() -> None:
    with pytest.raises(PrometheusConfigError, match="loopback"):
        load_prometheus_config(
            {
                "ATLAS_PROMETHEUS_MODE": "optional",
                "ATLAS_PROMETHEUS_HOST": "0.0.0.0",
            }
        )
```

- [ ] **Step 4: Implement the minimal parser**

```python
from __future__ import annotations

import difflib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class PrometheusMode(StrEnum):
    OFF = "off"
    OPTIONAL = "optional"
    REQUIRED = "required"


@dataclass(frozen=True)
class PrometheusConfig:
    mode: PrometheusMode
    host: str
    port: int


class PrometheusConfigError(ValueError):
    """A sanitized, operator-actionable exporter configuration error."""


_TRUE = frozenset({"1", "true", "yes"})
_FALSE = frozenset({"", "0", "false", "no"})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})


def _sanitized_value(raw: str) -> str:
    value = raw.strip()
    if len(value) > 64:
        value = value[:63] + "…"
    return repr(value)


def _legacy_mode(raw: str) -> PrometheusMode:
    normalized = raw.strip().lower()
    if normalized in _TRUE:
        return PrometheusMode.OPTIONAL
    if normalized in _FALSE:
        return PrometheusMode.OFF
    raise PrometheusConfigError(
        "ATLAS_PROMETHEUS has unsupported value "
        f"{_sanitized_value(raw)}; use true or false"
    )


def load_prometheus_config(env: Mapping[str, str]) -> PrometheusConfig:
    legacy_present = "ATLAS_PROMETHEUS" in env
    legacy_mode = _legacy_mode(env.get("ATLAS_PROMETHEUS", ""))
    explicit_raw = env.get("ATLAS_PROMETHEUS_MODE", "").strip().lower()
    try:
        explicit_mode = PrometheusMode(explicit_raw) if explicit_raw else None
    except ValueError as exc:
        raise PrometheusConfigError(
            "ATLAS_PROMETHEUS_MODE has unsupported value "
            f"{_sanitized_value(explicit_raw)}; use off, optional, or required"
        ) from exc
    if explicit_mode is not None and legacy_present and explicit_mode is not legacy_mode:
        raise PrometheusConfigError(
            "ATLAS_PROMETHEUS_MODE and ATLAS_PROMETHEUS are contradictory"
        )
    mode = explicit_mode or legacy_mode
    host = env.get("ATLAS_PROMETHEUS_HOST", "127.0.0.1").strip()
    if host not in _LOOPBACK_HOSTS:
        raise PrometheusConfigError(
            "ATLAS_PROMETHEUS_HOST must remain loopback in recovery cut R1; got "
            f"{_sanitized_value(host)}"
        )
    raw_port = env.get("ATLAS_PROMETHEUS_PORT", "9464").strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise PrometheusConfigError(
            "ATLAS_PROMETHEUS_PORT must be an integer, got "
            f"{_sanitized_value(raw_port)}"
        ) from exc
    if not 1 <= port <= 65535:
        raise PrometheusConfigError(
            f"ATLAS_PROMETHEUS_PORT must be in 1..65535, got {port}"
        )
    return PrometheusConfig(mode=mode, host=host, port=port)
```

- [ ] **Step 5: Add the secret-scoped migration-diff test**

```python
def test_migration_diff_contains_only_validated_prometheus_keys() -> None:
    diff = prometheus_migration_diff(
        {
            "ATLAS_PROMETHEUS": "true",
            "ATLAS_PROMETHEUS_PORT": "9091",
            "UNRELATED_API_KEY": "must-never-appear",
        }
    )
    assert "-ATLAS_PROMETHEUS=true" in diff
    assert "+ATLAS_PROMETHEUS_MODE=optional" in diff
    assert "+ATLAS_PROMETHEUS_HOST=127.0.0.1" in diff
    assert "+ATLAS_PROMETHEUS_PORT=9091" in diff
    assert "UNRELATED_API_KEY" not in diff
    assert "must-never-appear" not in diff
```

- [ ] **Step 6: Implement the read-only diff projection**

```python
_PROMETHEUS_KEYS = (
    "ATLAS_PROMETHEUS",
    "ATLAS_PROMETHEUS_MODE",
    "ATLAS_PROMETHEUS_HOST",
    "ATLAS_PROMETHEUS_PORT",
)


def prometheus_migration_diff(env: Mapping[str, str]) -> str:
    present = [key for key in _PROMETHEUS_KEYS if key in env]
    if not present:
        return ""
    config = load_prometheus_config(env)
    before = [f"{key}={env[key]}\n" for key in present]
    proposed = {"ATLAS_PROMETHEUS_MODE": config.mode.value}
    if config.mode is not PrometheusMode.OFF:
        proposed["ATLAS_PROMETHEUS_HOST"] = config.host
        proposed["ATLAS_PROMETHEUS_PORT"] = str(config.port)
    after = [
        f"{key}={proposed[key]}\n"
        for key in _PROMETHEUS_KEYS
        if key in proposed
    ]
    return "".join(
        difflib.unified_diff(
            before,
            after,
            fromfile="current-prometheus.env",
            tofile="proposed-prometheus.env",
        )
    )
```

This function validates first, so the diff can contain only the finite mode
vocabulary, an allowed loopback host, and an integer port. It deliberately
omits every unrelated key and returns the diff as data; it has no path or write
API.

- [ ] **Step 7: Run tests and mypy to verify GREEN**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_prometheus_config.py -q`

Expected: PASS.

Run: `MYPYPATH=src .venv/bin/python -m mypy src/atlas/runtime/prometheus_config.py`

Expected: `Success: no issues found`.

- [ ] **Step 8: Commit Task 1**

```bash
git status --short --branch
git add src/atlas/runtime/prometheus_config.py tests/test_prometheus_config.py
git commit -m "fix(runtime): define prometheus recovery configuration"
```

---

### Task 2: Publish audit-first atomic service status

**Files:**
- Create: `src/atlas/runtime/service_status.py`
- Create: `tests/test_service_status.py`

**Interfaces:**
- Consumes: `AuditTransition = Callable[[str, dict[str, object]], None]`, Atlas version, workspace path, PID, UUID factory, and UTC clock.
- Produces: `ServicePhase`, `ComponentPhase`, `RuntimeEndpoint`, `StatusDurabilityError(candidate_visible: bool)`, `ServiceStatusStore`, `ServiceStatusStore.snapshot() -> dict[str, object]`, `transition_service(...)`, `transition_component(...)`, and `read_service_status(path: Path) -> dict[str, object]`.

- [ ] **Step 1: Write the failing schema and audit-order test**

```python
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from atlas.runtime.service_status import (
    ComponentPhase,
    RuntimeEndpoint,
    ServicePhase,
    ServiceStatusStore,
    read_service_status,
)


def _ready_store(path: Path) -> ServiceStatusStore:
    store = ServiceStatusStore(
        path=path,
        atlas_version="0.12.0",
        audit=lambda _action, _payload: None,
        instance_id="boot-123",
        pid=4321,
        started_at="2026-08-02T18:00:00+00:00",
        clock=lambda: "2026-08-02T18:00:01+00:00",
    )
    store.transition_service(ServicePhase.STARTING, reason="boot")
    store.transition_service(ServicePhase.READY, reason="ready")
    return store


def test_transition_audits_before_publishing(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "service_status.json"
    observations: list[bool] = []

    def audit(_action: str, _payload: dict[str, object]) -> None:
        observations.append(path.exists())

    store = ServiceStatusStore(
        path=path,
        atlas_version="0.12.0",
        audit=audit,
        instance_id="boot-123",
        pid=4321,
        started_at="2026-08-02T18:00:00+00:00",
        clock=lambda: "2026-08-02T18:00:01+00:00",
    )
    store.transition_service(ServicePhase.STARTING, reason="boot")

    assert observations == [False]
    payload = read_service_status(path)
    assert payload["schema_version"] == 1
    assert payload["atlas_version"] == "0.12.0"
    assert payload["instance_id"] == "boot-123"
    assert payload["pid"] == 4321
    assert payload["started_at"] == "2026-08-02T18:00:00+00:00"
    assert payload["updated_at"] == "2026-08-02T18:00:01+00:00"
    assert payload["status"] == "starting"
    assert payload["reason"] == "boot"
    assert payload["components"] == {}
    assert payload["endpoints"] == []
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_failed_audit_does_not_publish(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "service_status.json"

    def reject(_action: str, _payload: dict[str, object]) -> None:
        raise OSError("audit unavailable")

    store = ServiceStatusStore(
        path=path,
        atlas_version="0.12.0",
        audit=reject,
        instance_id="boot-123",
        pid=4321,
        started_at="2026-08-02T18:00:00+00:00",
        clock=lambda: "2026-08-02T18:00:01+00:00",
    )
    with pytest.raises(OSError, match="audit unavailable"):
        store.transition_service(ServicePhase.STARTING, reason="boot")
    assert not path.exists()


def test_failed_later_audit_preserves_file_and_memory_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "service_status.json"
    reject = False

    def audit(_action: str, _payload: dict[str, object]) -> None:
        if reject:
            raise OSError("audit unavailable")

    store = ServiceStatusStore(
        path=path,
        atlas_version="0.12.0",
        audit=audit,
        instance_id="boot-123",
        pid=4321,
        started_at="2026-08-02T18:00:00+00:00",
        clock=lambda: "2026-08-02T18:00:01+00:00",
    )
    store.transition_service(ServicePhase.STARTING, reason="boot")
    before_bytes = path.read_bytes()
    before_snapshot = store.snapshot()
    reject = True

    with pytest.raises(OSError, match="audit unavailable"):
        store.transition_service(ServicePhase.READY, reason="ready")

    assert path.read_bytes() == before_bytes
    assert store.snapshot() == before_snapshot


def test_pre_replace_failure_preserves_file_and_memory_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "runtime" / "service_status.json"
    store = _ready_store(path)
    before_bytes = path.read_bytes()
    before_snapshot = store.snapshot()
    monkeypatch.setattr(os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("replace")))

    with pytest.raises(OSError, match="replace"):
        store.transition_service(ServicePhase.DEGRADED, reason="test")

    assert path.read_bytes() == before_bytes
    assert store.snapshot() == before_snapshot


def test_post_replace_directory_fsync_failure_is_fail_honest_and_coherent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from atlas.runtime.service_status import StatusDurabilityError

    path = tmp_path / "runtime" / "service_status.json"
    store = _ready_store(path)
    real_fsync = os.fsync

    def fail_directory_fsync(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("directory fsync")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_directory_fsync)
    with pytest.raises(StatusDurabilityError) as caught:
        store.transition_service(ServicePhase.DEGRADED, reason="test")

    assert caught.value.candidate_visible is True
    assert read_service_status(path)["status"] == "degraded"
    assert store.snapshot()["status"] == "degraded"
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_service_status.py -q`

Expected: FAIL because `atlas.runtime.service_status` does not exist.

- [ ] **Step 3: Add failing component and endpoint tests**

```python
def test_component_and_endpoint_share_boot_identity(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "service_status.json"
    audited: list[tuple[str, dict[str, object]]] = []
    store = ServiceStatusStore(
        path=path,
        atlas_version="0.12.0",
        audit=lambda action, payload: audited.append((action, payload)),
        instance_id="boot-123",
        pid=4321,
        started_at="2026-08-02T18:00:00+00:00",
        clock=lambda: "2026-08-02T18:00:01+00:00",
    )
    store.transition_component(
        name="prometheus",
        phase=ComponentPhase.READY,
        required=False,
        reason="listening",
        endpoint=RuntimeEndpoint(
            name="prometheus",
            url="http://127.0.0.1:9464/metrics",
            required=False,
            identity_kind="prometheus",
        ),
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["components"]["prometheus"]["status"] == "ready"
    assert payload["endpoints"][0]["instance_id"] == "boot-123"
    assert audited[0][0] == "service.component_transition"


def test_non_ready_component_transition_removes_its_stale_endpoint(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime" / "service_status.json"
    store = ServiceStatusStore(
        path=path,
        atlas_version="0.12.0",
        audit=lambda _action, _payload: None,
        instance_id="boot-123",
        pid=4321,
        started_at="2026-08-02T18:00:00+00:00",
        clock=lambda: "2026-08-02T18:00:01+00:00",
    )
    endpoint = RuntimeEndpoint(
        name="prometheus",
        url="http://127.0.0.1:9464/metrics",
        required=False,
        identity_kind="prometheus",
    )
    store.transition_component(
        "prometheus", ComponentPhase.READY, required=False, endpoint=endpoint
    )
    store.transition_component(
        "prometheus", ComponentPhase.DEGRADED, required=False, reason="OSError"
    )

    assert store.snapshot()["endpoints"] == []
```

- [ ] **Step 4: Implement the typed store and atomic writer**

The implementation must use these public shapes:

```python
class ServicePhase(StrEnum):
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPED = "stopped"


class ComponentPhase(StrEnum):
    DISABLED = "disabled"
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass(frozen=True)
class RuntimeEndpoint:
    name: str
    url: str
    required: bool
    identity_kind: str
```

Every `snapshot()` must have this exact top-level shape; component and endpoint
entries must not add exception text or environment values:

```python
{
    "schema_version": 1,
    "atlas_version": self._atlas_version,
    "instance_id": self._instance_id,
    "pid": self._pid,
    "started_at": self._started_at,
    "updated_at": self._updated_at,
    "status": self._service_phase.value,
    "reason": self._service_reason,
    "components": {
        name: {
            "status": component.phase.value,
            "required": component.required,
            "reason": component.reason,
            "updated_at": component.updated_at,
        }
        for name, component in sorted(self._components.items())
    },
    "endpoints": [
        {
            "name": endpoint.name,
            "url": endpoint.url,
            "required": endpoint.required,
            "identity_kind": endpoint.identity_kind,
            "instance_id": self._instance_id,
        }
        for endpoint in sorted(self._endpoints.values(), key=lambda item: item.name)
    ],
}
```

Use this write algorithm inside `ServiceStatusStore._publish(candidate)`. The
exception distinguishes failure before publication from failure to prove rename
durability after publication:

```python
class StatusDurabilityError(OSError):
    def __init__(self, message: str, *, candidate_visible: bool) -> None:
        super().__init__(message)
        self.candidate_visible = candidate_visible


def _publish(self, candidate: dict[str, object]) -> None:
    self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    encoded = json.dumps(candidate, sort_keys=True, indent=2).encode("utf-8")
    fd, raw_path = tempfile.mkstemp(
        prefix=".service_status.",
        suffix=".tmp",
        dir=self._path.parent,
    )
    temp_path = Path(raw_path)
    replaced = False
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, self._path)
        replaced = True
        directory_fd = os.open(self._path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        if replaced:
            raise StatusDurabilityError(
                "service status replaced but directory durability is unconfirmed",
                candidate_visible=True,
            ) from exc
        raise
    finally:
        temp_path.unlink(missing_ok=True)
```

`transition_service` and `transition_component` build a candidate without
mutating the committed in-memory snapshot, call the audit callback with that
candidate, call `_publish(candidate)`, and normally only then replace the
committed in-memory state. An audit failure or any filesystem failure before
`os.replace` leaves both the previous projection and `snapshot()` unchanged.
If `_publish` raises `StatusDurabilityError(candidate_visible=True)`, the
transition first adopts the candidate as its committed in-memory snapshot and
then re-raises: the caller must treat readiness as failed/unknown, but file and
memory never contradict one another and the implementation does not claim an
impossible rollback after rename. The preceding Merkle record is the intent
evidence for either outcome. Sanitize reasons to
`type(exc).__name__` plus `errno` at call sites; do not serialize arbitrary
exception text from external components.

When a component transitions to any phase other than `READY`, remove its
endpoint from the candidate before audit/publish. A stale endpoint must never
survive a failed, degraded, disabled, or stopped owner.

- [ ] **Step 5: Run tests and mypy to verify GREEN**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_service_status.py -q`

Expected: PASS.

Run: `MYPYPATH=src .venv/bin/python -m mypy src/atlas/runtime/service_status.py`

Expected: `Success: no issues found`.

- [ ] **Step 6: Commit Task 2**

```bash
git status --short --branch
git add src/atlas/runtime/service_status.py tests/test_service_status.py
git commit -m "feat(runtime): publish atomic boot status"
```

---

### Task 3: Bind exporter identity and close its socket cleanly

**Files:**
- Modify: `src/atlas/monitoring/prometheus_exporter.py:15-80`
- Create: `tests/test_prometheus_exporter.py`

**Interfaces:**
- Consumes: `TelemetryBus`, `host`, `port`, and the R1 `instance_id`.
- Produces: `PrometheusExporter.start() -> tuple[str, int]`, `bound_address: tuple[str, int] | None`, idempotent `stop()`, and `atlas_runtime_info{instance_id="..."} 1`.

- [ ] **Step 1: Write the real collision reproduction test**

```python
from __future__ import annotations

import errno
import socket
from urllib.request import urlopen

import pytest

from atlas.logging.telemetry_bus import TelemetryBus
from atlas.monitoring.prometheus_exporter import PrometheusExporter


def test_start_propagates_real_address_in_use() -> None:
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.bind(("127.0.0.1", 0))
    occupied.listen()
    port = int(occupied.getsockname()[1])
    exporter = PrometheusExporter(
        TelemetryBus(), host="127.0.0.1", port=port, instance_id="boot-123"
    )
    try:
        with pytest.raises(OSError) as caught:
            exporter.start()
        assert caught.value.errno == errno.EADDRINUSE
        assert exporter.bound_address is None
    finally:
        occupied.close()
```

- [ ] **Step 2: Run the collision test and verify RED**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_prometheus_exporter.py::test_start_propagates_real_address_in_use -q`

Expected: FAIL because the constructor has no `instance_id` parameter and no `bound_address` property.

- [ ] **Step 3: Write the identity and idempotent-stop test**

```python
def test_metrics_bind_the_current_boot_identity_and_stop_twice() -> None:
    exporter = PrometheusExporter(
        TelemetryBus(), host="127.0.0.1", port=0, instance_id="boot-123"
    )
    host, port = exporter.start()
    try:
        with urlopen(f"http://{host}:{port}/metrics", timeout=2) as response:
            body = response.read().decode("utf-8")
        assert "atlas_up 1" in body
        assert 'atlas_runtime_info{instance_id="boot-123"} 1' in body
    finally:
        exporter.stop()
        exporter.stop()
    assert exporter.bound_address is None
```

- [ ] **Step 4: Implement the minimal exporter changes**

Change the constructor default to `9464`, store `instance_id`, and add:

```python
@property
def bound_address(self) -> tuple[str, int] | None:
    if self._httpd is None:
        return None
    host, port = self._httpd.server_address[:2]
    return str(host), int(port)
```

Append identity after `atlas_up`:

```python
lines.append("# TYPE atlas_runtime_info gauge")
lines.append(f'atlas_runtime_info{{instance_id="{self._instance_id}"}} 1')
```

Return the actual bound address from `start`. Make `stop` close and clear ownership:

```python
def stop(self) -> None:
    httpd = self._httpd
    thread = self._thread
    if httpd is not None and thread is not None and thread.is_alive():
        httpd.shutdown()
    if httpd is not None:
        httpd.server_close()
    if thread is not None:
        thread.join(timeout=3)
        if thread.is_alive():
            raise RuntimeError("prometheus thread did not stop")
    self._httpd = None
    self._thread = None
```

- [ ] **Step 5: Run tests and mypy to verify GREEN**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_prometheus_exporter.py -q`

Expected: PASS without leaving an `atlas-prometheus` thread.

Run: `MYPYPATH=src .venv/bin/python -m mypy src/atlas/monitoring/prometheus_exporter.py`

Expected: `Success: no issues found`.

- [ ] **Step 6: Commit Task 3**

```bash
git status --short --branch
git add src/atlas/monitoring/prometheus_exporter.py tests/test_prometheus_exporter.py
git commit -m "fix(metrics): bind exporter to runtime identity"
```

---

### Task 4: Apply off, optional, and required exporter policy in the runner

**Files:**
- Modify: `src/atlas/runtime/service_runner.py:7-57,278-295`
- Modify: `src/atlas/interfaces/cli.py:891-960`
- Create: `tests/test_service_runner_prometheus.py`
- Create: `tests/test_cli_prometheus_migration.py`
- Modify: `docs/superpowers/specs/2026-08-02-atlas-integrity-recovery-program-design.md:178-213`
- Modify: `WORK_LEDGER.md`

**Interfaces:**
- Consumes: `load_prometheus_config(os.environ)`, `ServiceStatusStore`, and `PrometheusExporter` from Tasks 1-3.
- Produces: `AtlasServiceRunner.instance_id: str`, `status_snapshot() -> dict[str, object]`, `_start_prometheus_if_enabled() -> bool`, and read-only `atlas prometheus-migration-plan`; `True` means listener acquired, `False` means disabled or optional-degraded.

- [ ] **Step 1: Write the optional-collision RED test**

```python
from __future__ import annotations

import errno
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.logging.telemetry_bus import TelemetryBus
from atlas.runtime.service_runner import AtlasServiceRunner


class _Merkle:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def log(self, **record: object) -> None:
        self.records.append(record)


def _orchestrator(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        VERSION="0.12.0",
        _workspace=tmp_path,
        _merkle=_Merkle(),
        _observability=SimpleNamespace(telemetry=TelemetryBus()),
    )


def test_optional_collision_degrades_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.bind(("127.0.0.1", 0))
    occupied.listen()
    port = int(occupied.getsockname()[1])
    monkeypatch.setenv("ATLAS_PROMETHEUS_MODE", "optional")
    monkeypatch.setenv("ATLAS_PROMETHEUS_PORT", str(port))
    runner = AtlasServiceRunner(_orchestrator(tmp_path))
    try:
        assert runner._start_prometheus_if_enabled() is False
    finally:
        occupied.close()
    status = runner.status_snapshot()
    assert status["components"]["prometheus"]["status"] == "degraded"
    assert status["components"]["prometheus"]["reason"] == (
        f"OSError:errno={errno.EADDRINUSE}"
    )


def test_optional_non_socket_start_failure_also_degrades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_start(_exporter: object) -> None:
        raise RuntimeError("provider detail must not enter status")

    monkeypatch.setenv("ATLAS_PROMETHEUS_MODE", "optional")
    monkeypatch.setattr(
        "atlas.monitoring.prometheus_exporter.PrometheusExporter.start",
        fail_start,
    )
    runner = AtlasServiceRunner(_orchestrator(tmp_path))

    assert runner._start_prometheus_if_enabled() is False
    component = runner.status_snapshot()["components"]["prometheus"]
    assert component["status"] == "degraded"
    assert component["reason"] == "RuntimeError"
    assert "provider detail" not in str(component)


def test_audit_failure_cannot_skip_partial_exporter_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class PartialExporter:
        instance: "PartialExporter | None" = None

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.stopped = False
            PartialExporter.instance = self

        def start(self) -> tuple[str, int]:
            raise RuntimeError("partial exporter start")

        def stop(self) -> None:
            self.stopped = True

    orch = _orchestrator(tmp_path)
    orch._merkle.reject_after = 1  # STARTING audits; DEGRADED is rejected.
    monkeypatch.setenv("ATLAS_PROMETHEUS_MODE", "optional")
    monkeypatch.setattr(
        "atlas.monitoring.prometheus_exporter.PrometheusExporter",
        PartialExporter,
    )
    runner = AtlasServiceRunner(orch)

    with pytest.raises(ExceptionGroup) as caught:
        runner._start_prometheus_if_enabled()

    assert PartialExporter.instance is not None
    assert PartialExporter.instance.stopped is True
    assert [type(error).__name__ for error in caught.value.exceptions] == [
        "RuntimeError",
        "OSError",
    ]
```

Extend `_Merkle` with `reject_after: int | None = None`; after that many
successful records its `log` raises `OSError("audit unavailable")`. This gives
the test an audit-successful `STARTING` transition followed by a failed outcome
transition without reaching the live audit log.

- [ ] **Step 2: Run the optional test and verify RED**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_service_runner_prometheus.py::test_optional_collision_degrades_without_raising -q`

Expected: FAIL because the current helper returns `None`, re-raises `OSError`, and publishes no status.

- [ ] **Step 3: Add required and disabled tests**

```python
def test_required_collision_is_re_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.bind(("127.0.0.1", 0))
    occupied.listen()
    monkeypatch.setenv("ATLAS_PROMETHEUS_MODE", "required")
    monkeypatch.setenv("ATLAS_PROMETHEUS_PORT", str(occupied.getsockname()[1]))
    runner = AtlasServiceRunner(_orchestrator(tmp_path))
    try:
        with pytest.raises(OSError):
            runner._start_prometheus_if_enabled()
    finally:
        occupied.close()
    assert runner.status_snapshot()["components"]["prometheus"]["status"] == "failed"


def test_off_mode_records_disabled_without_listener(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_PROMETHEUS_MODE", "off")
    runner = AtlasServiceRunner(_orchestrator(tmp_path))
    assert runner._start_prometheus_if_enabled() is False
    assert runner.status_snapshot()["components"]["prometheus"]["status"] == "disabled"
```

- [ ] **Step 4: Wire config, status, and sanitized failure handling**

Initialize the store in `__init__` using `self._orch._workspace / "runtime" / "service_status.json"`, `str(uuid.uuid4())`, `os.getpid()`, and the wrapped Merkle callback. Expose only a copy through `status_snapshot`.

Use this failure reason helper:

```python
def _sanitized_error(exc: BaseException) -> str:
    errno_value = getattr(exc, "errno", None)
    suffix = f":errno={errno_value}" if isinstance(errno_value, int) else ""
    return f"{type(exc).__name__}{suffix}"
```

Implement `_start_prometheus_if_enabled` so config parsing happens before the
start-error containment boundary: invalid or contradictory configuration is
always fatal. `OFF` transitions to `disabled`. After valid configuration, both
`OPTIONAL` and `REQUIRED` catch any `Exception` from exporter
construction/start and first attempt the idempotent partial `stop()` in a
`finally`-equivalent path; an audit/status failure can never bypass that
cleanup. Only after the cleanup attempt do they publish `degraded` or `failed`.
If cleanup or outcome publication also fails, retain `self._prometheus` as an
owned retry handle and raise one ordered `ExceptionGroup` containing the
original start error first, then cleanup error, then audit/status error. If
cleanup succeeds, clear the field. A required start error is re-raised after a
successful `failed` transition; an optional start error is logged with
`_log.exception` and returns `False` only after both cleanup and degraded
publication succeed. On success, record the actual address returned from
`start` as a `RuntimeEndpoint` with `identity_kind="prometheus"`.

- [ ] **Step 5: Write the read-only migration CLI RED test**

```python
from __future__ import annotations

from click.testing import CliRunner

from atlas.interfaces.cli import cli


def test_prometheus_migration_plan_is_secret_scoped(monkeypatch) -> None:
    for key in (
        "ATLAS_PROMETHEUS",
        "ATLAS_PROMETHEUS_MODE",
        "ATLAS_PROMETHEUS_HOST",
        "ATLAS_PROMETHEUS_PORT",
    ):
        monkeypatch.delenv(key, raising=False)
    result = CliRunner().invoke(
        cli,
        ["prometheus-migration-plan"],
        env={
            "ATLAS_PROMETHEUS": "true",
            "UNRELATED_API_KEY": "must-never-appear",
        },
    )
    assert result.exit_code == 0
    assert "+ATLAS_PROMETHEUS_MODE=optional" in result.output
    assert "+ATLAS_PROMETHEUS_PORT=9464" in result.output
    assert "UNRELATED_API_KEY" not in result.output
    assert "must-never-appear" not in result.output
```

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_cli_prometheus_migration.py -q`

Expected: FAIL because the command is not registered.

- [ ] **Step 6: Implement the read-only CLI projection**

```python
@cli.command("prometheus-migration-plan")
def prometheus_migration_plan() -> None:
    """Print a secret-scoped dotenv migration diff without writing files."""
    from atlas.runtime.prometheus_config import prometheus_migration_diff

    diff = prometheus_migration_diff(os.environ)
    if diff:
        click.echo(diff, nl=False)
    else:
        click.echo("No Prometheus migration changes.")
```

Document the operator preview command without running it during R:

```bash
PYTHONPATH=src .venv/bin/python scripts/safe_dotenv.py .env -- \
  .venv/bin/atlas prometheus-migration-plan
```

The command has no `--apply` option. Any dotenv or scraper edit remains a
separate operator-reviewed action outside R.

- [ ] **Step 7: Run R1 integration tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_prometheus_config.py tests/test_prometheus_exporter.py tests/test_service_status.py tests/test_service_runner_prometheus.py tests/test_cli_prometheus_migration.py -q`

Expected: PASS.

Run: `MYPYPATH=src .venv/bin/python -m mypy src/atlas/runtime/service_runner.py src/atlas/runtime/prometheus_config.py src/atlas/runtime/service_status.py src/atlas/monitoring/prometheus_exporter.py src/atlas/interfaces/cli.py`

Expected: `Success: no issues found`.

- [ ] **Step 8: Record factual R1 closure and commit**

Append an R1 verification note to the recovery design containing the four commands above and the invariant “optional collision degraded; required collision raised.” Update `WORK_LEDGER.md` so the active runtime node says `R1 complete; R2 next; service remains intentionally stopped`. Do not add test totals.

```bash
git status --short --branch
git add src/atlas/runtime/service_runner.py src/atlas/interfaces/cli.py \
  tests/test_service_runner_prometheus.py tests/test_cli_prometheus_migration.py \
  docs/superpowers/specs/2026-08-02-atlas-integrity-recovery-program-design.md \
  WORK_LEDGER.md
git commit -m "fix(runtime): degrade optional exporter failures"
```

---

### Task 5: Add reversible EventBus subscriptions

**Files:**
- Modify: `src/atlas/core/event_bus.py:14-30`
- Create: `tests/test_event_bus_lifecycle.py`

**Interfaces:**
- Consumes: existing `EventType` and `Handler`.
- Produces: additive `EventBus.unsubscribe(event_type: EventType, handler: Handler) -> bool`; returns `True` only when the exact handler was removed.

- [ ] **Step 1: Write the failing unsubscribe behavior test**

```python
from __future__ import annotations

from atlas.core.contracts import Event, EventType
from atlas.core.event_bus import EventBus


def test_unsubscribe_removes_only_the_exact_handler() -> None:
    bus = EventBus()
    first: list[Event] = []
    second: list[Event] = []
    first_handler = first.append
    second_handler = second.append
    bus.subscribe(EventType.SHADOW_ALERT, first_handler)
    bus.subscribe(EventType.SHADOW_ALERT, second_handler)

    assert bus.unsubscribe(EventType.SHADOW_ALERT, first.append) is False
    assert bus.unsubscribe(EventType.SHADOW_ALERT, first_handler) is True
    assert bus.unsubscribe(EventType.SHADOW_ALERT, first_handler) is False
    event = Event(type=EventType.SHADOW_ALERT, payload={})
    bus.publish(event)

    assert first == []
    assert second == [event]
```

- [ ] **Step 2: Run the test and verify RED**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_event_bus_lifecycle.py -q`

Expected: FAIL with `AttributeError: 'EventBus' object has no attribute 'unsubscribe'`.

- [ ] **Step 3: Implement the additive method under the existing lock**

```python
def unsubscribe(self, event_type: EventType, handler: Handler) -> bool:
    with self._lock:
        handlers = self._subscribers.get(event_type)
        if handlers is None:
            return False
        index = next(
            (index for index, subscribed in enumerate(handlers) if subscribed is handler),
            None,
        )
        if index is None:
            return False
        del handlers[index]
        if not handlers:
            self._subscribers.pop(event_type, None)
        return True
```

- [ ] **Step 4: Run focused and existing EventBus consumers**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_event_bus_lifecycle.py tests/test_engineering_events.py tests/test_hermes_webhook.py -q`

Expected: PASS.

Run: `MYPYPATH=src .venv/bin/python -m mypy src/atlas/core/event_bus.py`

Expected: `Success: no issues found`.

- [ ] **Step 5: Commit Task 5**

```bash
git status --short --branch
git add src/atlas/core/event_bus.py tests/test_event_bus_lifecycle.py
git commit -m "feat(events): support reversible subscriptions"
```

---

### Task 6: Track acquired components and aggregate cleanup failures

**Files:**
- Create: `src/atlas/runtime/lifecycle.py`
- Create: `tests/test_runtime_lifecycle.py`

**Interfaces:**
- Consumes: named zero-argument cleanup callables.
- Produces: `CleanupFailure`, `CleanupReport`, `LifecycleStack.register(name, cleanup)`, `LifecycleStack.stop_all() -> CleanupReport`, `LifecycleStack.names -> tuple[str, ...]`, and `LifecycleStack.active -> bool`. Failed entries remain registered in original acquisition order.

- [ ] **Step 1: Write the reverse-order and failure-continuation tests**

```python
from __future__ import annotations

from atlas.runtime.lifecycle import LifecycleStack


def test_stop_all_uses_reverse_acquisition_order() -> None:
    calls: list[str] = []
    stack = LifecycleStack()
    stack.register("first", lambda: calls.append("first"))
    stack.register("second", lambda: calls.append("second"))

    report = stack.stop_all()
    assert report.cleaned == ("second", "first")
    assert report.failures == ()
    assert report.complete is True
    assert calls == ["second", "first"]
    assert stack.names == ()


def test_cleanup_failure_does_not_skip_older_components() -> None:
    calls: list[str] = []
    fail = True
    stack = LifecycleStack()
    stack.register("older", lambda: calls.append("older"))

    def broken() -> None:
        nonlocal fail
        calls.append("broken")
        if fail:
            fail = False
            raise RuntimeError("stop failed")

    stack.register("broken", broken)
    first = stack.stop_all()

    assert calls == ["broken", "older"]
    assert [(failure.component, failure.error_type) for failure in first.failures] == [
        ("broken", "RuntimeError")
    ]
    assert first.cleaned == ("older",)
    assert first.complete is False
    assert stack.names == ("broken",)

    second = stack.stop_all()
    assert second.complete is True
    assert second.cleaned == ("broken",)
    assert stack.names == ()
    assert calls == ["broken", "older", "broken"]


def test_multiple_failed_cleanups_remain_retryable_in_acquisition_order() -> None:
    stack = LifecycleStack()

    def fail_first() -> None:
        raise ValueError("first")

    def fail_second() -> None:
        raise RuntimeError("second")

    stack.register("first", fail_first)
    stack.register("middle", lambda: None)
    stack.register("second", fail_second)
    report = stack.stop_all()

    assert report.attempted == ("second", "middle", "first")
    assert report.cleaned == ("middle",)
    assert [failure.component for failure in report.failures] == ["second", "first"]
    assert stack.names == ("first", "second")
```

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_runtime_lifecycle.py -q`

Expected: FAIL because `atlas.runtime.lifecycle` does not exist.

- [ ] **Step 3: Implement the minimal stack**

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


Cleanup = Callable[[], None]


@dataclass(frozen=True)
class CleanupFailure:
    component: str
    error: Exception = field(repr=False)

    @property
    def error_type(self) -> str:
        return type(self.error).__name__


@dataclass(frozen=True)
class CleanupReport:
    attempted: tuple[str, ...]
    cleaned: tuple[str, ...]
    failures: tuple[CleanupFailure, ...]

    @property
    def complete(self) -> bool:
        return not self.failures


class LifecycleStack:
    def __init__(self) -> None:
        self._entries: list[tuple[str, Cleanup]] = []

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(name for name, _cleanup in self._entries)

    @property
    def active(self) -> bool:
        return bool(self._entries)

    def register(self, name: str, cleanup: Cleanup) -> None:
        if name in self.names:
            raise RuntimeError(f"component already acquired: {name}")
        self._entries.append((name, cleanup))

    def stop_all(self) -> CleanupReport:
        attempted: list[str] = []
        cleaned: list[str] = []
        failures: list[CleanupFailure] = []
        failed_entries: list[tuple[str, Cleanup]] = []
        entries, self._entries = self._entries, []
        for name, cleanup in reversed(entries):
            attempted.append(name)
            try:
                cleanup()
            except Exception as exc:
                failures.append(CleanupFailure(name, exc))
                failed_entries.append((name, cleanup))
            else:
                cleaned.append(name)
        self._entries = list(reversed(failed_entries))
        return CleanupReport(
            attempted=tuple(attempted),
            cleaned=tuple(cleaned),
            failures=tuple(failures),
        )
```

- [ ] **Step 4: Run tests and mypy to verify GREEN**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_runtime_lifecycle.py -q`

Expected: PASS.

Run: `MYPYPATH=src .venv/bin/python -m mypy src/atlas/runtime/lifecycle.py`

Expected: `Success: no issues found`.

- [ ] **Step 5: Commit Task 6**

```bash
git status --short --branch
git add src/atlas/runtime/lifecycle.py tests/test_runtime_lifecycle.py
git commit -m "feat(runtime): track acquired component cleanup"
```

---

### Task 7: Make the dashboard listener synchronously acquirable

**Files:**
- Modify: `src/atlas/interfaces/dashboard.py:74-145,484-487,523-527`
- Modify: `tests/test_dashboard.py`
- Create: `tests/test_dashboard_runtime_server.py`

**Interfaces:**
- Consumes: existing FastAPI `app`, Uvicorn, `host`, `port`, and boot `instance_id`.
- Produces: `set_runtime_identity(instance_id: str | None) -> None`, reversible `set_orchestrator(orch: Orchestrator | None) -> None`, and `DashboardServer.start() -> tuple[str, int]`, `wait() -> None`, `stop() -> None`, `bound_address`.

- [ ] **Step 1: Write a synchronous collision test**

```python
from __future__ import annotations

import socket
import threading

import pytest

from atlas.interfaces.dashboard import DashboardServer, app


def test_dashboard_collision_fails_before_thread_ownership() -> None:
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.bind(("127.0.0.1", 0))
    occupied.listen()
    port = int(occupied.getsockname()[1])
    server = DashboardServer(app, host="127.0.0.1", port=port)
    try:
        with pytest.raises(OSError):
            server.start()
    finally:
        occupied.close()
    assert server.bound_address is None
    assert not any(t.name == "atlas-dashboard" for t in threading.enumerate())
```

- [ ] **Step 2: Run collision test and verify RED**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_dashboard_runtime_server.py::test_dashboard_collision_fails_before_thread_ownership -q`

Expected: FAIL because `DashboardServer` does not exist.

- [ ] **Step 3: Write health identity and idempotent-stop tests**

```python
def test_dashboard_health_includes_runtime_identity(client) -> None:
    from atlas.interfaces.dashboard import set_runtime_identity

    set_runtime_identity("boot-123")
    try:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["instance_id"] == "boot-123"
    finally:
        set_runtime_identity(None)


def test_dashboard_server_stops_twice() -> None:
    server = DashboardServer(app, host="127.0.0.1", port=0)
    host, port = server.start()
    assert host == "127.0.0.1"
    assert port > 0
    server.stop()
    server.stop()
    assert server.bound_address is None


def test_runtime_orchestrator_swap_unsubscribes_exact_progress_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from atlas.core.contracts import EventType
    from atlas.core.event_bus import EventBus
    from atlas.interfaces import dashboard

    bus = EventBus()
    orch = SimpleNamespace(_bus=bus)
    monkeypatch.setattr(dashboard, "_wire_exec_api", lambda _orch: None)
    monkeypatch.setattr(dashboard, "_wire_hermes_webhook", lambda _orch: None)
    dashboard._progress_feed.clear()
    dashboard.set_orchestrator(orch)
    dashboard.set_orchestrator(None)

    bus.publish_type(EventType.AGENTIC_PROGRESS, {"summary": "stale"})
    assert list(dashboard._progress_feed) == []
```

- [ ] **Step 4: Implement a pre-bound Uvicorn server**

`DashboardServer.start` must call `_validate_bind_security`, create an IPv4
standard-library socket on the caller thread, set `SO_REUSEADDR`, bind it, and
call `listen(socket.SOMAXCONN)` before passing it to
`uvicorn.Server.run(sockets=[bound_socket])` on the `atlas-dashboard` thread.
This makes `EADDRINUSE` synchronous and gives Uvicorn a genuinely listening
socket. Wait up to three seconds for `server.started`; on timeout, call `stop`
and raise `RuntimeError("dashboard failed to become ready")`. `wait()` raises
`RuntimeError("dashboard is not started")` when there is no owned thread and
otherwise joins that thread without a timeout. `stop` sets
`server.should_exit = True`, joins for three seconds, raises
`RuntimeError("dashboard thread did not stop")` if it remains alive, then closes
the socket, calls `set_runtime_identity(None)`, and clears all references.
Retain references on a thread-stop failure so a later cleanup attempt does not
lose ownership.

Make dashboard injection reversible. Replace the boolean-only
`_progress_wired` ownership with the exact
`(EventBus, EventType.AGENTIC_PROGRESS, handler)` tuple returned by
`_wire_agentic_progress`. Before swapping orchestrators or setting `None`, call
`unsubscribe` with that exact handler and clear the tuple only after it returns
`True`; a failed unsubscribe raises and preserves the tuple for retry.
Application route registration remains process-lifetime, but it must resolve
the current orchestrator lazily rather than retain an old EventBus. Calling
`set_orchestrator(None)` clears `_orch` without invoking `_get_orch` or creating
a replacement. The runner's dashboard cleanup performs this release only after
`DashboardServer.stop()` has proved the listener thread dead.

Change `api_health` without mutating the orchestrator report:

```python
@app.get("/api/health")
async def api_health() -> dict[str, Any]:
    health = dict(_get_orch().health_report())
    health["instance_id"] = _runtime_instance_id
    return health
```

Keep standalone `serve` compatible without reaching into private fields:

```python
def serve(host: str = "127.0.0.1", port: int = PORT) -> None:
    server = DashboardServer(app, host=host, port=port)
    server.start()
    try:
        server.wait()
    finally:
        server.stop()
```

- [ ] **Step 5: Run dashboard tests and mypy**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_dashboard_runtime_server.py tests/test_dashboard.py -q`

Expected: PASS.

Run: `MYPYPATH=src .venv/bin/python -m mypy src/atlas/interfaces/dashboard.py`

Expected: `Success: no issues found`.

- [ ] **Step 6: Commit Task 7**

```bash
git status --short --branch
git add src/atlas/interfaces/dashboard.py tests/test_dashboard.py \
  tests/test_dashboard_runtime_server.py
git commit -m "fix(dashboard): acquire listener before thread start"
```

---

### Task 7A: Make component-owned handlers and polling threads reversible

**Files:**
- Modify: `src/atlas/core/orchestrator.py:1692-1767,1822-1830`
- Modify: `src/atlas/core/offline_monitor.py`
- Modify: `src/atlas/thermal/watchdog.py`
- Modify: `tests/test_telegram_orchestrator.py`
- Create: `tests/test_runtime_component_shutdown.py`

**Interfaces:**
- Produces: `_wire_bus_to_bot(bot) -> tuple[tuple[EventType, Handler], ...]`, `_unwire_bus_handlers(handlers) -> None`, and cooperative, ownership-preserving `OfflineMonitor.stop()` / `ThermalWatchdog.stop()`.

- [ ] **Step 1: Write RED tests for exact handlers and prompt cooperative stop**

```python
from __future__ import annotations

import time

from atlas.core.event_bus import EventBus
from atlas.core.offline_monitor import OfflineMonitor
from atlas.thermal.watchdog import ThermalWatchdog


class _Hermes:
    SHADOW_TIMEOUT_MINUTES = 15

    def check_offline_fallback(self) -> bool:
        return False


def test_offline_monitor_stop_interrupts_long_poll_sleep() -> None:
    monitor = OfflineMonitor(_Hermes(), EventBus(), poll_interval_seconds=60)
    monitor.start()
    owned_thread = monitor._thread
    started = time.monotonic()
    monitor.stop()

    assert time.monotonic() - started < 2
    assert owned_thread is not None and not owned_thread.is_alive()
    assert monitor._thread is None


def test_thermal_stop_interrupts_long_poll_sleep() -> None:
    watchdog = ThermalWatchdog(poll_interval_seconds=60)
    watchdog.start()
    owned_thread = watchdog._thread
    started = time.monotonic()
    watchdog.stop()

    assert time.monotonic() - started < 2
    assert owned_thread is not None and not owned_thread.is_alive()
    assert watchdog._thread is None
```

In `tests/test_telegram_orchestrator.py`, extend the existing `FakeBot` tests:

```python
def test_telegram_wiring_returns_handlers_that_unwire_exactly(orch) -> None:
    bot = _fake_bot()
    handlers = orch._wire_bus_to_bot(bot)
    orch._unwire_bus_handlers(handlers)

    for event_type in (
        EventType.APPROVAL_REQUIRED,
        EventType.THERMAL_ALERT,
        EventType.SHADOW_ALERT,
        EventType.SESSION_STARTED,
        EventType.COLD_UPDATE_BATCH_READY,
        EventType.AGENTIC_PROGRESS,
    ):
        orch.bus.publish_type(event_type, {})
    assert bot.calls == []


def test_partial_telegram_wiring_unwinds_prior_exact_handlers(orch, monkeypatch) -> None:
    real_subscribe = orch.bus.subscribe
    calls = 0

    def fail_third(event_type, handler) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("subscribe")
        real_subscribe(event_type, handler)

    monkeypatch.setattr(orch.bus, "subscribe", fail_third)
    with pytest.raises(RuntimeError, match="subscribe"):
        orch._wire_bus_to_bot(_fake_bot())
    assert all(not handlers for handlers in orch.bus._subscribers.values())
```

The test-local `_fake_bot()` returns one object implementing all six callbacks
and appending their names to `calls`. Tests may inspect `_subscribers` only to
prove absence after the partial-acquisition failure; production code must use
`unsubscribe`, not mutate that mapping.

- [ ] **Step 2: Run the ownership tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_runtime_component_shutdown.py tests/test_telegram_orchestrator.py -q`

Expected: FAIL because polling sleeps are not interruptible, Telegram wiring
returns no handles, and stop clears thread fields without proving termination.

- [ ] **Step 3: Implement cooperative ownership release**

Give both polling classes a private `threading.Event`. `start()` sets
`_running=True` and clears it;
their loops replace `time.sleep(poll_interval)` with
`stop_event.wait(poll_interval)` and return when signalled. `stop()` sets the
`_running=False` before setting the event, joins for a bounded two seconds, and
raises if the thread is still alive.
Only after verified termination may it clear `_thread` and other owner fields.

`_wire_bus_to_bot` evaluates each bound method once, subscribes it, and appends
that exact `(EventType, Handler)` pair to a local list. If any later subscribe
fails, it unwinds the already-added pairs in reverse order before re-raising.
On success it returns an immutable tuple. `start_telegram_bot` stores it in
`self._telegram_subscriptions`; `stop_telegram_bot` asks the bot to stop, joins
and verifies the exact thread, then unsubscribes every stored pair. A failed
join or unsubscribe preserves the bot, thread, and remaining pairs for retry;
fields are cleared only after all three ownership classes are released.

Change `Orchestrator.stop_offline_monitor()` and thermal release wrappers with
the same rule: never clear the owning field until the owner's `stop()` returns
after a verified dead thread. The runner captures the owner object in each
lifecycle closure so an unexpected orchestrator field change cannot redirect a
cleanup.

- [ ] **Step 4: Verify GREEN and type-check**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_runtime_component_shutdown.py tests/test_telegram_orchestrator.py tests/test_telegram_disable_flag.py tests/test_gate_i_service.py -q`

Expected: PASS with no `atlas-offline-monitor`, `atlas-thermal`, or
`atlas-telegram-bot` thread left alive.

Run: `MYPYPATH=src .venv/bin/python -m mypy src/atlas/core/orchestrator.py src/atlas/core/offline_monitor.py src/atlas/thermal/watchdog.py`

Expected: `Success: no issues found`.

- [ ] **Step 5: Commit Task 7A**

```bash
git status --short --branch
git add src/atlas/core/orchestrator.py src/atlas/core/offline_monitor.py \
  src/atlas/thermal/watchdog.py tests/test_runtime_component_shutdown.py \
  tests/test_telegram_orchestrator.py
git commit -m "fix(runtime): retain reversible component ownership"
```

---

### Task 8: Make `AtlasServiceRunner` startup transactional

**Files:**
- Modify: `src/atlas/runtime/service_runner.py:33-91,93-277,297-393`
- Modify: `tests/test_gate_i_service.py`
- Create: `tests/test_service_runner_transactional.py`
- Modify: `docs/superpowers/specs/2026-08-02-atlas-integrity-recovery-program-design.md:214-230`
- Modify: `WORK_LEDGER.md`

**Interfaces:**
- Consumes: `LifecycleStack`, reversible `EventBus`, `DashboardServer`, Prometheus policy/status, and existing orchestrator start/stop methods.
- Produces: `_acquire_component(name, required, start, stop) -> bool`, `start()`, and idempotent `stop()` with audited reverse rollback.

- [ ] **Step 1: Write a parameterized partial-start rollback test**

```python
from __future__ import annotations

from types import SimpleNamespace

import pytest

from atlas.runtime.service_runner import AtlasServiceRunner


@pytest.mark.parametrize(
    ("failing_component", "expected_cleanup"),
    [
        ("operational_alerts", []),
        ("offline_monitor", ["operational_alerts"]),
    ],
)
def test_required_start_failure_rolls_back_in_reverse_order(
    runner_factory,
    failing_component: str,
    expected_cleanup: list[str],
) -> None:
    runner, fake = runner_factory(fail_on=failing_component)

    with pytest.raises(RuntimeError, match=failing_component):
        runner.start()

    assert fake.cleaned == expected_cleanup
    assert runner._running is False
    assert runner.status_snapshot()["status"] == "failed"
    assert fake.audit_actions.count("service.start_failed") == 1


def test_required_prometheus_failure_rolls_back_every_prior_owner(
    runner_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_PROMETHEUS_MODE", "required")
    runner, fake = runner_factory(fail_on="prometheus", enable_all=True)

    with pytest.raises(RuntimeError, match="prometheus"):
        runner.start()

    assert fake.cleaned == [
        "dashboard",
        "thermal",
        "telegram",
        "offline_monitor",
        "operational_alerts",
    ]
    assert runner.status_snapshot()["status"] == "failed"
```

The `runner_factory` is a local fake orchestrator fixture in this test file. It
accepts keyword-only `fail_on: str | None`, `fail_stop_once_on: str | None`, and
`enable_all: bool`; it returns `tuple[AtlasServiceRunner, SimpleNamespace]`.
It exposes only attributes used by `AtlasServiceRunner`. Every successful start
appends its component name, every stop appends to `cleaned`, and the requested
component raises `RuntimeError(component)`. With `enable_all=True`, all optional
stages before Prometheus are enabled so the required-Prometheus case proves the
real rollback order.

- [ ] **Step 2: Run the rollback test and verify RED**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_service_runner_transactional.py::test_required_start_failure_rolls_back_in_reverse_order -q`

Expected: FAIL because current `stop()` returns when `_started` is false and no rollback registry exists.

- [ ] **Step 3: Add optional-stage, idempotency, cleanup-failure, and subscription tests**

```python
@pytest.mark.parametrize(
    "failing_component",
    [
        "telegram",
        "thermal",
        "dashboard",
        "prometheus",
        "maintenance",
        "self_audit",
        "swarm",
        "audit_sample",
        "knowledge",
    ],
)
def test_optional_start_failure_degrades_and_keeps_core_alive(
    runner_factory,
    monkeypatch: pytest.MonkeyPatch,
    failing_component: str,
) -> None:
    monkeypatch.setenv("ATLAS_PROMETHEUS_MODE", "optional")
    runner, fake = runner_factory(fail_on=failing_component, enable_all=True)

    runner.start()
    try:
        assert runner.status_snapshot()["status"] == "degraded"
        assert runner.status_snapshot()["components"][failing_component]["status"] == (
            "degraded"
        )
        assert failing_component not in runner._lifecycle.names
    finally:
        runner.stop()

    assert fake.bus_subscription_count == 0
    assert fake.alive_components == set()


def test_second_start_is_rejected_without_duplicate_components(runner_factory) -> None:
    runner, fake = runner_factory()
    runner.start()
    try:
        with pytest.raises(RuntimeError, match="already started"):
            runner.start()
        assert fake.started.count("offline_monitor") == 1
    finally:
        runner.stop()


def test_failed_cleanup_remains_owned_and_second_stop_retries(runner_factory) -> None:
    runner, fake = runner_factory(fail_stop_once_on="telegram", enable_all=True)
    runner.start()

    with pytest.raises(ExceptionGroup) as caught:
        runner.stop()

    assert [type(error).__name__ for error in caught.value.exceptions] == [
        "RuntimeError"
    ]
    assert runner._lifecycle.names == ("telegram",)
    assert "telegram" in fake.alive_components
    assert runner.status_snapshot()["status"] == "failed"
    assert "offline_monitor" in fake.cleaned
    assert "operational_alerts" in fake.cleaned
    assert fake.audit_actions.count("service.cleanup_failed") == 1

    runner.stop()
    assert runner._lifecycle.names == ()
    assert fake.alive_components == set()
    assert runner.status_snapshot()["status"] == "stopped"


def test_stop_unsubscribes_every_runner_owned_handler(runner_factory) -> None:
    runner, fake = runner_factory(enable_all=True)
    runner.start()
    assert fake.bus_subscription_count > 3
    runner.stop()
    assert fake.bus_subscription_count == 0


def test_outcome_audit_failure_preserves_original_and_cannot_skip_cleanup(
    runner_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner, fake = runner_factory(partial_fail_on="thermal", enable_all=True)
    real_transition = runner._status.transition_component

    def reject_thermal_outcome(*args, **kwargs) -> None:
        if kwargs.get("name") == "thermal" and kwargs.get("phase").value == "degraded":
            raise OSError("audit unavailable")
        real_transition(*args, **kwargs)

    monkeypatch.setattr(runner._status, "transition_component", reject_thermal_outcome)
    with pytest.raises(ExceptionGroup) as caught:
        runner.start()

    assert [type(error).__name__ for error in caught.value.exceptions[:2]] == [
        "RuntimeError",
        "OSError",
    ]
    assert fake.alive_components == set()
    assert runner._lifecycle.names == ()


def test_partial_cleanup_failure_is_registered_before_outer_rollback(
    runner_factory,
) -> None:
    runner, fake = runner_factory(
        partial_fail_on="thermal",
        fail_stop_once_on="thermal",
        enable_all=True,
    )

    with pytest.raises(ExceptionGroup):
        runner.start()

    assert fake.stop_attempts["thermal"] == 2
    assert fake.alive_components == set()
    assert runner._lifecycle.names == ()


def test_ready_projection_failure_rolls_back_the_acquired_owner(
    runner_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner, fake = runner_factory()
    real_transition = runner._status.transition_component

    def reject_offline_ready(*args, **kwargs) -> None:
        if kwargs.get("name") == "offline_monitor" and kwargs.get("phase").value == "ready":
            raise OSError("audit unavailable")
        real_transition(*args, **kwargs)

    monkeypatch.setattr(runner._status, "transition_component", reject_offline_ready)
    with pytest.raises(OSError, match="audit unavailable"):
        runner.start()

    assert "offline_monitor" in fake.cleaned
    assert fake.alive_components == set()


def test_stop_projection_failure_does_not_skip_other_outcomes(
    runner_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner, fake = runner_factory(enable_all=True)
    runner.start()
    real_transition = runner._status.transition_component

    def reject_one_stopped(*args, **kwargs) -> None:
        if kwargs.get("name") == "telegram" and kwargs.get("phase").value == "stopped":
            raise OSError("audit unavailable")
        real_transition(*args, **kwargs)

    monkeypatch.setattr(runner._status, "transition_component", reject_one_stopped)
    with pytest.raises(OSError, match="audit unavailable"):
        runner.stop()

    assert fake.alive_components == set()
    assert fake.outcome_attempts.issuperset(fake.started)
    assert runner.status_snapshot()["status"] == "failed"


@pytest.mark.parametrize(
    ("component", "required"),
    [
        ("operational_alerts", True),
        ("offline_monitor", True),
        ("telegram", False),
        ("thermal", False),
        ("dashboard", False),
        ("maintenance", False),
        ("self_audit", False),
        ("swarm", False),
        ("audit_sample", False),
        ("knowledge", False),
    ],
)
def test_partial_acquisition_is_cleaned_when_start_then_raises(
    runner_factory,
    component: str,
    required: bool,
) -> None:
    runner, fake = runner_factory(
        partial_fail_on=component,
        enable_all=True,
    )

    if required:
        with pytest.raises(RuntimeError, match=component):
            runner.start()
    else:
        runner.start()
        runner.stop()

    assert component in fake.cleaned
    assert fake.alive_components == set()
```

Extend `runner_factory` with `partial_fail_on: str | None` and
`fail_stop_once_on: str | None`. That fake start marks the named component alive
and then raises; the first requested stop attempt raises without removing it,
and the next succeeds. Expose `stop_attempts: Counter[str]` and
`outcome_attempts: set[str]`. This proves cleanup
of a partially acquired owner and retry retention rather than failure before
acquisition.

- [ ] **Step 4: Implement explicit acquisition and rollback**

Add `Callable` from `collections.abc`. At runner construction, create
`LifecycleStack`, set every owned component field to `None`, and remove
`_started` as the cleanup authority. `_started` may remain as a compatibility
observation, but cleanup decisions use the stack.

Use this acquisition skeleton:

```python
def _acquire_component(
    self,
    *,
    name: str,
    required: bool,
    start: Callable[[], bool],
    stop: Callable[[], None],
) -> bool:
    self._status.transition_component(
        name=name,
        phase=ComponentPhase.STARTING,
        required=required,
        reason="starting",
    )
    try:
        acquired = start()
    except Exception as start_error:
        errors: list[Exception] = [start_error]
        try:
            stop()
        except Exception as cleanup_exc:
            errors.append(cleanup_exc)
            # A partial owner whose cleanup failed is still an owner. The
            # outer rollback must retry it.
            if name not in self._lifecycle.names:
                self._lifecycle.register(name, stop)
        phase = ComponentPhase.FAILED if required else ComponentPhase.DEGRADED
        try:
            self._status.transition_component(
                name=name,
                phase=phase,
                required=required,
                reason=_sanitized_error(start_error),
            )
        except Exception as status_error:
            errors.append(status_error)
        if required and len(errors) == 1:
            raise
        if len(errors) > 1:
            raise ExceptionGroup(f"{name} acquisition failed", errors)
        _log.exception("optional component %s failed to start", name)
        return False
    if not acquired:
        if required:
            self._status.transition_component(
                name=name,
                phase=ComponentPhase.FAILED,
                required=True,
                reason="did_not_acquire",
            )
            raise RuntimeError(f"required component did not acquire: {name}")
        self._status.transition_component(
            name=name,
            phase=ComponentPhase.DISABLED,
            required=required,
            reason="disabled",
        )
        return False
    try:
        self._lifecycle.register(name, stop)
    except Exception as register_error:
        errors = [register_error]
        try:
            stop()
        except Exception as cleanup_error:
            errors.append(cleanup_error)
        raise ExceptionGroup(f"{name} ownership registration failed", errors)
    self._status.transition_component(
        name=name,
        phase=ComponentPhase.READY,
        required=required,
        reason="started",
    )
    return True
```

The skeleton's exception list is deliberately flat and ordered. If a nested
`ExceptionGroup` arrives from a lower owner, flatten its leaf exceptions while
preserving encounter order before adding runner-level secondary failures. A
shared `_raise_lifecycle_errors` helper re-raises the sole leaf directly and
creates a flat `ExceptionGroup` only for two or more leaves. Never
serialize exception messages into status or audit payloads; the aggregate is
for the in-process caller, while persisted evidence uses sanitized types and
`errno` only.

Required components in R2 are `operational_alerts` and `offline_monitor`.
Telegram, thermal, dashboard,
maintenance, self-audit, swarm, audit-sample, and knowledge are optional. A
disabled optional component returns `False`; it is not degraded. Adapt existing
`None`-returning starters with small owned wrappers that return `True` only
after acquisition; do not infer acquisition from a component field later. For
example:

```python
def _acquire_offline_monitor(self) -> bool:
    self._orch.start_offline_monitor(
        poll_interval_seconds=int(os.environ.get("ATLAS_OFFLINE_POLL_S", "60"))
    )
    self._offline_monitor = self._orch._offline_monitor
    return True


def _release_offline_monitor(self) -> None:
    owner = self._offline_monitor
    if owner is None:
        return
    owner.stop()
    if owner._thread is not None:
        raise RuntimeError("offline monitor retained a live thread")
    if self._orch._offline_monitor is owner:
        self._orch._offline_monitor = None
    self._offline_monitor = None
```

Operational-alert acquisition retains the three exact handler objects and its
registered cleanup unsubscribes those same objects. Telegram retains the exact
handler pairs introduced by Task 7A. Each scheduler/thread
cleanup captures the object acquired by that start, requests cooperative stop
where supported, joins it, verifies `is_alive()` is false, and only then clears
the owning field. Dashboard cleanup stops the server and only then calls
`set_orchestrator(None)`; Prometheus cleanup calls the idempotent owner from
Task 3. Application-global FastAPI route definitions are not active resources,
but no route closure may retain an obsolete EventBus.

Prometheus is the one special acquisition path: Task 4 already owns its
`off|optional|required` transitions and partial cleanup. Call
`_start_prometheus_if_enabled()` directly, register its idempotent `stop` on the
lifecycle stack only when it returns `True`, and let a `required` exception
reach the outer fatal rollback. Do not wrap it in `_acquire_component` or emit a
second, contradictory component transition. If it raises while
`self._prometheus` remains non-`None`, its partial cleanup failed: register that
exact owner's retry cleanup before entering the outer rollback. A registration
failure after successful exporter start likewise invokes its stop immediately
and is aggregated; it never leaves an untracked listener.

`start()` rejects a second invocation before publishing another transition,
transitions service to `starting`, acquires components in the current order,
sets `_running=True` before loop threads, and ends in `degraded` if any optional
component is degraded or `ready` otherwise. An optional component start error is
contained only after its degraded transition is successfully audited and
published; an audit/status failure is fatal. On any fatal exception it attempts
`service.start_failed`, but places `LifecycleStack.stop_all()` in a `finally`
path so an audit failure can never skip rollback. Capture the names before the
call and use its `CleanupReport`: independently attempt a `stopped` transition
for every cleaned component and a `failed` transition for every retained
component. Audit every cleanup failure and attempt every remaining projection
even if one audit/status write fails. Finally attempt service `failed`, set
`_running=False`, and call `_raise_lifecycle_errors`: original start leaf errors
first, then cleanup leaves in attempt order, then audit/status errors in
observation order. No secondary failure may hide the initiating one.

`stop()` sets `_running=False`, calls `stop_all`, and applies the same
independent transition/audit loop. It publishes service `stopped` only when the
report is complete and every component outcome projection succeeded. If a
cleanup remains registered, publish service `failed`, preserve its owner, and
raise the ordered aggregate after attempting all others. If resources are all
gone but a status/audit publication failed, do not synthesize success: retain
the visible snapshot semantics from Task 2 and raise. A later `stop()` retries
registered cleanups and may then reach `stopped`. Only an empty stack plus an
already-`stopped` projection returns without duplicate audit.

- [ ] **Step 5: Run R2 focused tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_event_bus_lifecycle.py tests/test_runtime_lifecycle.py tests/test_runtime_component_shutdown.py tests/test_dashboard_runtime_server.py tests/test_service_runner_transactional.py tests/test_gate_i_service.py tests/test_telegram_orchestrator.py -q`

Expected: PASS and the process exits normally with no Atlas-owned threads.

Run: `MYPYPATH=src .venv/bin/python -m mypy src/atlas/core/event_bus.py src/atlas/core/orchestrator.py src/atlas/core/offline_monitor.py src/atlas/thermal/watchdog.py src/atlas/interfaces/dashboard.py src/atlas/runtime/lifecycle.py src/atlas/runtime/service_runner.py`

Expected: `Success: no issues found`.

- [ ] **Step 6: Record factual R2 closure and commit**

Append the executed rollback matrix and idempotency commands to the recovery design. Update `WORK_LEDGER.md` to `R2 complete; R3 next; service remains intentionally stopped`. Do not state that systemd is recovered yet.

```bash
git status --short --branch
git add src/atlas/runtime/service_runner.py tests/test_gate_i_service.py \
  tests/test_service_runner_transactional.py \
  docs/superpowers/specs/2026-08-02-atlas-integrity-recovery-program-design.md \
  WORK_LEDGER.md
git commit -m "fix(runtime): roll back partial service startup"
```

---

### Task 9: Verify readiness by PID and boot identity

**Files:**
- Create: `src/atlas/runtime/readiness.py`
- Create: `tests/test_runtime_readiness.py`

**Interfaces:**
- Consumes: status path, expected systemd `MainPID`, and injectable `FetchText = Callable[[str], str]`.
- Produces: `ReadinessResult(ready, instance_id, required_failures, optional_failures)`, `verify_service_readiness(...)`, and `fetch_local_text(url: str) -> str`.

- [ ] **Step 1: Write failing PID and identity tests**

```python
from __future__ import annotations

import json
from pathlib import Path

from atlas.runtime.readiness import verify_service_readiness


def _write_status(path: Path, *, pid: int = 4321) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "instance_id": "boot-123",
                "pid": pid,
                "status": "ready",
                "components": {},
                "endpoints": [
                    {
                        "name": "dashboard",
                        "url": "http://127.0.0.1:7331/api/health",
                        "required": True,
                        "identity_kind": "json",
                        "instance_id": "boot-123",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_pid_mismatch_is_not_ready(tmp_path: Path) -> None:
    path = tmp_path / "service_status.json"
    _write_status(path, pid=1111)
    result = verify_service_readiness(
        path=path,
        expected_main_pid=4321,
        fetch_text=lambda _url: '{"instance_id":"boot-123"}',
    )
    assert result.ready is False
    assert result.required_failures == ("pid mismatch: status=1111 systemd=4321",)


def test_foreign_json_endpoint_is_not_atlas(tmp_path: Path) -> None:
    path = tmp_path / "service_status.json"
    _write_status(path)
    result = verify_service_readiness(
        path=path,
        expected_main_pid=4321,
        fetch_text=lambda _url: '{"instance_id":"foreign-boot"}',
    )
    assert result.ready is False
    assert result.required_failures == ("dashboard identity mismatch",)
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_runtime_readiness.py -q`

Expected: FAIL because `atlas.runtime.readiness` does not exist.

- [ ] **Step 3: Add Prometheus and optional-degradation tests**

```python
def test_prometheus_identity_metric_proves_listener_ownership(tmp_path: Path) -> None:
    path = tmp_path / "service_status.json"
    _write_status(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["endpoints"][0] = {
        "name": "prometheus",
        "url": "http://127.0.0.1:9464/metrics",
        "required": True,
        "identity_kind": "prometheus",
        "instance_id": "boot-123",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = verify_service_readiness(
        path=path,
        expected_main_pid=4321,
        fetch_text=lambda _url: 'atlas_up 1\natlas_runtime_info{instance_id="boot-123"} 1\n',
    )
    assert result.ready is True


def test_optional_failed_endpoint_is_reported_without_blocking(tmp_path: Path) -> None:
    path = tmp_path / "service_status.json"
    _write_status(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["status"] = "degraded"
    payload["endpoints"][0]["required"] = False
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = verify_service_readiness(
        path=path,
        expected_main_pid=4321,
        fetch_text=lambda _url: '{"instance_id":"foreign-boot"}',
    )
    assert result.ready is True
    assert result.optional_failures == ("dashboard identity mismatch",)


def test_required_non_endpoint_component_blocks_readiness(tmp_path: Path) -> None:
    path = tmp_path / "service_status.json"
    _write_status(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["components"]["maintenance"] = {
        "status": "failed",
        "required": True,
        "reason": "RuntimeError",
        "updated_at": "2026-08-02T18:00:01+00:00",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = verify_service_readiness(
        path=path,
        expected_main_pid=4321,
        fetch_text=lambda _url: '{"instance_id":"boot-123"}',
    )

    assert result.ready is False
    assert result.required_failures == ("maintenance component failed",)


def test_optional_non_endpoint_component_degrades_without_blocking(
    tmp_path: Path,
) -> None:
    path = tmp_path / "service_status.json"
    _write_status(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["status"] = "degraded"
    payload["components"]["maintenance"] = {
        "status": "degraded",
        "required": False,
        "reason": "RuntimeError",
        "updated_at": "2026-08-02T18:00:01+00:00",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = verify_service_readiness(
        path=path,
        expected_main_pid=4321,
        fetch_text=lambda _url: '{"instance_id":"boot-123"}',
    )

    assert result.ready is True
    assert result.optional_failures == ("maintenance component degraded",)


def test_invalid_json_is_not_ready_instead_of_raising(tmp_path: Path) -> None:
    path = tmp_path / "service_status.json"
    path.write_text("{", encoding="utf-8")

    result = verify_service_readiness(
        path=path,
        expected_main_pid=4321,
        fetch_text=lambda _url: (_ for _ in ()).throw(AssertionError("no fetch")),
    )

    assert result.ready is False
    assert result.required_failures == ("invalid status projection: invalid_json",)


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda payload: payload.update(components=[]), "components_type"),
        (lambda payload: payload.update(endpoints={}), "endpoints_type"),
        (lambda payload: payload.update(pid=True), "pid_type"),
        (lambda payload: payload.update(instance_id=""), "instance_id"),
    ],
)
def test_malformed_projection_types_fail_honestly(
    tmp_path: Path, mutate, reason: str
) -> None:
    path = tmp_path / "service_status.json"
    _write_status(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = verify_service_readiness(
        path=path,
        expected_main_pid=4321,
        fetch_text=lambda _url: (_ for _ in ()).throw(AssertionError("no fetch")),
    )
    assert result.ready is False
    assert result.required_failures == (f"invalid status projection: {reason}",)


@pytest.mark.parametrize("case", ["duplicate", "foreign_record", "unknown_kind"])
def test_invalid_endpoint_contract_never_fetches(tmp_path: Path, case: str) -> None:
    path = tmp_path / "service_status.json"
    _write_status(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    endpoint = payload["endpoints"][0]
    if case == "duplicate":
        payload["endpoints"].append(dict(endpoint))
    elif case == "foreign_record":
        endpoint["instance_id"] = "foreign-boot"
    else:
        endpoint["identity_kind"] = "guess"
    path.write_text(json.dumps(payload), encoding="utf-8")
    fetched: list[str] = []

    result = verify_service_readiness(
        path=path,
        expected_main_pid=4321,
        fetch_text=lambda url: fetched.append(url) or "",
    )

    assert result.ready is False
    assert fetched == []


def test_non_loopback_endpoint_is_rejected_before_fetch(tmp_path: Path) -> None:
    path = tmp_path / "service_status.json"
    _write_status(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["endpoints"][0]["url"] = "http://example.invalid/api/health"
    path.write_text(json.dumps(payload), encoding="utf-8")
    fetched: list[str] = []

    result = verify_service_readiness(
        path=path,
        expected_main_pid=4321,
        fetch_text=lambda url: fetched.append(url) or "",
    )

    assert result.ready is False
    assert result.required_failures == ("dashboard endpoint is not loopback",)
    assert fetched == []
```

Add `import pytest` to this test module. Type the `mutate` parameter as
`Callable[[dict[str, object]], None]` in the committed test rather than leaving
it implicit.

- [ ] **Step 4: Implement the verifier with no network fallback**

`verify_service_readiness` is a total, fail-honest function over untrusted file
bytes: it catches read, decode, and structural errors and returns a finite,
sanitized failure code rather than raising. Validate exact schema `1`, nonempty
string `instance_id`, positive integer (not boolean) `pid`, allowed service
state, mapping-shaped components with typed fields, list-shaped endpoints with
typed fields and unique names, endpoint-record identity equal to the top-level
boot identity, and `identity_kind in {"json", "prometheus"}` before any fetch.
Reject non-loopback URLs before invoking even an injected fetcher.

It must return not-ready for a missing/unreadable file, nonpositive expected
PID, PID mismatch, service state outside `ready|degraded`, any required
component outside `ready`, or any required endpoint fetch/identity failure. A
disabled component is acceptable only when its recorded `required` flag is
false. Non-ready optional components other than `disabled`, and optional
endpoint failures are accumulated in `optional_failures` without making
`ready` false. It must never treat `atlas_up 1` as identity. JSON endpoints
compare their parsed `instance_id`; Prometheus endpoints search for the exact
escaped identity metric generated in Task 3. Catch and sanitize every fetch,
JSON, and decoding exception so `atlas reality` and the installer cannot crash
on a corrupt projection.

Use `urllib.request.urlopen(url, timeout=2)` only in `fetch_local_text`; reject URLs whose parsed hostname is not `127.0.0.1` or `localhost` before opening them.

- [ ] **Step 5: Run tests and mypy to verify GREEN**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_runtime_readiness.py -q`

Expected: PASS.

Run: `MYPYPATH=src .venv/bin/python -m mypy src/atlas/runtime/readiness.py`

Expected: `Success: no issues found`.

- [ ] **Step 6: Commit Task 9**

```bash
git status --short --branch
git add src/atlas/runtime/readiness.py tests/test_runtime_readiness.py
git commit -m "feat(runtime): verify pid-bound service readiness"
```

---

### Task 10: Expose readiness through CLI and `atlas reality`

**Files:**
- Modify: `src/atlas/interfaces/cli.py:891-960`
- Modify: `src/atlas/core/reality_live.py:42-101`
- Modify: `src/atlas/core/reality.py:126-165`
- Create: `tests/test_cli_service_readiness.py`
- Modify: `tests/test_reality_live.py:62-106`

**Interfaces:**
- Consumes: `verify_service_readiness`, the workspace resolved by `collect_reality`, and injected systemctl/readiness runners.
- Produces: `atlas service-readiness --main-pid INTEGER [--status-file PATH] --json`; daemon reality fields `main_pid`, `n_restarts`, `ready`, and `instance_id` while preserving `active`.

- [ ] **Step 1: Write CLI exit-code tests**

```python
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from atlas.interfaces.cli import cli


def test_service_readiness_json_exits_zero_for_current_instance(
    tmp_path: Path, monkeypatch
) -> None:
    status = tmp_path / "service_status.json"
    status.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "instance_id": "boot-123",
                "pid": 4321,
                "status": "ready",
                "components": {},
                "endpoints": [],
            }
        ),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        cli,
        [
            "service-readiness",
            "--main-pid",
            "4321",
            "--status-file",
            str(status),
            "--json",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.output)["ready"] is True


def test_service_readiness_exits_one_for_stale_pid(tmp_path: Path) -> None:
    status = tmp_path / "service_status.json"
    status.write_text(
        '{"schema_version":1,"instance_id":"boot-123","pid":1111,'
        '"status":"ready","components":{},"endpoints":[]}',
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        cli,
        ["service-readiness", "--main-pid", "4321", "--status-file", str(status)],
    )
    assert result.exit_code == 1
    assert "pid mismatch" in result.output
```

- [ ] **Step 2: Run CLI tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_cli_service_readiness.py -q`

Expected: FAIL because the command is not registered.

- [ ] **Step 3: Add reality daemon-projection tests**

Extend the existing fake systemctl runner so it returns values based on the
command argument, and inject readiness so this unit test never opens a socket:

```python
from atlas.runtime.readiness import ReadinessResult


class _SystemctlByProperty:
    def __call__(self, argv: list[str], **_kwargs: object) -> object:
        if "is-active" in argv:
            stdout = "active\n"
        elif any("MainPID" in arg for arg in argv):
            stdout = "4321\n"
        elif any("NRestarts" in arg for arg in argv):
            stdout = "7\n"
        else:
            raise AssertionError(f"unexpected systemctl argv: {argv!r}")
        return type("R", (), {"stdout": stdout, "returncode": 0})()


def test_active_daemon_reports_identity_bound_readiness(tmp_path: Path) -> None:
    status_path = tmp_path / "runtime" / "service_status.json"

    def ready(path: Path, pid: int) -> ReadinessResult:
        assert path == status_path
        assert pid == 4321
        return ReadinessResult(True, "boot-123", (), ())

    state = daemon_state(
        runner=_SystemctlByProperty(),
        status_path=status_path,
        readiness_probe=ready,
    )
    assert state["active"] is True
    assert state["main_pid"] == 4321
    assert state["n_restarts"] == 7
    assert state["ready"] is True
    assert state["instance_id"] == "boot-123"


def test_pid_mismatch_does_not_rewrite_active_state(tmp_path: Path) -> None:
    result = ReadinessResult(False, "boot-123", ("pid mismatch",), ())
    state = daemon_state(
        runner=_SystemctlByProperty(),
        status_path=tmp_path / "service_status.json",
        readiness_probe=lambda _path, _pid: result,
    )
    assert state["active"] is True
    assert state["ready"] is False
    assert state["readiness_failures"] == ["pid mismatch"]
```

- [ ] **Step 4: Implement the read-only CLI command**

```python
@cli.command("service-readiness")
@click.option("--main-pid", required=True, type=click.IntRange(min=1))
@click.option(
    "--status-file",
    type=click.Path(path_type=Path, dir_okay=False),
    default=lambda: Path(os.environ.get("ATLAS_HOME", "~/atlas")).expanduser()
    / "runtime"
    / "service_status.json",
)
@click.option("--json", "as_json", is_flag=True)
def service_readiness(main_pid: int, status_file: Path, as_json: bool) -> None:
    from atlas.runtime.readiness import verify_service_readiness

    result = verify_service_readiness(path=status_file, expected_main_pid=main_pid)
    payload = result.to_dict()
    console.print_json(data=payload) if as_json else console.print(payload)
    if not result.ready:
        raise click.exceptions.Exit(1)
```

Extend `daemon_state` with `status_path: Path | None` and
`readiness_probe: Callable[[Path, int], ReadinessResult] | None`, plus separate
`systemctl show --property=MainPID --value` and
`--property=NRestarts --value` calls. If either value cannot be parsed, report
`ready=None` with a fail-honest reason. If active, call the injected probe or
`verify_service_readiness`; the direct-call fallback path is
`${ATLAS_HOME:-~/atlas}/runtime/service_status.json`. In `collect_reality`, pass
`ws / "runtime" / "service_status.json"` so an explicit `workspace=` never
falls back to ambient environment. Keep the section evidence class `live`
because systemd and endpoints are probed now.

- [ ] **Step 5: Run CLI and reality tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_cli_service_readiness.py tests/test_reality_live.py tests/test_reality.py -q`

Expected: PASS.

Run: `MYPYPATH=src .venv/bin/python -m mypy src/atlas/runtime/readiness.py src/atlas/core/reality_live.py src/atlas/core/reality.py src/atlas/interfaces/cli.py`

Expected: `Success: no issues found`.

- [ ] **Step 6: Commit Task 10**

```bash
git status --short --branch
git add src/atlas/interfaces/cli.py src/atlas/core/reality_live.py \
  src/atlas/core/reality.py \
  tests/test_cli_service_readiness.py tests/test_reality_live.py
git commit -m "feat(runtime): expose identity-bound readiness"
```

---

### Task 11: Bound systemd restarts and require stable installer readiness

**Files:**
- Modify: `scripts/atlas-core.service:1-16`
- Modify: `scripts/install_atlas_systemd.sh:6-104`
- Create: `tests/test_install_atlas_systemd.py`
- Modify: `tests/test_daemon_idle_guard.py:123-137`

**Interfaces:**
- Consumes: `atlas service-readiness`, `safe_dotenv.py`, user systemd `MainPID` and `NRestarts`.
- Produces: finite restart burst (`StartLimitIntervalSec=300`, `StartLimitBurst=5`), three stable readiness observations, atomic unit replacement, complete installer rollback to previous bytes/mode plus enabled/active/linger state, and a mode-`0600` `recovery_required` marker when rollback cannot be proven complete.

- [ ] **Step 1: Write unit hardening RED assertions**

```python
def test_service_limits_persistent_restart_bursts() -> None:
    unit = SERVICE_PATH.read_text(encoding="utf-8")
    assert "StartLimitIntervalSec=300" in unit
    assert "StartLimitBurst=5" in unit
    assert "Restart=always" in unit
    assert "RestartSec=10" in unit
```

- [ ] **Step 2: Write a behavioral fake-systemd installer test**

`tests/test_install_atlas_systemd.py` builds a temporary `HOME/bin` with
executable fakes for `systemctl`, `loginctl`, `sudo`, `atlas`, and `sleep`. The
`systemctl` fake must model `daemon-reload`, `enable --now`, `enable`, `disable`,
`start`, `stop`, `is-enabled`, `is-active`, `show MainPID`, `show NRestarts`, and
`status`. The `atlas` fake consumes a scripted sequence of readiness exit codes
from a file. Create an empty mode-`0600` dotenv fixture and invoke the installer
with:

```python
env = {
    **os.environ,
    "HOME": str(tmp_path / "home"),
    "PATH": f"{fake_bin}:{os.environ['PATH']}",
    "ATLAS_INSTALL_ATLAS_BIN": str(fake_bin / "atlas"),
    "ATLAS_INSTALL_PYTHON_BIN": sys.executable,
    "ATLAS_INSTALL_ENV_FILE": str(tmp_path / ".env"),
    "ATLAS_INSTALL_RECOVERY_FILE": str(tmp_path / "install-recovery.json"),
    "ATLAS_INSTALL_READY_TIMEOUT_SECONDS": "8",
}
```

The first test scripts `active` throughout but readiness `[1, 1, 1, 1, 1, 1,
1, 1]`; it asserts installer exit `1`, restoration of the preexisting unit
bytes and mode, restoration of its initially disabled/stopped state, and reversal of
`enable-linger` when the initial `Linger` value was `no`. The second
scripts readiness `[0, 0, 0]` with stable PID/restart count; it asserts installer
exit `0`. The third changes `NRestarts` between successful probes; it asserts
the consecutive counter resets and requires three later stable successes. A
fourth changes `MainPID` while `NRestarts` stays constant and likewise requires
three later stable successes for one PID. A fifth begins enabled/active with
linger already enabled, forces readiness failure, and asserts rollback restarts
the restored unit without disabling linger or leaving the failed replacement
running. The fake records every command so these are behavioral assertions, not
text searches over the shell script.

Add a parameterized rollback-failure matrix for `stop`, unit restore `mv`,
`daemon-reload`, enable/disable restoration, prior-active restart, and
`disable-linger`. PATH fakes may delegate successful `cp`/`mv` calls to their
absolute system binaries and fail only the selected invocation. Every case
asserts that later rollback steps were still attempted, exit is nonzero, no
success banner was printed, the original failure appears before sanitized
rollback step names, and
`${ATLAS_INSTALL_RECOVERY_FILE}` remains mode `0600` with
`state="recovery_required"`, the retained backup path, and the failed step
names. A follow-up successful invocation must consume/remove that marker only
after it has restored or explicitly superseded the retained transaction. Also
kill the installer subprocess during candidate rendering and assert the
original unit remains byte-for-byte intact; this proves replacement is atomic,
not merely recoverable through the normal EXIT trap.

- [ ] **Step 3: Run installer tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_install_atlas_systemd.py tests/test_daemon_idle_guard.py::TestSystemdHardening -q`

Expected: FAIL because the unit lacks start limits and the installer accepts transient `active` without identity.

- [ ] **Step 4: Add finite restart limits**

Add under `[Unit]`:

```ini
StartLimitIntervalSec=300
StartLimitBurst=5
```

Keep `Restart=always`, `RestartSec=10`, `TimeoutStopSec=1h`, `KillMode=control-group`, and all existing hardening.

- [ ] **Step 5: Replace transient-active readiness with stable identity checks**

Add explicit, validated command/file seams so the behavioral test reaches the
same shell branch as production while intercepting the absolute Atlas path:

```bash
ATLAS_BIN="${ATLAS_INSTALL_ATLAS_BIN:-$REPO_ROOT/.venv/bin/atlas}"
PYTHON_BIN="${ATLAS_INSTALL_PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"
ENV_FILE="${ATLAS_INSTALL_ENV_FILE:-$REPO_ROOT/.env}"
if [ ! -x "$ATLAS_BIN" ] || [ ! -x "$PYTHON_BIN" ] || [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: Atlas binary, Python binary, and dotenv file must exist" >&2
  exit 2
fi
```

Before replacing `UNIT_DST`, copy an existing unit with metadata to a `mktemp`
backup and remember whether it existed, its mode, whether it was enabled, and
whether it was active. Render the candidate into a mode-`0600` temporary file
in the destination directory, close it successfully, and atomically `mv` that
exact file over `UNIT_DST`; never stream `sed` directly into the live unit. Read the
initial `Linger` state before any mutation and accept only the exact values
`yes|no`; an unreadable/unknown value aborts before replacement. Install a trap
that removes disposable temporaries but preserves evidence needed by a failed
rollback. Refuse to begin a new transaction while an unresolved recovery marker
exists unless its retained backup is first reconciled. On any failure after replacement: stop the new unit;
restore the backup or remove only the newly-created exact `UNIT_DST`; run
`systemctl --user daemon-reload`; restore enabled/disabled state; restore
active/stopped state; and, if this transaction changed linger from `no` to
`yes`, run `sudo loginctl disable-linger "$USER_NAME"` and verify it returned to
`no`. Attempt every rollback step independently. Aggregate rollback failures in
the final error rather than masking the original failure. If any rollback step
fails, write the sanitized mode-`0600` JSON recovery marker at
`${ATLAS_INSTALL_RECOVERY_FILE:-$HOME/.local/state/atlas/install_atlas_systemd.recovery.json}`,
retain the backup, and report `recovery_required`; never print or return success.
If rollback is complete, remove backup and marker. Mark the transaction committed only after all stable readiness
observations pass, so failures from linger, `enable --now`, probing, or final
verification use the same rollback path. A successful install intentionally
retains any linger enablement it performed.

Inside the bounded loop:

```bash
stable_reads=0
last_main_pid=""
last_restarts=""
for ((attempt = 1; attempt <= READY_TIMEOUT_SECONDS; attempt++)); do
  if systemctl --user is-active --quiet "$UNIT_NAME"; then
    main_pid="$(systemctl --user show "$UNIT_NAME" --property=MainPID --value)"
    n_restarts="$(systemctl --user show "$UNIT_NAME" --property=NRestarts --value)"
    if [[ "$main_pid" =~ ^[1-9][0-9]*$ ]] \
      && [[ "$n_restarts" =~ ^[0-9]+$ ]] \
      && PYTHONPATH="$REPO_ROOT/src" \
        "$PYTHON_BIN" "$REPO_ROOT/scripts/safe_dotenv.py" \
        "$ENV_FILE" -- "$ATLAS_BIN" \
        service-readiness --main-pid "$main_pid" --json >/dev/null; then
      if [ "$main_pid" = "$last_main_pid" ] \
        && [ "$n_restarts" = "$last_restarts" ]; then
        stable_reads=$((stable_reads + 1))
      else
        stable_reads=1
        last_main_pid="$main_pid"
        last_restarts="$n_restarts"
      fi
      if [ "$stable_reads" -ge 3 ]; then
        ready=1
        break
      fi
    else
      stable_reads=0
      last_main_pid=""
      last_restarts="$n_restarts"
    fi
  else
    stable_reads=0
    last_main_pid=""
    last_restarts=""
  fi
  sleep 1
done
```

- [ ] **Step 6: Run installer tests and Bash syntax checks**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_install_atlas_systemd.py tests/test_daemon_idle_guard.py::TestSystemdHardening -q`

Expected: PASS.

Run: `bash -n scripts/install_atlas_systemd.sh && systemd-analyze --user verify scripts/atlas-core.service`

Expected: exit `0`; warnings unrelated to this user unit must be reported rather than suppressed.

- [ ] **Step 7: Commit Task 11**

```bash
git status --short --branch
git add scripts/atlas-core.service scripts/install_atlas_systemd.sh \
  tests/test_install_atlas_systemd.py tests/test_daemon_idle_guard.py
git commit -m "fix(systemd): require stable atlas readiness"
```

---

### Task 12: Prove hermetic recovery and close R without activating A

**Files:**
- Modify: `scripts/gate_i_smoke.py:12-36`
- Create: `scripts/runtime_systemd_smoke.py`
- Create: `tests/test_runtime_systemd_smoke.py`
- Modify: `docs/operations/prometheus_setup.md`
- Modify: `docs/superpowers/specs/2026-08-02-atlas-integrity-recovery-program-design.md:232-257`
- Modify: `WORK_LEDGER.md`
- Modify: `MEMORY.md`

**Interfaces:**
- Consumes: completed R1/R2/R3 status/readiness contracts and exact unit `atlas-core.service`.
- Produces: self-deleting hermetic foreground smoke, opt-in systemd smoke with verified full rollback or durable `recovery_required` evidence, corrected operator runbook, and an honest R closure that leaves A blocked.

- [ ] **Step 1: Write the systemd-smoke refusal and rollback tests**

```python
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.runtime_systemd_smoke import SmokeError, run_smoke


def test_smoke_refuses_without_explicit_opt_in(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    with pytest.raises(SmokeError, match="ATLAS_RUNTIME_SYSTEMD_SMOKE=1"):
        run_smoke(
            env={},
            unit_dir=tmp_path,
            run=lambda argv: calls.append(argv) or "",
            probe=lambda _pid: True,
            sleep=lambda _seconds: None,
        )
    assert calls == []
    assert list(tmp_path.iterdir()) == []


def test_smoke_refuses_if_exact_unit_is_already_active(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def run(argv: list[str]) -> str:
        calls.append(argv)
        return "active" if "is-active" in argv else ""

    with pytest.raises(SmokeError, match="must be inactive"):
        run_smoke(
            env={
                "ATLAS_RUNTIME_SYSTEMD_SMOKE": "1",
                "HOME": str(tmp_path / "home"),
            },
            unit_dir=tmp_path,
            run=run,
            probe=lambda _pid: True,
            sleep=lambda _seconds: None,
        )
    assert ["systemctl", "--user", "start", "atlas-core.service"] not in calls
    assert not (tmp_path / "atlas-core.service.d").exists()
    assert not (tmp_path / "home").exists()


def test_smoke_restores_dropin_and_stopped_state_after_failure(tmp_path: Path) -> None:
    installed_unit = tmp_path / "atlas-core.service"
    installed_unit.write_text("previous unit", encoding="utf-8")
    installed_unit.chmod(0o640)
    candidate_unit = tmp_path / "candidate-atlas-core.service"
    candidate_unit.write_text("candidate unit", encoding="utf-8")
    dropin_dir = tmp_path / "atlas-core.service.d"
    dropin_dir.mkdir()
    dropin = dropin_dir / "90-runtime-recovery.conf"
    dropin.write_text("previous", encoding="utf-8")
    dropin.chmod(0o600)
    calls: list[list[str]] = []

    def run(argv: list[str]) -> str:
        calls.append(argv)
        if any("MainPID" in arg for arg in argv):
            return "4321"
        if any("NRestarts" in arg for arg in argv):
            return "4781"
        return ""

    with pytest.raises(SmokeError, match="readiness"):
        run_smoke(
            env={
                "ATLAS_RUNTIME_SYSTEMD_SMOKE": "1",
                "HOME": str(tmp_path / "home"),
            },
            unit_dir=tmp_path,
            candidate_unit=candidate_unit,
            run=run,
            probe=lambda _pid: False,
            sleep=lambda _seconds: None,
        )

    assert installed_unit.read_text(encoding="utf-8") == "previous unit"
    assert installed_unit.stat().st_mode & 0o777 == 0o640
    assert dropin.read_text(encoding="utf-8") == "previous"
    assert dropin.stat().st_mode & 0o777 == 0o600
    assert ["systemctl", "--user", "stop", "atlas-core.service"] in calls
    assert calls[-1] == ["systemctl", "--user", "daemon-reload"]


def test_success_also_restores_unit_and_leaves_service_stopped(tmp_path: Path) -> None:
    installed_unit = tmp_path / "atlas-core.service"
    installed_unit.write_text("previous unit", encoding="utf-8")
    candidate_unit = tmp_path / "candidate-atlas-core.service"
    candidate_unit.write_text("candidate unit", encoding="utf-8")
    active = False
    calls: list[list[str]] = []
    probes: list[int] = []
    sleeps: list[float] = []

    def run(argv: list[str]) -> str:
        nonlocal active
        calls.append(argv)
        if "is-active" in argv:
            return "active" if active else "inactive"
        if "start" in argv:
            active = True
        if "stop" in argv:
            active = False
        if any("MainPID" in arg for arg in argv):
            return "4321"
        if any("NRestarts" in arg for arg in argv):
            return "8"
        return ""

    run_smoke(
        env={
            "ATLAS_RUNTIME_SYSTEMD_SMOKE": "1",
            "HOME": str(tmp_path / "home"),
        },
        unit_dir=tmp_path,
        candidate_unit=candidate_unit,
        run=run,
        probe=lambda pid: probes.append(pid) or True,
        sleep=sleeps.append,
    )

    assert probes == [4321, 4321, 4321]
    assert sleeps == [15.0, 15.0]
    assert active is False
    assert installed_unit.read_text(encoding="utf-8") == "previous unit"
    assert not (tmp_path / "atlas-core.service.d" / "90-runtime-recovery.conf").exists()
    assert calls[-1] == ["systemctl", "--user", "daemon-reload"]


def test_smoke_dropin_neutralizes_live_dotenv_and_external_transports(
    tmp_path: Path,
) -> None:
    # Use the same successful fake as above and capture the drop-in before the
    # finally block removes it.
    captured: list[str] = []

    def inspect_dropin(path: Path) -> None:
        captured.append(path.read_text(encoding="utf-8"))

    _run_successful_fake_smoke(tmp_path, after_start=inspect_dropin)

    raw = captured[0]
    assert "EnvironmentFile=" in raw
    assert "UnsetEnvironment=ATLAS_PROMETHEUS" in raw
    assert "HERMES_KANBAN_TRANSPORT" in raw
    assert "HERMES_SSH_HOST" in raw
    assert "ATLAS_MAINTENANCE_SCHEDULER=0" in raw
    assert "ATLAS_PROMETHEUS_MODE=optional" in raw
    assert "StandardOutput=journal" in raw


@pytest.mark.parametrize(
    "rollback_step",
    ["stop", "restore_unit", "restore_dropin", "restore_marker", "daemon_reload"],
)
def test_smoke_cleanup_failure_is_aggregated_and_requires_recovery(
    tmp_path: Path, rollback_step: str
) -> None:
    result = _run_failing_cleanup_smoke(tmp_path, rollback_step=rollback_step)

    assert result.error.startswith("readiness failed")
    assert rollback_step in result.error
    assert result.later_cleanup_steps_were_attempted is True
    recovery = json.loads(result.recovery_file.read_text(encoding="utf-8"))
    assert recovery["state"] == "recovery_required"
    assert rollback_step in recovery["failed_steps"]
    assert result.recovery_file.stat().st_mode & 0o777 == 0o600
    assert result.success_reported is False


def test_unresolved_smoke_recovery_marker_refuses_before_systemctl(
    tmp_path: Path,
) -> None:
    recovery = tmp_path / "runtime-smoke-recovery.json"
    recovery.write_text('{"state":"recovery_required"}', encoding="utf-8")
    calls: list[list[str]] = []

    with pytest.raises(SmokeError, match="recovery_required"):
        run_smoke(
            env={
                "ATLAS_RUNTIME_SYSTEMD_SMOKE": "1",
                "ATLAS_RUNTIME_SMOKE_RECOVERY_FILE": str(recovery),
                "HOME": str(tmp_path / "home"),
            },
            unit_dir=tmp_path,
            run=lambda argv: calls.append(argv) or "",
            probe=lambda _pid: True,
            sleep=lambda _seconds: None,
        )
    assert calls == []
```

Add `import json`. `_run_failing_cleanup_smoke` is a test-local helper that
uses the successful state machine already factored above, raises the production
`SmokeCommandError` at exactly one named cleanup step, and returns a small
test-only result record. It must not introduce a production failure-injection
environment variable.

Factor the successful fake setup into the test-local
`_run_successful_fake_smoke` helper used by the last two tests. Its
`after_start` callback is invoked by the fake command runner when it observes
the fixed `systemctl --user start atlas-core.service` argv; it is not a
production seam on `run_smoke`.

- [ ] **Step 2: Run smoke tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_runtime_systemd_smoke.py -q`

Expected: FAIL because `scripts.runtime_systemd_smoke` does not exist.

- [ ] **Step 3: Make foreground Gate I hermetic**

Before importing Atlas in `gate_i_smoke.py`, assign exact safe values rather than `setdefault`:

```python
safe_env = {
    "ATLAS_PENDING_HMAC_KEY": "gate-i-smoke-key",
    "ATLAS_DECIDER": "human",
    "ATLAS_DISABLE_TELEGRAM": "1",
    "ATLAS_MAINTENANCE_SCHEDULER": "0",
    "ATLAS_SELF_AUDIT_SCHEDULER": "0",
    "ATLAS_SWARM_SCHEDULER": "0",
    "ATLAS_AUDIT_SAMPLE_SCHEDULER": "0",
    "ATLAS_KNOWLEDGE_SCHEDULER": "0",
    "ATLAS_SERVE_DASHBOARD": "0",
    "ATLAS_PROMETHEUS_MODE": "off",
    "ATLAS_THERMAL_MONITOR": "0",
    "HERMES_KANBAN_TRANSPORT": "",
    "HERMES_SSH_HOST": "",
    "HERMES_BASE_URL": "",
    "HERMES_API_KEY": "",
    "ATLAS_HERMES_LOCAL": "",
}
os.environ.update(safe_env)
os.environ.pop("ATLAS_PROMETHEUS", None)
```

Set `ATLAS_CORE_ROOT` to `root`, the implementation worktree resolved from the
script, so configuration and code references remain valid. Keep `ATLAS_HOME`
inside a `tempfile.TemporaryDirectory` context so all runtime state, audit,
keys, and status writes are isolated and removed on success or exception. The
explicit empty Hermes variables must be present before
any Atlas import: `python-dotenv` then cannot repopulate them from an ambient
`.env`. Snapshot hashes of package-owned configuration files below `root`
before construction and assert they are unchanged after stop. Capture Atlas-owned
thread names before start; before leaving the temporary-directory context,
assert no newly-created `atlas-*` thread remains and status is exactly
`stopped`.

- [ ] **Step 4: Implement the opt-in systemd smoke**

`run_smoke` uses fixed unit name `atlas-core.service`; it accepts no unit-name
argument. `candidate_unit` defaults to the repository's
`scripts/atlas-core.service` and exists only as a filesystem test seam. It
requires the service inactive at entry. It snapshots the exact installed unit
bytes, mode, and existence, atomically installs the repository candidate, and
writes
`90-runtime-recovery.conf` atomically. The drop-in must reset the base unit's
`EnvironmentFile` list with an empty `EnvironmentFile=`, override
`WorkingDirectory`, `ExecStart`, `PYTHONPATH`, and `ATLAS_CORE_ROOT` to the
implementation worktree, point `ATLAS_HOME` at a temporary smoke directory,
route stdout/stderr to the journal, and remove ambient legacy/provider transport
settings with `UnsetEnvironment` before applying the safe environment above.
At minimum the reset must include `ATLAS_PROMETHEUS`,
`HERMES_KANBAN_TRANSPORT`, `HERMES_SSH_HOST`, `HERMES_BASE_URL`,
`HERMES_API_KEY`, and `ATLAS_HERMES_LOCAL`. It then adds:

```ini
[Service]
EnvironmentFile=
ExecStart=
ExecStart=<worktree>/.venv/bin/atlas serve --poll-interval 1.0
WorkingDirectory=<worktree>
StandardOutput=journal
StandardError=journal
UnsetEnvironment=ATLAS_PROMETHEUS HERMES_KANBAN_TRANSPORT HERMES_SSH_HOST HERMES_BASE_URL HERMES_API_KEY ATLAS_HERMES_LOCAL
Environment=PYTHONPATH=<worktree>/src
Environment=ATLAS_CORE_ROOT=<worktree>
Environment=ATLAS_HOME=<smoke-home>
Environment=ATLAS_PENDING_HMAC_KEY=gate-a-smoke-key
Environment=ATLAS_DECIDER=human
Environment=ATLAS_DISABLE_TELEGRAM=1
Environment=ATLAS_MAINTENANCE_SCHEDULER=0
Environment=ATLAS_SELF_AUDIT_SCHEDULER=0
Environment=ATLAS_SWARM_SCHEDULER=0
Environment=ATLAS_AUDIT_SAMPLE_SCHEDULER=0
Environment=ATLAS_KNOWLEDGE_SCHEDULER=0
Environment=ATLAS_SERVE_DASHBOARD=0
Environment=ATLAS_THERMAL_MONITOR=0
Environment=ATLAS_PROMETHEUS_MODE=optional
Environment=ATLAS_PROMETHEUS_HOST=127.0.0.1
Environment=ATLAS_PROMETHEUS_PORT=9464
```

It backs up any previous drop-in and the `~/.atlas/daemon_idle_parked` marker,
creates the parked marker, reloads systemd, records `NRestarts`, and starts the
unit. After the first valid positive `MainPID`, it requires identity readiness
at that same PID three times at 15-second spacing; every sample re-reads both
`MainPID` and `NRestarts` and fails if either changes. It always stops the unit.
In `finally`, restore or remove the installed unit, restore or remove the
drop-in, restore the parked-marker state, and run `daemon-reload`. Every
subprocess argv is a fixed list beginning with `systemctl --user`; no shell
strings are accepted. The CLI entry point catches only `SmokeError`, writes its
sanitized message to stderr, and exits `1`; a successful run exits `0` after
cleanup.

The production command adapter executes fixed argv with `check=False`, captures
bounded text, and raises sanitized `SmokeCommandError(step, returncode)` for a
nonzero result; injected runners obey the same contract. Before the first
mutation, refuse if
`${ATLAS_RUNTIME_SMOKE_RECOVERY_FILE:-$HOME/.local/state/atlas/runtime_systemd_smoke.recovery.json}`
already records `recovery_required`. Keep installed-unit, drop-in, and parked
marker backups outside the disposable smoke home until restoration is proven.
In `finally`, execute stop and every restore/reload step independently. A
failed stop does not prevent file restoration, but it makes service state
unknown and therefore forces failure. Aggregate the initiating error first and
cleanup step failures afterward. If any cleanup fails, atomically write the
mode-`0600` recovery marker with retained backup paths and failed step names;
do not delete those backups or emit success. Remove them and any old marker only
after exact bytes, modes, marker state, inactive service state, and final
`daemon-reload` have all been verified.

- [ ] **Step 5: Run all R-targeted tests and static checks**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_prometheus_config.py \
  tests/test_prometheus_exporter.py \
  tests/test_service_status.py \
  tests/test_service_runner_prometheus.py \
  tests/test_cli_prometheus_migration.py \
  tests/test_event_bus_lifecycle.py \
  tests/test_runtime_lifecycle.py \
  tests/test_runtime_component_shutdown.py \
  tests/test_telegram_orchestrator.py \
  tests/test_dashboard_runtime_server.py \
  tests/test_service_runner_transactional.py \
  tests/test_gate_i_service.py \
  tests/test_dashboard.py \
  tests/test_runtime_readiness.py \
  tests/test_cli_service_readiness.py \
  tests/test_reality_live.py \
  tests/test_reality.py \
  tests/test_install_atlas_systemd.py \
  tests/test_daemon_idle_guard.py \
  tests/test_runtime_systemd_smoke.py -q
```

Expected: PASS and normal process exit.

Run: `MYPYPATH=src .venv/bin/python -m mypy src/atlas/`

Expected: `Success: no issues found`.

Run: `bash -n scripts/install_atlas_systemd.sh && .venv/bin/python -m py_compile scripts/gate_i_smoke.py scripts/runtime_systemd_smoke.py`

Expected: exit `0`.

- [ ] **Step 6: Run the isolated foreground smoke**

Run: `PYTHONPATH=src .venv/bin/python scripts/gate_i_smoke.py`

Expected: `gate_i_smoke: OK`; status ends `stopped`; no Atlas-owned thread remains.

- [ ] **Step 7: Run repository completion checks before claiming R complete**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/ -q`

Expected: PASS under configured `not computer_use` selection.

Run the Atlas CLI checks only against a disposable workspace; neither command
may construct an `Orchestrator` or `MerkleLogger` over the operator's live
`ATLAS_HOME` during R:

```bash
r_check_home="$(mktemp -d)"
cleanup_r_check() { rm -rf -- "$r_check_home"; }
trap cleanup_r_check EXIT
run_r_check() {
  env -u ATLAS_PROMETHEUS \
    ATLAS_HOME="$r_check_home" ATLAS_CORE_ROOT="$PWD" PYTHONPATH=src \
    ATLAS_PENDING_HMAC_KEY=r-check-key ATLAS_DECIDER=human \
    ATLAS_DISABLE_TELEGRAM=1 ATLAS_MAINTENANCE_SCHEDULER=0 \
    ATLAS_SELF_AUDIT_SCHEDULER=0 ATLAS_SWARM_SCHEDULER=0 \
    ATLAS_AUDIT_SAMPLE_SCHEDULER=0 ATLAS_KNOWLEDGE_SCHEDULER=0 \
    ATLAS_SERVE_DASHBOARD=0 ATLAS_PROMETHEUS_MODE=off \
    ATLAS_THERMAL_MONITOR=0 HERMES_KANBAN_TRANSPORT= \
    HERMES_SSH_HOST= HERMES_BASE_URL= HERMES_API_KEY= \
    ATLAS_HERMES_LOCAL= "$@"
}
run_r_check .venv/bin/atlas audit --verify
run_r_check .venv/bin/atlas reality --json
test "$(systemctl --user is-active atlas-core.service || true)" = "inactive"
```

Expected: the disposable Merkle chain verifies, reality reports its workspace
honestly, and the exact live unit remains inactive. This does **not** claim the
operator's live Merkle chain valid: the true read-only live verifier belongs to
G1/P3 and must pass immediately before A. Remove the disposable directory via
the trap; do not run either Atlas command against the live workspace in R.

- [ ] **Step 8: Prove the live smoke remains gated and defer it to A**

Run only the refusal path during R:

```bash
env -u ATLAS_RUNTIME_SYSTEMD_SMOKE PYTHONPATH=src \
  .venv/bin/python scripts/runtime_systemd_smoke.py
```

Expected: exit `1` before any systemctl mutation with the opt-in instruction.
Do **not** set `ATLAS_RUNTIME_SYSTEMD_SMOKE=1` or start the unit in cut R. The
live systemd run belongs to Activation A, after R3 + G1 + zero-pending P3 +
Merkle validity have all been freshly proven. At that point A invokes this same
script and expects three identity-bound readiness samples, unchanged PID and
`NRestarts`, unit stopped in `finally`, temporary drop-in restored, and
parked-marker state restored. A is successful only if the smoke recovery marker
is absent afterward; `recovery_required` blocks every later activation step.

- [ ] **Step 9: Correct operational documentation and record closure**

Update `prometheus_setup.md` so examples use `ATLAS_PROMETHEUS_MODE=optional`, `127.0.0.1:9464/metrics`, identity metric verification, and the legacy migration mapping. Remove claims that the exporter is served on dashboard port `7331`; dashboard health remains `/api/health` on `7331` only when enabled.

Append R3 code/test evidence to the recovery design and resolve the conflict in
§5.5: R proves the systemd transaction and rollback with fake-systemd tests;
the real systemd acceptance observation is owned by A because running it before
G1/P3 would cross the unhealthy authorization boundary. Update
`WORK_LEDGER.md` to the exact state: `R1-R3 code/tests complete; live systemd
acceptance is deferred to A after G1 + P3 + Merkle, and atlas-core.service stays
stopped`.

Add this one-line lesson to `MEMORY.md`: `Optional listeners require explicit degraded state, boot identity, transactional cleanup, and stable readiness; process active is not service ready.`

- [ ] **Step 10: Commit Task 12 without operator-owned paths**

```bash
git status --short --branch
git add scripts/gate_i_smoke.py scripts/runtime_systemd_smoke.py \
  tests/test_runtime_systemd_smoke.py docs/operations/prometheus_setup.md \
  docs/superpowers/specs/2026-08-02-atlas-integrity-recovery-program-design.md \
  WORK_LEDGER.md MEMORY.md
git diff --cached --check
git commit -m "test(runtime): seal bounded recovery evidence"
```

---

## R1-R3 completion checklist

- [ ] Real occupied-socket test reproduces `EADDRINUSE` without fixed ports.
- [ ] Invalid mode, contradiction, host, and port errors are contextual and sanitized.
- [ ] Healthy exporter returns `atlas_up 1` and current `atlas_runtime_info` identity.
- [ ] Optional exporter failure yields service `degraded`; required failure rolls back and raises.
- [ ] Status transitions audit first and publish schema `1` atomically with mode `0600`; injected pre-rename failures preserve the prior snapshot and post-rename durability failures remain file/memory coherent and fail-honest.
- [ ] Fatal failure at every required stage rolls back in reverse order; failure at every optional stage degrades, continues, and is fully cleaned by final stop.
- [ ] Exact operational, Telegram, and dashboard handlers are reversible; Offline/Thermal polling stops cooperatively.
- [ ] A cleanup failure retains its owner and blocks `stopped`; a later retry empties the lifecycle stack and leaves no owned resource alive.
- [ ] Dashboard bind failures are synchronous and its health response carries current `instance_id`.
- [ ] Readiness rejects stale PID, stale identity, missing/malformed projection, invalid endpoint schema, non-loopback URLs, and foreign listeners without raising or fetching invalid targets.
- [ ] systemd limits persistent restart bursts and the installer requires three stable observations.
- [ ] Fake-systemd tests cover success, transient active, restart/PID changes, timeout, atomic unit replacement, complete rollback, every rollback-failure family, and durable `recovery_required` evidence.
- [ ] Foreground smoke is hermetic and removes its workspace; the live systemd smoke refuses without opt-in, its success/rollback/cleanup-failure transactions are fake-tested, and actual execution is deferred to A.
- [ ] Repository completion CLI checks use a disposable `ATLAS_HOME`; no R command constructs Atlas runtime state over the operator's live workspace.
- [ ] `.env`, scraper config, governance, `.gitignore`, and `docs/fixtures/` remain untouched.
- [ ] R ends stopped and does not authorize gate A or autonomous schedulers.

## Execution handoff

Plan implementation must use one of these modes:

1. **Subagent-Driven (recommended):** use `superpowers:subagent-driven-development`, dispatch a fresh implementation agent per task, and run specification then quality review before advancing.
2. **Inline Execution:** use `superpowers:executing-plans`, execute tasks in order, and stop at the R1, R2, and R3 evidence checkpoints for review.
