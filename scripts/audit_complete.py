#!/usr/bin/env python3
"""Auditoria completa ejecutable — pytest acotado, mypy y smokes.

Pytest se ejecuta por lotes de ficheros en procesos independientes.  El
aislamiento evita que imports/caches de cientos de módulos se acumulen en un
único proceso hasta superar el ``MemoryMax`` del runner systemd de 24 horas.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SENSITIVE_ENV_KEYS = (
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "TOGETHER_API_KEY",
    "GEMINI_API_KEY",
    "HERMES_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "ATLAS_PENDING_HMAC_KEY",
    "TAILSCALE_AUTH_KEY",
)

DEFAULT_TEST_BATCH_SIZE = 20
MAX_TEST_BATCH_SIZE = 64
DEFAULT_CHECK_TIMEOUT_SECONDS = 1800
MAX_CHECK_TIMEOUT_SECONDS = 21600


def redact(text: str, env: dict) -> str:
    redacted = text
    for key in SENSITIVE_ENV_KEYS:
        value = str(env.get(key, "")).strip()
        if value:
            redacted = redacted.replace(value, f"***{key}***")
    return redacted


def _check_timeout(env: dict) -> int:
    raw = str(
        env.get(
            "ATLAS_AUDIT_CHECK_TIMEOUT_SECONDS",
            DEFAULT_CHECK_TIMEOUT_SECONDS,
        )
    )
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_CHECK_TIMEOUT_SECONDS
    if 1 <= value <= MAX_CHECK_TIMEOUT_SECONDS:
        return value
    return DEFAULT_CHECK_TIMEOUT_SECONDS


def run(cmd: list[str], cwd: Path, env: dict | None = None) -> dict:
    e = {**os.environ, **(env or {})}
    timeout = _check_timeout(e)
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=e,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
    if timed_out:
        stderr = f"{stderr or ''}\nERROR: check timed out after {timeout}s"
    return {
        "cmd": " ".join(cmd),
        "exit": 124 if timed_out else process.returncode,
        "stdout_tail": redact(stdout or "", e)[-1500:],
        "stderr_tail": redact(stderr or "", e)[-800:],
    }


def skipped(name: str, reason: str) -> dict:
    return {
        "cmd": name,
        "exit": 0,
        "stdout_tail": f"SKIPPED: {reason}",
        "stderr_tail": "",
        "skipped": True,
    }


def discover_test_files(root: Path) -> list[Path]:
    """Return the complete, deterministic set of pytest source files."""
    return sorted((root / "tests").rglob("test_*.py"))


def discover_computer_use_test_files(root: Path) -> list[Path]:
    """Return a safe superset of files that can declare computer-use tests.

    Pytest's marker expression remains the authority.  Text discovery only
    narrows collection to files capable of mentioning the marker, so mixed
    core/browser modules remain correctly filtered by ``-m computer_use``.
    """
    return [
        path
        for path in discover_test_files(root)
        if "computer_use" in path.read_text(encoding="utf-8")
    ]


def _test_batch_size(env: dict) -> int:
    raw = str(env.get("ATLAS_AUDIT_TEST_BATCH_SIZE", DEFAULT_TEST_BATCH_SIZE))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TEST_BATCH_SIZE
    if 1 <= value <= MAX_TEST_BATCH_SIZE:
        return value
    return DEFAULT_TEST_BATCH_SIZE


def run_pytest_batches(
    root: Path,
    env: dict,
    files: list[Path],
    *,
    marker: str,
    batch_size: int,
) -> list[dict]:
    """Run pytest in bounded subprocesses and return one check per batch."""
    checks: list[dict] = []
    total = (len(files) + batch_size - 1) // batch_size
    for batch_number, start in enumerate(range(0, len(files), batch_size), start=1):
        batch = files[start : start + batch_size]
        relative = [str(path.relative_to(root)) for path in batch]
        print(
            f"[audit] pytest {marker!r} batch {batch_number}/{total} "
            f"({len(batch)} files)",
            flush=True,
        )
        checks.append(
            run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    *relative,
                    "-q",
                    "--tb=line",
                    "-m",
                    marker,
                ],
                root,
                env,
            )
        )
        print(
            f"[audit] batch {batch_number}/{total} exit={checks[-1]['exit']}",
            flush=True,
        )
    return checks


def smoke_self_audit(root: Path, env: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="atlas-self-audit-smoke-") as tmp_s:
        tmp = Path(tmp_s)
        repo = tmp / "repo"
        home = tmp / "home"
        (repo / "docs").mkdir(parents=True)
        home.mkdir()
        (repo / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
        (repo / "pyproject.toml").write_text(
            "[project]\nname='atlas-self-audit-smoke'\n",
            encoding="utf-8",
        )
        for cmd in (
            ["git", "init", "-b", "main"],
            ["git", "add", "."],
            [
                "git",
                "-c",
                "user.email=audit@example.local",
                "-c",
                "user.name=Atlas Audit",
                "commit",
                "-m",
                "init",
            ],
        ):
            result = subprocess.run(
                cmd, cwd=repo, capture_output=True, text=True, check=False
            )
            if result.returncode != 0:
                return {
                    "cmd": " ".join(cmd),
                    "exit": result.returncode,
                    "stdout_tail": redact(result.stdout or "", env)[-1500:],
                    "stderr_tail": redact(result.stderr or "", env)[-800:],
                }
        return run(
            [
                sys.executable,
                "-m",
                "atlas.interfaces.cli",
                "self-audit",
                "run",
                "--hours",
                "1",
                "--profile",
                "quick",
                "--max-cycles",
                "1",
                "--dry-run",
            ],
            root,
            {**env, "ATLAS_CORE_ROOT": str(repo), "ATLAS_HOME": str(home)},
        )


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    env = {**os.environ, "PYTHONPATH": str(src), "MYPYPATH": str(src)}
    report: dict = {
        "root": str(root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": [],
    }

    batch_size = _test_batch_size(env)
    test_files = discover_test_files(root)
    report["checks"].extend(
        run_pytest_batches(
            root,
            env,
            test_files,
            marker="not computer_use",
            batch_size=batch_size,
        )
    )
    if env.get("ATLAS_AUDIT_COMPUTER_USE") == "1":
        report["checks"].extend(
            run_pytest_batches(
                root,
                env,
                discover_computer_use_test_files(root),
                marker="computer_use",
                batch_size=batch_size,
            )
        )
    else:
        report["checks"].append(
            skipped(
                "pytest -m computer_use",
                "set ATLAS_AUDIT_COMPUTER_USE=1 to run Playwright/browser tests",
            )
        )
    report["checks"].append(
        run([sys.executable, "-m", "mypy", "src/atlas/"], root, env)
    )
    for script in ("gate_i_smoke.py", "gate_h_smoke.py"):
        path = root / "scripts" / script
        if path.exists():
            report["checks"].append(
                run([sys.executable, str(path)], root, env)
            )
    report["checks"].append(smoke_self_audit(root, env))
    report["checks"].append(
        run([sys.executable, str(root / "scripts" / "twin_e2e_smoke.py")], root, env)
    )

    if env.get("ATLAS_AUDIT_LIVE") == "1" and env.get("VPS_HOST"):
        report["checks"].append(
            run(["bash", str(root / "scripts" / "verify_twin_pairing.sh")], root, env)
        )
    else:
        report["checks"].append(
            skipped(
                "scripts/verify_twin_pairing.sh",
                "set ATLAS_AUDIT_LIVE=1 and VPS_HOST for a read-only live pairing check; "
                "provider inference and Telegram delivery are never automatic",
            )
        )

    failed = [c for c in report["checks"] if c["exit"] != 0]
    skipped_count = len([c for c in report["checks"] if c.get("skipped")])
    report["passed"] = len(failed) == 0
    report["failed_count"] = len(failed)
    report["skipped_count"] = skipped_count
    out = root / "docs" / "audit_complete_latest.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "failed": report["failed_count"], "out": str(out)}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
