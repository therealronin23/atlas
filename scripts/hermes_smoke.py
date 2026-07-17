#!/usr/bin/env python3
"""Retirado — smoke del canal REST legado de Hermes (HermesRestAdapter).

ADR-070 retiro HermesRestAdapter (ver
docs/decisions/adr/adr_070_retire_hermes_rest_adapter.md): el VPS Hermes REST
esta dado de baja desde mayo 2026 y el canal canonico es el Kanban bridge
(HermesKanbanAdapter, ADR-028) operado por las skills atlas-twin/atlas-audit.
Este script mutaba la cola REST creando y cancelando una tarea contra un
endpoint que ya no existe.

Reemplazo: no hay smoke equivalente para el canal kanban porque su
reachability ya se reporta en `atlas doctor` (check hermes_twin) y en
`atlas reality` (report["hermes"]).
"""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "ERROR: hermes_smoke.py is retired.\n\n"
        "It exercised the legacy Hermes REST channel (HermesRestAdapter), "
        "which was retired in ADR-070 — the VPS REST endpoint no longer "
        "exists. The canonical channel is the Kanban bridge "
        "(HermesKanbanAdapter, ADR-028); check its reachability with "
        "`atlas doctor` (hermes_twin check) or `atlas reality`.\n\n"
        "See docs/decisions/adr/adr_070_retire_hermes_rest_adapter.md.",
        file=sys.stderr,
    )
    return 64


if __name__ == "__main__":
    sys.exit(main())
