#!/usr/bin/env python3
"""Hook UserPromptSubmit / beforeSubmitPrompt — routing determinista (Pieza 3).

Lee JSON de stdin (prompt del usuario), enruta contra el catálogo graduado e
imprime contexto adicional para el agente.

Uso manual:
  echo '{"prompt":"revisar código react"}' | PYTHONPATH=src python scripts/capability_route_hook.py
  PYTHONPATH=src python scripts/capability_route_hook.py --prompt "tests pytest"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from atlas.mcp.capability_router import format_routing_block, route_capabilities
from atlas.mcp.catalog import CatalogEntry, load_catalog, load_taxonomy
from atlas.mcp.router_telemetry import (
    DEFAULT_COOLDOWN_TURNS,
    append_suggestion,
    apply_cooldown,
)


def _extract_prompt(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if not isinstance(data, dict):
        return str(data)
    for key in ("prompt", "userPrompt", "user_prompt", "message", "text", "content"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _load_entries(repo_root: Path) -> tuple[list[CatalogEntry], dict[str, Any]]:
    catalog_path = repo_root / "docs" / "design" / "mcp_catalog.yaml"
    entries = load_catalog(catalog_path)
    taxonomy = load_taxonomy(catalog_path)
    classified = repo_root / "docs" / "design" / "mcp_catalog_classified.yaml"
    if classified.is_file():
        entries = entries + load_catalog(classified)
    return entries, taxonomy


def main() -> int:
    parser = argparse.ArgumentParser(description="Routing determinista de capacidades (Pieza 3)")
    parser.add_argument("--prompt", default="", help="Prompt (alternativa a stdin JSON)")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--cursor-json",
        action="store_true",
        help="Salida JSON para Cursor beforeSubmitPrompt",
    )
    parser.add_argument(
        "--cooldown-turns",
        type=int,
        default=DEFAULT_COOLDOWN_TURNS,
        help="F5.2: turnos sin repetir una tool ya sugerida",
    )
    parser.add_argument(
        "--no-state",
        action="store_true",
        help="Salta cooldown y telemetría (debug manual; no toca workspace/mcp)",
    )
    args = parser.parse_args()

    prompt = args.prompt.strip() or _extract_prompt(sys.stdin.read())
    if not prompt:
        return 0

    repo = args.repo_root.resolve()
    entries, taxonomy = _load_entries(repo)
    hits = route_capabilities(prompt, entries, taxonomy, limit=args.limit)

    if not args.no_state:
        # F5.2 anti-fatiga + F5.1 telemetría. Fail-soft: el estado/registro
        # JAMÁS rompe el hook de prompts (peor caso: sugerencia repetida y
        # sin telemetría, nunca un prompt bloqueado).
        state_dir = repo / "workspace" / "mcp"
        try:
            hits = apply_cooldown(
                hits,
                state_dir / "router_cooldown.json",
                cooldown_turns=args.cooldown_turns,
            )
            # Se registra SOLO lo realmente mostrado tras el cooldown (hash del
            # prompt, nunca el texto): es lo que mide el cierre de bucle.
            append_suggestion(
                state_dir / "routing_suggestions.jsonl", prompt=prompt, hits=hits
            )
        except Exception:  # noqa: BLE001 — telemetría, nunca bloquea el hook
            pass

    block = format_routing_block(hits)
    if not block:
        return 0

    if args.cursor_json:
        print(json.dumps({"continue": True, "additional_context": block}, ensure_ascii=False))
    else:
        print(block)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
