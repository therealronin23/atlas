"""Atlas Core — History Compactor (técnica #21, patrón Codex CLI).

Compacta el historial de errores de iteraciones anteriores: el más
reciente se mantiene completo, los anteriores se truncan.
"""

from __future__ import annotations

__all__ = ["compact_history"]


def compact_history(entries: list[str], *, budget_chars: int) -> str:
    """Devuelve el historial compactado: el ÚLTIMO entry completo, los
    anteriores truncados a lo que quepa en el presupuesto restante, con
    marcador '[...] (truncado)' si se recortaron."""
    if not entries:
        return ""
    if len(entries) == 1:
        return entries[0]
    recent = entries[-1]
    older = entries[:-1]
    older_joined = "\n---\n".join(older)
    remaining = budget_chars - len(recent)
    if remaining > 0 and len(older_joined) <= remaining:
        return older_joined + "\n---\n" + recent
    if remaining <= 0:
        return recent
    truncated = older_joined[: max(0, remaining - 20)] + "\n[...] (truncado)\n"
    return truncated + "---\n" + recent
