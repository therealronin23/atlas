#!/usr/bin/env python3
"""Etapa 1 de ADR-075 — pre-screen estático read-only sobre el catálogo sembrado.

Sin descarga, sin ejecución. Lee docs/design/mcp_catalog_seeded.yaml (NUNCA lo
muta) y escribe docs/design/mcp_catalog_stage1_triage.jsonl con, por candidato:
routing por transporte (stdio/http/unknown) + severidad de tool-poisoning en la
descripción. Ver docs/decisions/adr/adr_075_remote_mcp_continuous_vetting.md.

    python3 scripts/mcp_stage1_triage.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from atlas.mcp.candidate_triage import run_stage1_triage  # noqa: E402

_SEEDED = ROOT / "docs" / "design" / "mcp_catalog_seeded.yaml"
_REPORT = ROOT / "docs" / "design" / "mcp_catalog_stage1_triage.jsonl"


def main() -> int:
    summary = run_stage1_triage(_SEEDED, _REPORT)
    print(f"etapa 1 sobre {summary['total']} candidatos -> {_REPORT.relative_to(ROOT)}")
    print(f"  elegibles (candidato->metadata-cleared): {summary['eligible']}")
    print(f"  pending_review (transporte ambiguo o inyección MAJOR+): {summary['pending_review']}")
    print(f"  pista stdio: {summary['track_stdio']}  |  pista http: {summary['track_http']}  |  unknown: {summary['track_unknown']}")
    print(f"  inyección MAJOR o peor: {summary['injection_major_or_worse']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
