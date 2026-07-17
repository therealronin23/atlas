"""Reality report: verifiable operational state for Atlas.

This module is intentionally boring. It reports what can be derived from the
local repo/env and marks everything else as unknown or degraded. No subsystem is
"ready" just because a document says so.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.util import find_spec
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CommandEvidence:
    command: list[str]
    exit_code: int
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "summary": self.summary,
        }


def collect_reality(
    *,
    repo_root: Path | None = None,
    workspace: Path | None = None,
    run_checks: bool = False,
    include_browser: bool = False,
) -> dict[str, Any]:
    """Collect a factual report for the current Atlas checkout."""
    root = (repo_root or _project_root()).resolve()
    ws = (workspace or Path(os.environ.get("ATLAS_HOME", "~/atlas")).expanduser()).resolve()
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": _repo_state(root),
        "workspace": _workspace_state(ws),
        "runtime": _runtime_state(root),
        "tests": _test_state(root),
        "browser": _browser_state(),
        "hermes": _hermes_state(),
        "llm": _llm_state(),
        "mcp": _mcp_state(root, ws),
        "autonomy": _autonomy_state(),
        "docs": _docs_state(root),
        "provider_smoke": _provider_smoke_state(root),
        "checks": {},
    }
    report["capabilities"] = _capability_plane(report)
    if run_checks:
        report["checks"] = _run_checks(root, include_browser=include_browser)
        _project_check_evidence(report)
    report["status"] = _overall_status(report)
    report["strict_failures"] = strict_failures(report)
    return report


def _project_root() -> Path:
    return Path(os.environ.get("ATLAS_CORE_ROOT", Path.cwd())).expanduser()


def _repo_state(root: Path) -> dict[str, Any]:
    version = "unknown"
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            version = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
        except Exception:
            version = "unknown"
    branch = _git(root, "branch", "--show-current")
    sha = _git(root, "rev-parse", "--short", "HEAD")
    status = _git(root, "status", "--short")
    dirty_lines = [ln for ln in status.splitlines() if ln.strip()]
    return {
        "root": str(root),
        "version": version,
        "branch": branch or "unknown",
        "commit": sha or "unknown",
        "dirty": bool(dirty_lines),
        "dirty_count": len(dirty_lines),
        "dirty_paths": dirty_lines[:50],
    }


def _workspace_state(workspace: Path) -> dict[str, Any]:
    audit = workspace / "memory" / "audit"
    merkle: dict[str, Any] = {"status": "unknown", "record_count": None, "reason": "audit dir absent"}
    if audit.exists():
        try:
            from atlas.logging.merkle_logger import MerkleLogger

            logger = MerkleLogger(audit)
            ok, msg = logger.verify_chain()
            merkle = {
                "status": "ok" if ok else "corrupt",
                "record_count": logger.record_count,
                "reason": msg,
            }
        except Exception as exc:  # noqa: BLE001
            merkle = {"status": "error", "record_count": None, "reason": type(exc).__name__}
    return {"path": str(workspace), "exists": workspace.exists(), "merkle": merkle}


def _runtime_state(root: Path) -> dict[str, Any]:
    source_files = list((root / "src" / "atlas").rglob("*.py"))
    test_files = list((root / "tests").glob("test_*.py"))
    return {
        "python": sys.version.split()[0],
        "source_file_count": len(source_files),
        "test_file_count": len(test_files),
    }


def _test_state(root: Path) -> dict[str, Any]:
    pyproject = root / "pyproject.toml"
    addopts = ""
    markers: list[str] = []
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            pytest_cfg = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
            addopts = str(pytest_cfg.get("addopts", ""))
            markers = [str(m) for m in pytest_cfg.get("markers", [])]
        except Exception:
            pass
    return {
        "core": {"status": "unknown", "reason": "run atlas reality --run-checks for live evidence"},
        "browser": {"status": "unknown", "reason": "run atlas reality --run-checks --include-browser"},
        "pytest_addopts": addopts,
        "markers": markers,
    }


def _browser_state() -> dict[str, Any]:
    installed = find_spec("playwright") is not None
    cache = Path.home() / ".cache" / "ms-playwright"
    executables = []
    if cache.exists():
        executables = [
            str(p)
            for p in cache.glob("chromium*/**/*chrome*")
            if p.is_file() and os.access(p, os.X_OK)
        ]
    expected_executable, expected_error = _playwright_chromium_executable()
    expected_present = (
        expected_executable is not None
        and expected_executable.is_file()
        and os.access(expected_executable, os.X_OK)
    )
    status = "ready" if installed and expected_present else "degraded"
    if not installed:
        reason = "missing playwright package"
    elif expected_error:
        reason = f"could not resolve playwright chromium executable: {expected_error}"
    elif not expected_executable:
        reason = "could not resolve playwright chromium executable"
    elif not expected_present:
        reason = f"missing playwright chromium executable: {expected_executable}"
    else:
        reason = f"playwright chromium executable present: {expected_executable}"
    return {
        "status": status,
        "playwright_installed": installed,
        "browser_executable_count": len(executables),
        "expected_chromium_executable": str(expected_executable) if expected_executable else "",
        "expected_chromium_present": expected_present,
        "reason": reason,
    }


def _playwright_chromium_executable() -> tuple[Path | None, str]:
    if find_spec("playwright") is None:
        return None, ""
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415

        manager = sync_playwright().start()
        try:
            return Path(str(manager.chromium.executable_path)), ""
        finally:
            manager.stop()
    except Exception as exc:  # noqa: BLE001
        return None, type(exc).__name__


def _hermes_state() -> dict[str, Any]:
    base_url = os.environ.get("HERMES_BASE_URL", "").strip()
    api_key = os.environ.get("HERMES_API_KEY", "").strip()
    kanban_transport = os.environ.get("HERMES_KANBAN_TRANSPORT", "").strip().lower()
    ssh_host = os.environ.get("HERMES_SSH_HOST", "").strip()
    local_takeover = os.environ.get("ATLAS_HERMES_LOCAL", "").strip().lower() in {"1", "true", "yes"}
    if kanban_transport:
        mode = f"kanban_{kanban_transport}"
        if kanban_transport == "local":
            configured = True
            reason = (
                "local Hermes kanban transport is configured; run a live delegation "
                "for runtime evidence"
            )
        elif kanban_transport == "ssh" and ssh_host:
            from atlas.hermes.kanban_bridge import ssh_destination_is_allowed  # noqa: PLC0415

            configured = ssh_destination_is_allowed(ssh_host)
            reason = (
                "SSH Hermes kanban transport and private/Tailscale host are configured; "
                "run a live delegation for runtime evidence"
                if configured
                else "HERMES_SSH_HOST must be a safe user@private-or-Tailscale destination"
            )
        elif kanban_transport == "ssh":
            configured = False
            reason = "HERMES_KANBAN_TRANSPORT=ssh requires HERMES_SSH_HOST"
        else:
            configured = False
            reason = f"unsupported HERMES_KANBAN_TRANSPORT={kanban_transport!r}"
    elif base_url and api_key:
        mode = "configured"
        configured = True
        reason = (
            "legacy HermesRestAdapter variables are set; only the legacy REST smoke "
            "can verify that compatibility endpoint"
        )
    elif local_takeover:
        mode = "local_takeover"
        configured = True
        reason = "legacy ATLAS_HERMES_LOCAL is set; run a live delegation for runtime evidence"
    else:
        mode = "mock"
        configured = False
        reason = "no native Hermes kanban transport or legacy REST contract configured"
    return {
        "mode": mode,
        "configured": configured,
        "live_verified": False,
        "base_url_set": bool(base_url),
        "api_key_set": bool(api_key),
        "ssh_host_set": bool(ssh_host),
        "reason": reason,
    }


def _llm_state() -> dict[str, Any]:
    keys = {
        "groq": bool(os.environ.get("GROQ_API_KEY")),
        "openrouter": bool(os.environ.get("OPENROUTER_API_KEY")),
        "gemini": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
        "together": bool(os.environ.get("TOGETHER_API_KEY")),
    }
    configured = [name for name, present in keys.items() if present]
    return {
        "mode_env": os.environ.get("ATLAS_INFERENCE_MODE", "auto"),
        "configured_providers": configured,
        "status": "configured" if configured else "stub_or_local",
        "reason": "provider keys present; run inference_smoke for live evidence" if configured else "no external provider keys in environment",
    }


def _mcp_state(root: Path, workspace: Path) -> dict[str, Any]:
    path = Path(os.environ.get("ATLAS_MCP_SERVERS", str(workspace / "mcp_servers.json")))
    if not path.is_absolute():
        path = (root / path).resolve()
    count = 0
    enabled = 0
    error = ""
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                count = len(raw)
                enabled = sum(1 for item in raw if isinstance(item, dict) and item.get("enabled", True))
        except Exception as exc:  # noqa: BLE001
            error = type(exc).__name__
    return {
        "config_path": str(path),
        "config_exists": path.exists(),
        "server_count": count,
        "enabled_count": enabled,
        "status": "configured" if enabled else "empty",
        "error": error,
    }


def _autonomy_state() -> dict[str, Any]:
    decider = os.environ.get("ATLAS_DECIDER", "human").strip() or "human"
    scheduler = os.environ.get("ATLAS_MAINTENANCE_SCHEDULER", "").strip().lower() in {"1", "true", "yes"}
    return {
        "decider": decider,
        "maintenance_scheduler_enabled": scheduler,
        "agentic_auto_approve": [
            t.strip()
            for t in os.environ.get("ATLAS_AGENTIC_AUTO_APPROVE", "").split(",")
            if t.strip()
        ],
    }


def _capability_plane(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Static capability inventory with honest readiness labels."""
    browser = report["browser"]
    hermes = report["hermes"]
    llm = report["llm"]
    mcp = report["mcp"]
    merkle = report["workspace"]["merkle"]
    autonomy = report["autonomy"]
    bwrap_available = shutil.which("bwrap") is not None
    return [
        {
            "name": "audit.merkle",
            "status": "ready" if merkle.get("status") == "ok" else "degraded",
            "trusted": True,
            "mutating": False,
            "reversible": False,
            "evidence": merkle.get("reason", ""),
        },
        {
            "name": "execution.command",
            "status": "ready" if bwrap_available else "degraded",
            "trusted": True,
            "mutating": True,
            "reversible": False,
            "evidence": (
                "bubblewrap is available; structured commands use the OS jail"
                if bwrap_available
                else "bubblewrap is missing; structured command execution will fail closed"
            ),
        },
        {
            "name": "browser.computer_use",
            "status": browser["status"],
            "trusted": False,
            "mutating": True,
            "reversible": False,
            "evidence": browser["reason"],
        },
        {
            "name": "hermes.delegation",
            # Environment variables prove configuration, not reachability or a
            # successful provider/Telegram round trip. A fresh smoke may report
            # live evidence elsewhere, but this static collector never invents it.
            "status": "configured" if hermes["configured"] else "degraded",
            "trusted": False,
            "mutating": True,
            "reversible": False,
            "evidence": hermes["reason"],
        },
        {
            "name": "llm.inference",
            "status": "configured" if llm["configured_providers"] else "degraded",
            "trusted": False,
            "mutating": False,
            "reversible": False,
            "evidence": llm["reason"],
        },
        {
            "name": "mcp.tools",
            "status": "configured" if mcp["enabled_count"] else "empty",
            "trusted": False,
            "mutating": True,
            "reversible": False,
            "evidence": (
                f"enabled_servers={mcp['enabled_count']}; unregister cannot undo "
                "effects performed by third-party code"
            ),
        },
        {
            "name": "self_improvement.cold_update",
            "status": "ready",
            "trusted": True,
            "mutating": True,
            "reversible": True,
            "evidence": "ColdUpdate validates in isolated worktree before apply",
        },
        {
            "name": "autonomy.decider",
            "status": autonomy["decider"],
            "trusted": True,
            "mutating": True,
            "reversible": True,
            "evidence": "high risk remains denied or HITL depending on decider",
        },
    ]


_COUNT_CLAIM_RE = re.compile(r"\b(\d{2,4})\s+(?:tests?|passed|green|verdes?)\b", re.IGNORECASE)


def _docs_state(root: Path) -> dict[str, Any]:
    docs = ["AGENTS.md", "CLAUDE.md", "ROADMAP.md"]
    claims: dict[str, list[int]] = {}
    for name in docs:
        path = root / name
        if not path.is_file():
            claims[name] = []
            continue
        text = path.read_text(encoding="utf-8")
        claims[name] = [int(m.group(1)) for m in _COUNT_CLAIM_RE.finditer(text)]
    unique = sorted({value for values in claims.values() for value in values})
    stale = len(unique) > 1
    return {
        "test_count_claims": claims,
        "unique_test_count_claims": unique,
        "status": "stale" if stale else "ok",
        "reason": "multiple contradictory test-count claims" if stale else "no contradictory test-count claims detected",
    }


def _provider_smoke_state(root: Path) -> dict[str, Any]:
    """Proyecta el último resultado del smoke diario de proveedores
    (``ProviderChainSmoke``, ver maintenance_facade.maintenance_provider_smoke_tick)
    sin disparar ninguna llamada de red: solo lee el fichero de estado que
    ya escribió el daemon. Fichero ausente o ilegible -> ``never_ran`` con
    razón honesta, jamás una excepción (mismo principio fail-honesto que
    ``_mcp_state``)."""
    path = root / "workspace" / "self_build" / "provider_smoke_state.json"
    never_ran: dict[str, Any] = {
        "status": "never_ran",
        "last_run_date": None,
        "ok": [],
        "dead": [],
        "skipped": [],
    }
    if not path.is_file():
        return {
            **never_ran,
            "reason": (
                "no provider_smoke_state.json found; set ATLAS_PROVIDER_SMOKE=1 "
                "to enable the daily provider smoke"
            ),
        }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {
            **never_ran,
            "reason": f"provider_smoke_state.json unreadable: {type(exc).__name__}",
        }
    if not isinstance(raw, dict):
        return {
            **never_ran,
            "reason": "provider_smoke_state.json is not a JSON object",
        }
    last_run_date = raw.get("last_run_date")
    results = raw.get("last_results")
    if not isinstance(results, list):
        results = []

    def _names(outcome: str) -> list[str]:
        return [
            entry["provider_name"]
            for entry in results
            if isinstance(entry, dict)
            and isinstance(entry.get("provider_name"), str)
            and entry.get("outcome") == outcome
        ]

    ok = _names("ok")
    dead = _names("failed")
    skipped = _names("skipped")
    if dead:
        reason = f"{len(dead)} provider(s) dead: {', '.join(dead)}"
    elif not results:
        reason = "provider_smoke_state.json present but empty (no results recorded)"
    else:
        reason = "all probed providers ok or skipped"
    return {
        "status": "ran",
        "last_run_date": last_run_date,
        "ok": ok,
        "dead": dead,
        "skipped": skipped,
        "reason": reason,
    }


def _run_checks(root: Path, *, include_browser: bool) -> dict[str, Any]:
    checks = {
        "pytest_core": _run([sys.executable, "-m", "pytest", "tests/", "-q"], root).to_dict(),
        "mypy": _run([sys.executable, "-m", "mypy", "src/atlas/"], root, extra_env={"MYPYPATH": "src"}).to_dict(),
    }
    if include_browser:
        checks["pytest_browser"] = _run(
            [sys.executable, "-m", "pytest", "tests/", "-q", "-m", "computer_use"],
            root,
        ).to_dict()
    return checks


def _project_check_evidence(report: dict[str, Any]) -> None:
    """Keep the summary test state consistent with freshly executed checks."""
    tests = report.get("tests")
    checks = report.get("checks")
    if not isinstance(tests, dict) or not isinstance(checks, dict):
        return
    for state_name, check_name in (
        ("core", "pytest_core"),
        ("browser", "pytest_browser"),
    ):
        check = checks.get(check_name)
        if not isinstance(check, dict):
            continue
        exit_code = check.get("exit_code")
        summary = str(check.get("summary") or f"exit_code={exit_code}")
        tests[state_name] = {
            "status": "passed" if exit_code == 0 else "failed",
            "reason": summary,
        }


def _default_check_timeout() -> int:
    """Timeout por check, configurable. El default de 180s daba un falso
    `degraded` cuando la suite (sola ~80s) competía con mypy/browser en una
    máquina cargada, y eso abortó la auditoría de 24h del 2026-06-12."""
    raw = os.environ.get("ATLAS_REALITY_TIMEOUT", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return 600


def _run(
    command: list[str],
    root: Path,
    *,
    extra_env: dict[str, str] | None = None,
    timeout_s: int | None = None,
) -> CommandEvidence:
    if timeout_s is None:
        timeout_s = _default_check_timeout()
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", "src")
    if extra_env:
        env.update(extra_env)
    try:
        proc = subprocess.run(
            command,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        summary = _summarize_check_output(proc.stdout, proc.stderr)
        return CommandEvidence(command=command, exit_code=proc.returncode, summary=summary)
    except subprocess.TimeoutExpired:
        return CommandEvidence(command=command, exit_code=-1, summary=f"timeout after {timeout_s}s")


def _summarize_check_output(stdout: str, stderr: str) -> str:
    text = "\n".join(part for part in (stdout, stderr) if part)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for line in reversed(lines):
        if " passed" in line or " failed" in line or line.startswith("Success:"):
            return line
    return lines[-1] if lines else ""


def _overall_status(report: dict[str, Any]) -> str:
    checks = report.get("checks") or {}
    if any(isinstance(v, dict) and v.get("exit_code") not in (0, None) for v in checks.values()):
        return "degraded"
    docs = report.get("docs", {})
    if docs.get("status") == "stale":
        return "degraded"
    merkle = report.get("workspace", {}).get("merkle", {})
    if merkle.get("status") == "corrupt":
        return "degraded"
    return "ok"


def strict_failures(report: dict[str, Any]) -> list[str]:
    """Failures that should make a strict readiness gate exit non-zero."""
    failures: list[str] = []
    if report.get("docs", {}).get("status") != "ok":
        failures.append("docs freshness")
    if report.get("workspace", {}).get("merkle", {}).get("status") not in {"ok", "unknown"}:
        failures.append("merkle integrity")
    checks = report.get("checks") or {}
    for name, check in checks.items():
        if isinstance(check, dict) and check.get("exit_code") != 0:
            failures.append(name)
    if report.get("browser", {}).get("status") != "ready":
        failures.append("browser readiness")
    return failures


def _git(root: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""
