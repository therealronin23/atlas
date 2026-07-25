#!/usr/bin/env python3
"""Manual-only cleanup of legacy MCP ``candidato`` entries.

The default is dry-run.  ``--apply`` is intentionally an explicit, one-time
operator action after the precision pipeline is live.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


def filter_out_candidates(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Copy ``data`` without entries whose status is ``candidato``."""
    removed = 0
    sectors = data.get("sectors", {})
    copied: dict[str, Any] = {}
    for name, block in sectors.items():
        entries = block.get("entries", [])
        kept = [entry for entry in entries if entry.get("status") != "candidato"]
        removed += len(entries) - len(kept)
        copied[name] = {**block, "entries": kept}
    return {**data, "sectors": copied}, removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("classified_path", type=Path)
    parser.add_argument("--apply", action="store_true", help="write the filtered YAML")
    args = parser.parse_args(argv)
    data = yaml.safe_load(args.classified_path.read_text(encoding="utf-8")) or {}
    filtered, removed = filter_out_candidates(data)
    print(f"Candidatos a eliminar: {removed}")
    if args.apply:
        args.classified_path.write_text(yaml.safe_dump(filtered, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print("Aplicado.")
    else:
        print("Dry-run: no se escribió ningún fichero.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
