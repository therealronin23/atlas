#!/usr/bin/env python3
"""Etapa 2 de ADR-075 — corrida por lotes real sobre candidatos elegibles.

Lee docs/design/mcp_catalog_stage1_triage.jsonl (elegibles) + el catálogo
sembrado (para los campos install/remote_url reales), corre run_stage2a_stdio
/run_stage2b_http sobre una MUESTRA (--limit-stdio/--limit-http, por defecto
modestos -- correr los ~2097 completos son horas reales de reloj, ver
ADR-075). Escribe docs/design/mcp_catalog_stage2_report.jsonl.

    python3 scripts/mcp_stage2_batch.py --limit-stdio 20 --limit-http 40
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from atlas.mcp.candidate_stage2 import run_stage2a_stdio, run_stage2b_http  # noqa: E402
from atlas.mcp.http_mcp_transport import urllib_fetcher_with_headers  # noqa: E402

_TRIAGE = ROOT / "docs" / "design" / "mcp_catalog_stage1_triage.jsonl"
_SEEDED = ROOT / "docs" / "design" / "mcp_catalog_seeded.yaml"
_REPORT = ROOT / "docs" / "design" / "mcp_catalog_stage2_report.jsonl"
_QUARANTINE = ROOT / "workspace" / "mcp" / "quarantine"


def _load_seeded_by_name() -> dict[str, dict]:
    doc = yaml.safe_load(_SEEDED.read_text(encoding="utf-8")) or {}
    entries = {}
    for sector in (doc.get("sectors") or {}).values():
        for e in sector.get("entries") or []:
            entries[e["name"]] = e
    return entries


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-stdio", type=int, default=10)
    ap.add_argument("--limit-http", type=int, default=20)
    ap.add_argument("--per-request-delay", type=float, default=0.3, help="cortesía entre sondeos http a distintos terceros")
    args = ap.parse_args()

    triaged = [json.loads(ln) for ln in _TRIAGE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    by_name = _load_seeded_by_name()
    _QUARANTINE.mkdir(parents=True, exist_ok=True)

    stdio_names = [t["name"] for t in triaged if t["track"] == "stdio" and t["eligible"]][: args.limit_stdio]
    http_names = [t["name"] for t in triaged if t["track"] == "http" and t["eligible"]][: args.limit_http]

    results = []
    for name in stdio_names:
        entry = by_name.get(name, {"name": name})
        r = run_stage2a_stdio(entry, quarantine_root=_QUARANTINE)
        results.append({
            "track": "stdio", "name": name, "completed": r.completed, "stage_reached": r.stage_reached,
            "reason": r.reason, "entrypoint": r.entrypoint_module, "n_findings": len(r.static_findings),
            "worst_severity": r.worst_severity.name,
        })
        print(f"[2A] {name}: completed={r.completed} stage={r.stage_reached} findings={len(r.static_findings)}")

    for name in http_names:
        entry = by_name.get(name, {"name": name})
        r = run_stage2b_http(entry, fetcher=urllib_fetcher_with_headers)
        results.append({
            "track": "http", "name": name, "completed": r.completed, "reason": r.reason, "tool_count": r.tool_count,
        })
        print(f"[2B] {name}: completed={r.completed} tools={r.tool_count} reason={r.reason[:60]}")
        time.sleep(args.per_request_delay)

    with _REPORT.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n_ok = sum(1 for r in results if r["completed"])
    print(f"\n{n_ok}/{len(results)} completados -> {_REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
