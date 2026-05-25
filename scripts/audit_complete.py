#!/usr/bin/env python3
"""Auditoria completa ejecutable — pytest, mypy, smokes, conteos."""

from __future__ import annotations

import json
import os
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


def redact(text: str, env: dict) -> str:
    redacted = text
    for key in SENSITIVE_ENV_KEYS:
        value = str(env.get(key, "")).strip()
        if value:
            redacted = redacted.replace(value, f"***{key}***")
    return redacted


def run(cmd: list[str], cwd: Path, env: dict | None = None) -> dict:
    e = {**os.environ, **(env or {})}
    r = subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True, check=False)
    return {
        "cmd": " ".join(cmd),
        "exit": r.returncode,
        "stdout_tail": redact(r.stdout or "", e)[-1500:],
        "stderr_tail": redact(r.stderr or "", e)[-800:],
    }


def skipped(name: str, reason: str) -> dict:
    return {
        "cmd": name,
        "exit": 0,
        "stdout_tail": f"SKIPPED: {reason}",
        "stderr_tail": "",
        "skipped": True,
    }


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

    report["checks"].append(
        run([sys.executable, "-m", "pytest", "tests/", "-q", "-m", "not computer_use"], root, env)
    )
    if env.get("ATLAS_AUDIT_COMPUTER_USE") == "1":
        report["checks"].append(
            run([sys.executable, "-m", "pytest", "tests/", "-q", "-m", "computer_use"], root, env)
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

    if env.get("ATLAS_AUDIT_LIVE") == "1":
        report["checks"].append(
            run([sys.executable, str(root / "scripts" / "operational_smoke.py")], root, env)
        )
    else:
        report["checks"].append(
            skipped(
                "scripts/operational_smoke.py",
                "set ATLAS_AUDIT_LIVE=1 and load .env to run live Hermes/Telegram smoke",
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
