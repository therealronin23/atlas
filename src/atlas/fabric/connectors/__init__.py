"""Conectores REALES del Fabric (Fase 15+).

A diferencia de `atlas.fabric.recipes`/`registry` (que describen conectores
declarativamente, mock/sandbox), este subpaquete contiene clientes que sí
hacen red — con cliente propio (stdlib), sin depender del MCP conducido por
Claude, para que Atlas sea autosuficiente. Cero dependencia nueva salvo que
un ADR dedicado lo apruebe explícitamente.
"""

from __future__ import annotations
