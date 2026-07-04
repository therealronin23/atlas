"""Atlas Core — Token Budget (técnica #5, patrón Priompt de Cursor).

Recorte binario de bloques de contexto por presupuesto de caracteres: si
el conjunto excede el presupuesto, se descartan los bloques de MENOR
prioridad primero hasta caber.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Block", "fit_to_budget"]


@dataclass(frozen=True)
class Block:
    text: str
    priority: int


def fit_to_budget(blocks: list[Block], *, budget_chars: int) -> str:
    """Devuelve los bloques concatenados que caben en budget_chars,
    priorizando los de mayor prioridad. Si un único bloque excede el
    presupuesto por sí solo, se incluye igual (mejor exceder un poco que
    no dar nada)."""
    if not blocks:
        return ""
    ordered = sorted(blocks, key=lambda b: b.priority, reverse=True)
    kept: list[str] = []
    used = 0
    for block in ordered:
        if used + len(block.text) > budget_chars and kept:
            continue
        kept.append(block.text)
        used += len(block.text)
    return "\n".join(kept)
