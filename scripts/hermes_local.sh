#!/usr/bin/env bash
# Retirado — takeover local del canal REST legado de Hermes (ADR-070).
#
# Este script gestionaba el ciclo de vida (start/stop/status/logs) de
# scripts/hermes_agent_stub/agent.py, un servidor REST local compatible con
# HermesRestAdapter. ADR-070 retiró el adapter y su stub: el canal canónico
# es el Kanban bridge (HermesKanbanAdapter, ADR-028) con
# HERMES_KANBAN_TRANSPORT=local.
# Ver docs/decisions/adr/adr_070_retire_hermes_rest_adapter.md.
set -euo pipefail

cat >&2 <<'EOF'
ERROR: hermes_local.sh is retired (exit 64).

It managed the local Hermes REST stub (scripts/hermes_agent_stub/), removed
in ADR-070 together with HermesRestAdapter. For local Hermes delegation use
the Kanban transport: HERMES_KANBAN_TRANSPORT=local (canonical channel,
ADR-028). See docs/decisions/adr/adr_070_retire_hermes_rest_adapter.md.
EOF
exit 64
