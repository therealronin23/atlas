#!/usr/bin/env python3
"""Gate I smoke — health report + service start/stop."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    os.environ.setdefault("ATLAS_PENDING_HMAC_KEY", "gate-i-smoke-key")
    tmp = Path(tempfile.mkdtemp(prefix="atlas-gate-i-"))
    os.environ["ATLAS_HOME"] = str(tmp / "atlas")

    from atlas.core.orchestrator import Orchestrator
    from atlas.runtime.service_runner import AtlasServiceRunner

    orch = Orchestrator(workspace=tmp / "atlas")
    health = orch.health_report()
    assert health["version"]
    assert "merkle_chain_ok" in health

    runner = AtlasServiceRunner(orch)
    runner.start()
    assert runner._running
    runner.stop()

    print("gate_i_smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
