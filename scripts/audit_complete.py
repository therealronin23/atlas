#!/usr/bin/env python3
"""Auditoria completa ejecutable — pytest, mypy, smokes, conteos."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path, env: dict | None = None) -> dict:
    e = {**os.environ, **(env or {})}
    r = subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True, check=False)
    return {
        "cmd": " ".join(cmd),
        "exit": r.returncode,
        "stdout_tail": (r.stdout or "")[-1500:],
        "stderr_tail": (r.stderr or "")[-800:],
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    env = {"PYTHONPATH": str(src)}
    report: dict = {"root": str(root), "checks": []}

    report["checks"].append(
        run([sys.executable, "-m", "pytest", "tests/", "-q", "-m", "not computer_use"], root, env)
    )
    report["checks"].append(
        run([sys.executable, "-m", "mypy", "src/atlas/"], root, {**env, "MYPYPATH": str(src)})
    )
    for script in ("gate_i_smoke.py", "gate_h_smoke.py"):
        path = root / "scripts" / script
        if path.exists():
            report["checks"].append(
                run([sys.executable, str(path)], root, env)
            )

    failed = [c for c in report["checks"] if c["exit"] != 0]
    report["passed"] = len(failed) == 0
    report["failed_count"] = len(failed)
    out = root / "docs" / "audit_complete_latest.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "failed": report["failed_count"], "out": str(out)}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
