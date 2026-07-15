#!/usr/bin/env bash
# SUPERSEDED: configuration and release state now have one idempotent authority.
set -euo pipefail
printf '%s\n' \
  'SUPERSEDED: run install_hermes_agent_vps.sh with a fresh sealed bootstrap.json.' \
  'This legacy entry point intentionally performs no mutation.' >&2
exit 64
