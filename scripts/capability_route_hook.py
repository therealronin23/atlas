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
from collections.abc import Callable
from pathlib import Path
from typing import Any

from atlas.mcp.capability_router import format_routing_block, route_capabilities
from atlas.mcp.catalog import CatalogEntry, load_catalog, load_taxonomy
from atlas.mcp.router_telemetry import (
    DEFAULT_COOLDOWN_TURNS,
    append_suggestion,
    apply_cooldown,
)
from atlas.mcp.workbench_compliance import check_and_maybe_synthesize

# Mismo save_dir que .cursor/mcp.json / el --mcp-config real de la CLI
# ("${userHome}/atlas-mcp"): la raíz del tronco, no del repo -- es donde
# workbench://manifest deja su rastro de consulta cada vez que se lee.
_WORKBENCH_SAVE_DIR = Path.home() / "atlas-mcp"


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


def _build_manifest_json_fn(repo_root: Path, entries: list[CatalogEntry]) -> Callable[[], str]:
    """Construcción PEREZOSA del manifiesto de la mesa de trabajo (catálogo ya
    cargado + lecciones + backlog + memoria) -- solo se invoca cuando
    check_and_maybe_synthesize decide que toca síntesis (primera vez de la
    sesión, ver workbench_compliance.is_synthesis_due). Mismo patrón fail-soft
    por fuente que trunk_server.py: una fuente ausente no tumba las demás."""

    def _build() -> str:
        from atlas.core.lesson_store import LessonStore
        from atlas.core.self_maintenance.backlog import load_backlog
        from atlas.mcp.workbench_resources import workbench_manifest_json

        # LessonStore.__init__ crea el directorio si falta (mkdir parents=True,
        # exist_ok=True) -- no necesita guarda propia; un fallo real aquí
        # (p.ej. permisos) se propaga y lo atrapa build_workbench_synth_fn.
        lesson_store_obj = LessonStore(repo_root / "workspace" / "lessons")

        backlog_items: list[Any] = []
        try:
            backlog_path = repo_root / "docs" / "backlog.yaml"
            if backlog_path.is_file():
                backlog_items = load_backlog(backlog_path)
        except Exception:  # noqa: BLE001
            backlog_items = []

        memory_count = 0
        try:
            memory_db = _WORKBENCH_SAVE_DIR / "memory.db"
            if memory_db.is_file():
                import sqlite3

                conn = sqlite3.connect(str(memory_db))
                try:
                    memory_count = int(conn.execute("SELECT COUNT(*) FROM records").fetchone()[0])
                finally:
                    conn.close()
        except Exception:  # noqa: BLE001
            memory_count = 0

        manifest_json: str = workbench_manifest_json(
            entries, lesson_store_obj, backlog_items, memory_count
        )
        return manifest_json

    return _build


def _build_workbench_synth_fn_safe(
    repo_root: Path, entries: list[CatalogEntry]
) -> Callable[[str], str | None] | None:
    """Compone hub (gemini_free dedicado) + manifiesto perezoso. Si el propio
    import/construcción del hub falla, no hay synth_fn -- check_and_maybe_synthesize
    cae directamente al aviso de texto plano, igual que hoy."""
    try:
        from atlas.core.inference_hub import InferenceHub
        from atlas.mcp.workbench_synthesis import build_workbench_synth_fn

        hub = InferenceHub(mode="auto")
        synth_fn: Callable[[str], str | None] = build_workbench_synth_fn(
            hub, _build_manifest_json_fn(repo_root, entries)
        )
        return synth_fn
    except Exception:  # noqa: BLE001 — nunca bloquea el hook
        return None


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

    # Mesa de trabajo obligatoria (2026-07-23, diseño del operador) + síntesis
    # Gemini de primera-vez-por-sesión (2026-07-25, ver memoria
    # trunk-plan-cooperation-design): si workbench://manifest lleva stale Y es
    # la primera vez que esta sesión lo ve así (is_synthesis_due, cooldown de
    # 6h), se hace UNA llamada real a gemini_free que sintetiza un briefing
    # del manifiesto sobre el prompt actual -- esa llamada cuenta como
    # consulta real y resetea el reloj. Si no toca síntesis, o falla, cae al
    # aviso de texto plano de siempre; el hallazgo queda igualmente registrado
    # en workspace/mcp/workbench_compliance_findings.jsonl. Fail-soft total:
    # check_and_maybe_synthesize nunca lanza. Respeta --no-state (su contrato
    # es "no toca workspace/mcp" — el mismo que cooldown/telemetría).
    workbench_notice = None
    if not args.no_state:
        synth_fn = _build_workbench_synth_fn_safe(repo, entries)
        workbench_notice = check_and_maybe_synthesize(
            consultation_log_path=_WORKBENCH_SAVE_DIR / "workbench_consultations.jsonl",
            findings_path=repo / "workspace" / "mcp" / "workbench_compliance_findings.jsonl",
            prompt=prompt,
            goal=prompt,
            synth_fn=synth_fn,
        )

    combined = "\n\n".join(part for part in (block, workbench_notice) if part)
    if not combined:
        return 0

    if args.cursor_json:
        print(json.dumps({"continue": True, "additional_context": combined}, ensure_ascii=False))
    else:
        print(combined)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
