"""Prompt preflight built from atlas-trunk metadata.

The MCP server exposes ``trunk_prepare`` to external clients. Internal coding
harnesses reuse the same pure ranking logic directly so they do not need to
spawn a nested MCP client just to build their prompt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_trunk_preflight_section(repo_root: Path, goal: str, *, limit: int = 6) -> str:
    """Return a compact markdown section for agent prompts.

    Fail-open by design: preflight context should improve tool selection, never
    prevent an otherwise valid coding task from running.
    """
    try:
        from atlas.mcp.catalog import load_catalog, load_taxonomy
        from atlas.mcp.trunk_prepare import prepare_task_context

        catalog_path = repo_root / "docs" / "design" / "mcp_catalog.yaml"
        if not catalog_path.is_file():
            return ""
        catalog = load_catalog(catalog_path)
        classified = repo_root / "docs" / "design" / "mcp_catalog_classified.yaml"
        if classified.is_file():
            catalog = catalog + load_catalog(classified)
        packet = prepare_task_context(
            catalog,
            load_taxonomy(catalog_path),
            goal,
            limit=limit,
            workbench_available=True,
        )
    except Exception:  # noqa: BLE001
        return ""
    return format_trunk_preflight_section(packet)


def format_trunk_preflight_section(packet: dict[str, Any]) -> str:
    rows = packet.get("recommended") or []
    if not isinstance(rows, list) or not rows:
        return ""
    lines = [
        "## Trunk preflight",
        "Antes de editar, usa este paquete mínimo de contexto/capacidades. "
        "No instales ni conectes candidatos sin consentimiento explícito.",
    ]
    resources = packet.get("resources") or []
    if isinstance(resources, list) and resources:
        lines.append("Resources sugeridos: " + ", ".join(str(r) for r in resources[:4]))
    lines.append("Recomendaciones:")
    for row in rows[:6]:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status", ""))
        usable = "usable" if row.get("usable_now") else "candidate-only"
        sector = str(row.get("sector", ""))
        purpose = str(row.get("purpose", ""))[:140]
        lines.append(
            f"- {row.get('name')} [{row.get('kind')}/{status}/{usable}, sector={sector}]: {purpose}"
        )
    missing = packet.get("missing") or []
    if isinstance(missing, list) and missing:
        lines.append("Pendiente/no automático:")
        for item in missing[:4]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('name')}: {item.get('reason')}")
    return "\n".join(lines) + "\n\n"
