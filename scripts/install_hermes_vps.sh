#!/usr/bin/env bash
# SUPERSEDED: the old REST stub is not Hermes Agent and is not a supported
# deployment target. Historical source remains under docs/archive and git.
set -euo pipefail
printf '%s\n' \
  'SUPERSEDED: this legacy stub installer is intentionally disabled.' \
  'Use deploy_hermes_vps_oneshot.sh or install_hermes_agent_vps.sh with a sealed bootstrap.' >&2
exit 64
