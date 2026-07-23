#!/usr/bin/env bash
# tmp_cache_sweep.sh — barre cachés efímeras conocidas de /tmp para evitar que
# el tmpfs de 4G se llene (auditoría 2026-07-23: /tmp llegó a 100% en vivo
# durante esta misma sesión, bloqueando Bash con ENOSPC intermitente y
# tumbando un ciclo de self_build_tick con "OSError: No space left on
# device" — ver WORK_LEDGER.md). Solo toca patrones identificables como
# caché regenerable; nunca /tmp/systemd-private-* (pertenece a servicios
# vivos) ni nada fuera de los prefijos listados abajo.
set -euo pipefail

MAX_AGE_DAYS_CLAUDE_SESSIONS="${MAX_AGE_DAYS_CLAUDE_SESSIONS:-2}"

# Sesiones de Claude Code más viejas que N días (scratch efímero por diseño,
# ver CLAUDE.md del harness: "session-specific, isolated from the user's
# project"). find -mtime +N sobre el DIRECTORIO de sesión (no ficheros
# sueltos) para no barrer sesiones activas a medias.
find /tmp/claude-1000 -mindepth 2 -maxdepth 2 -type d -mtime "+${MAX_AGE_DAYS_CLAUDE_SESSIONS}" \
  -exec rm -rf {} + 2>/dev/null || true

# Caché de pytest: regenerable siempre, sin coste de recomputar.
rm -rf /tmp/pytest-of-* 2>/dev/null || true

echo "tmp_cache_sweep: $(df -h /tmp | tail -1)"
