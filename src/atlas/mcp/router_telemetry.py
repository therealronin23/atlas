"""
Atlas Core — F5.1/F5.2 (plan toasty-hatching-pillow): telemetría de cierre de
bucle + anti-fatiga del router determinista de capacidades (Pieza 3).

Telemetría (F5.1): cada bloque de sugerencias realmente MOSTRADO se registra
en ``workspace/mcp/routing_suggestions.jsonl`` como una línea JSON
``{ts, prompt_hash, hits, top_score}``. El prompt JAMÁS se persiste en claro —
solo su SHA-256 (basta para dedupe/correlación y no filtra contenido).
``usage_report`` cruza esas sugerencias con el ToolUsageCounter del tronco
(invocaciones reales) → "% de sugerencias realmente usadas". Antes de esto el
router sugería a ciegas: cero registro de qué se sugirió ni de si se usó.

Anti-fatiga (F5.2): estado de cooldown entre turnos en
``workspace/mcp/router_cooldown.json`` — una tool ya sugerida no se repite
durante ``cooldown_turns`` turnos (cada invocación del hook = un turno).
Sin esto el router repetía el mismo bloque en cada prompt (fatiga → el agente
acaba ignorándolo, el gating anti-fatiga era parte del diseño original).

Consumidores: ``scripts/capability_route_hook.py`` (escribe) y
``scripts/router_usage_report.py`` (lee y cruza).
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from atlas.mcp.capability_router import RouteHit

#: Turnos que una tool sugerida permanece en cooldown antes de poder repetirse.
DEFAULT_COOLDOWN_TURNS = 3


def hash_prompt(prompt: str) -> str:
    """SHA-256 hex del prompt (normalizado con strip). Nunca el texto en claro."""
    return hashlib.sha256(prompt.strip().encode("utf-8")).hexdigest()


def append_suggestion(
    path: Path, *, prompt: str, hits: list[RouteHit], ts: float | None = None
) -> None:
    """Registra un bloque de sugerencias mostrado: {ts, prompt_hash, hits,
    top_score}. ``hits`` vacío no escribe nada (no hubo sugerencia). El prompt
    solo entra como hash — JAMÁS en claro."""
    if not hits:
        return
    entry: dict[str, Any] = {
        "ts": time.time() if ts is None else ts,
        "prompt_hash": hash_prompt(prompt),
        "hits": [h.name for h in hits],
        "top_score": max(h.score for h in hits),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_suggestions(path: Path) -> list[dict[str, Any]]:
    """Lee el JSONL de sugerencias. Fichero ausente → []; líneas corruptas se
    saltan (es telemetría, no evidencia — la evidencia va al Merkle)."""
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            out.append(data)
    return out


def _load_state(path: Path) -> dict[str, Any]:
    """Estado de cooldown; corrupto/ausente → {} (fail-open: mejor sugerir de
    más una vez que romper el hook de prompts)."""
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def apply_cooldown(
    hits: list[RouteHit],
    state_path: Path,
    *,
    cooldown_turns: int = DEFAULT_COOLDOWN_TURNS,
) -> list[RouteHit]:
    """Filtra las tools sugeridas hace <= ``cooldown_turns`` turnos y avanza
    el turno (cada llamada = un turno nuevo; el hook corre como proceso
    efímero por prompt, por eso el estado vive en disco).

    Estado: ``{"turn": N, "suggested": {tool: turno_en_que_se_sugirió}}``.
    Solo las tools que SÍ se muestran refrescan su turno; una tool filtrada
    conserva el turno original y reaparece al expirar la ventana.
    """
    state = _load_state(state_path)
    try:
        turn = int(state.get("turn", 0)) + 1
    except (TypeError, ValueError):
        turn = 1
    suggested: dict[str, int] = {}
    raw_suggested = state.get("suggested")
    if isinstance(raw_suggested, dict):
        for key, val in raw_suggested.items():
            if isinstance(val, int):
                suggested[str(key)] = val

    kept: list[RouteHit] = []
    for hit in hits:
        last = suggested.get(hit.name)
        if last is not None and (turn - last) <= cooldown_turns:
            continue  # en cooldown: no repetir
        kept.append(hit)
        suggested[hit.name] = turn

    # Poda: lo que ya salió de la ventana no puede volver a filtrar nada.
    horizon = turn - cooldown_turns
    suggested = {k: v for k, v in suggested.items() if v >= horizon}

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {"turn": turn, "suggested": suggested, "updated_at": time.time()},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return kept


def usage_report(
    suggestions: list[dict[str, Any]],
    usage_counts: dict[str, dict[str, int]],
) -> dict[str, Any]:
    """Cruza sugerencias (JSONL) con uso real (``ToolUsageCounter.counts()``).

    Una sugerencia ``name`` cuenta como usada si alguna key de uso ``k``
    cumple ``k == name`` o ``k.startswith(f"mcp__{name}__")`` (el namespacing
    del registry: las invocaciones vía tronco se registran como
    ``mcp__<server>__<tool>``). Limitación honesta: el counter solo ve
    invocaciones vía el agregador (kind=mcp); una skill sugerida y leída
    directamente no deja rastro ahí todavía — aparecerá con used=0.
    """
    per_tool: dict[str, dict[str, int]] = {}
    for entry in suggestions:
        raw_hits = entry.get("hits")
        if not isinstance(raw_hits, list):
            continue
        for name in raw_hits:
            if not isinstance(name, str):
                continue
            row = per_tool.setdefault(name, {"suggested": 0, "used": 0})
            row["suggested"] += 1

    for name, row in per_tool.items():
        used = 0
        prefix = f"mcp__{name}__"
        for key, origins in usage_counts.items():
            if key == name or key.startswith(prefix):
                used += sum(origins.values())
        row["used"] = used

    tools_suggested = len(per_tool)
    tools_used = sum(1 for row in per_tool.values() if row["used"] > 0)
    percent = round(100.0 * tools_used / tools_suggested, 1) if tools_suggested else 0.0
    return {
        "suggestions_logged": len(suggestions),
        "tools_suggested": tools_suggested,
        "tools_used": tools_used,
        "percent_used": percent,
        "per_tool": per_tool,
    }
