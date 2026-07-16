#!/usr/bin/env bash
# Guarda barata de daemon inactivo — F4.4 (plan toasty-hatching-pillow.md, F4 — DAEMON).
#
# Cableado en los hooks SessionStart portables de Claude y Codex, por el MISMO
# mecanismo que capability_route_hook: al arrancar una sesión nueva, si
# atlas-core.service lleva > DAEMON_IDLE_GUARD_THRESHOLD_SECONDS (24h por
# defecto) inactivo, imprime UNA línea de aviso a stdout (se inyecta como
# contexto de arranque).
# Si el daemon está activo, o inactivo desde hace menos del umbral, permanece
# en silencio (sin salida, sin ruido en cada sesión).
#
# Por qué esto NO va en el radar de auto-mantenimiento (preflight_gate /
# maintenance_facade): el radar es un consumidor que corre DENTRO del propio
# tick del daemon (self_maintenance). Pedirle al radar que detecte que el
# daemon está muerto es una contradicción — si el daemon no corre, el radar
# tampoco corre, y nunca dispararía el aviso. Este guard vive fuera, en los
# hooks de sesión de los clientes, precisamente porque NO depende de que
# atlas-core.service esté vivo para ejecutarse.
#
# Testabilidad: systemctl se resuelve vía PATH (mockeable) — ver
# tests/test_daemon_idle_guard.py, que antepone un `systemctl` falso al PATH
# en vez de tocar el daemon real. Nunca se hace start/stop/restart aquí.
set -euo pipefail

UNIT="${DAEMON_IDLE_GUARD_UNIT:-atlas-core.service}"
THRESHOLD_SECONDS="${DAEMON_IDLE_GUARD_THRESHOLD_SECONDS:-86400}"

if ! [[ "$THRESHOLD_SECONDS" =~ ^[0-9]+$ ]]; then
  THRESHOLD_SECONDS=86400
fi

if ! command -v systemctl >/dev/null 2>&1; then
  exit 0
fi

active_state="$(systemctl --user is-active "$UNIT" 2>/dev/null || true)"
if [ "$active_state" = "active" ]; then
  exit 0
fi

enabled_state="$(systemctl --user is-enabled "$UNIT" 2>/dev/null || true)"
if [ "$enabled_state" != "enabled" ]; then
  exit 0
fi

inactive_ts_raw="$(systemctl --user show "$UNIT" -p InactiveEnterTimestamp --value 2>/dev/null || true)"
timestamp_source="systemd"
if [ -z "$inactive_ts_raw" ] || [ "$inactive_ts_raw" = "n/a" ]; then
  # `daemon-reload` puede vaciar InactiveEnterTimestamp aunque la unidad enabled
  # lleve días parada. El último evento del journal es una cota conservadora y
  # factual; sin evento seguimos en silencio para no inventar una antigüedad.
  inactive_epoch="$(journalctl --user-unit "$UNIT" -n 1 --no-pager -o short-unix \
    2>/dev/null | awk 'NR == 1 { split($1, parts, "."); print parts[1] }')"
  timestamp_source="journal"
else
  inactive_epoch="$(date -d "$inactive_ts_raw" +%s 2>/dev/null || true)"
fi
if [ -z "$inactive_epoch" ]; then
  exit 0
fi

now_epoch="$(date +%s)"
idle_seconds=$(( now_epoch - inactive_epoch ))

if [ "$idle_seconds" -gt "$THRESHOLD_SECONDS" ]; then
  idle_hours=$(( idle_seconds / 3600 ))
  if [ "$timestamp_source" = "journal" ]; then
    echo "### AVISO: ${UNIT} lleva sin actividad registrada ~${idle_hours}h (última evidencia: journal). Si esperabas el daemon vivo: systemctl --user start ${UNIT}"
  else
    echo "### AVISO: ${UNIT} lleva inactivo ~${idle_hours}h (desde ${inactive_ts_raw}). Si esperabas el daemon vivo: systemctl --user start ${UNIT}"
  fi
fi

exit 0
