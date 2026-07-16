#!/usr/bin/env python3
"""Informe F5.1 — % de sugerencias del router realmente usadas.

Cruza ``workspace/mcp/routing_suggestions.jsonl`` (lo que el hook de routing
sugirió; solo hashes de prompt, nunca texto en claro) con el ToolUsageCounter
del tronco (``tool_usage.json`` — invocaciones reales vía trunk_invoke).
Imprime el informe como JSON en stdout.

Uso:
  PYTHONPATH=src python scripts/router_usage_report.py
  PYTHONPATH=src python scripts/router_usage_report.py \\
      --suggestions workspace/mcp/routing_suggestions.jsonl \\
      --usage ~/atlas-mcp/tool_usage.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from atlas.mcp.router_telemetry import read_suggestions, usage_report
from atlas.mcp.tool_usage import ToolUsageCounter


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cruza sugerencias del router con uso real (ToolUsageCounter)"
    )
    parser.add_argument(
        "--repo-root", type=Path, default=Path("."),
        help="Raíz del repo (para el default de --suggestions)",
    )
    parser.add_argument(
        "--suggestions", type=Path, default=None,
        help="JSONL de sugerencias (default: <repo-root>/workspace/mcp/routing_suggestions.jsonl)",
    )
    parser.add_argument(
        "--usage", type=Path, default=None,
        help="tool_usage.json del tronco (default: ~/atlas-mcp/tool_usage.json, el save_dir real)",
    )
    args = parser.parse_args()

    suggestions_path: Path = (
        args.suggestions
        if args.suggestions is not None
        else args.repo_root / "workspace" / "mcp" / "routing_suggestions.jsonl"
    )
    usage_path: Path = (
        args.usage if args.usage is not None else Path.home() / "atlas-mcp" / "tool_usage.json"
    )

    counts: dict[str, dict[str, int]] = {}
    if usage_path.is_file():  # fail-open: sin counter aún, el informe sale con used=0
        counts = ToolUsageCounter(usage_path).counts()

    report = usage_report(read_suggestions(suggestions_path), counts)
    report["suggestions_path"] = str(suggestions_path)
    report["usage_path"] = str(usage_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
