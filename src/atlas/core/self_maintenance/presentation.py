"""ADR-039 slice 2 — presentación de una propuesta para el humano (HITL).

Formateador puro: convierte una ``McpProposal`` en el texto que el humano ve
antes de apretar el botón (qué / por qué / riesgos / procedencia). **No envía
nada** — el wire al bot y el botón de aprobación son slice 3.
"""

from __future__ import annotations

from atlas.core.self_maintenance.candidate import (
    PROVENANCE_AUTHORITATIVE,
    McpProposal,
)


def format_proposal(proposal: McpProposal) -> str:
    """Renderiza la propuesta como mensaje legible para Telegram (HITL)."""
    lines = [
        f"🔧 Propuesta MCP: {proposal.capability} v{proposal.version}",
        f"id: {proposal.id}  ·  estado: {proposal.status}",
    ]
    if proposal.purpose:
        lines.append(f"\nQué hace: {proposal.purpose}")

    lines.append(f"\nComando: {' '.join(proposal.cmd) if proposal.cmd else '(sin cmd)'}")

    lines.append("\nRiesgos:")
    if proposal.risks:
        lines.extend(f"  • {r}" for r in proposal.risks)
    else:
        lines.append("  • (ninguno reportado)")

    lines.append("\nProcedencia:")
    for ev in proposal.evidence:
        mark = "✓ corrobora" if ev.corroborates else "· señal"
        auth = " (autoritativa)" if ev.provenance == PROVENANCE_AUTHORITATIVE else " (community)"
        lines.append(f"  {mark}{auth}: {ev.url}")

    lines.append("\nNada se ejecuta sin tu aprobación.")
    return "\n".join(lines)
