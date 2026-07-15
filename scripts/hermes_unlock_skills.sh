#!/usr/bin/env bash
# SUPERSEDED: external/community skill auto-install was an unsafe trust bypass.
set -euo pipefail
printf '%s\n' \
  'SUPERSEDED: the pinned provisioner installs only the repository-owned atlas-twin skill.' \
  'This legacy entry point intentionally performs no mutation.' >&2
exit 64
