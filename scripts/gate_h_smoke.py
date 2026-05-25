#!/usr/bin/env python3
"""
Gate H smoke — local, no VPS required.

  PYTHONPATH=src python scripts/gate_h_smoke.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def main() -> int:
    os.environ.setdefault("ATLAS_PENDING_HMAC_KEY", "gate-h-smoke-key")
    tmp = Path(tempfile.mkdtemp(prefix="atlas-gate-h-"))
    os.environ["ATLAS_HOME"] = str(tmp)

    from atlas.core.orchestrator import Orchestrator
    from atlas.core.contracts import TaskStatus

    orch = Orchestrator(workspace=tmp)
    print(f"[1/4] Gate H status: {orch.gate_h_status()}")

    task = orch.handle_intent("editor run projects/.atlas/generated :: echo smoke-ok")
    if task.status != TaskStatus.AWAITING_APPROVAL:
        print(f"ERROR: expected awaiting_approval, got {task.status}")
        return 1
    result = orch.approve_pending(task.id, approved=True)
    if result.get("status") != "done":
        print(f"ERROR approve: {result}")
        return 1
    if not task.result.get("gate_h", {}).get("valid"):
        print(f"ERROR gate_h validation: {task.result}")
        return 1
    print("[2/4] generated run + audit OK")

    orch._gate_h.pause_tool("smoke.tool")
    orch2 = Orchestrator(workspace=tmp)
    if not orch2._gate_h.is_tool_paused("smoke.tool"):
        print("ERROR pause persistence")
        return 1
    print("[3/4] pause persistence OK")

    rebuild = orch.rebuild_memory()
    print(f"[4/4] rebuild_memory: {rebuild}")

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print("=== Gate H smoke OK ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
