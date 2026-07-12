#!/usr/bin/env bash
# Daemon Ollama de USUARIO, solo-CPU, en 127.0.0.1:11435 (start|stop|status|logs).
#
# Por qué existe: el servicio ollama de sistema (11434) crashea en esta máquina
# porque el runner CUDA moderno no soporta la GTX 960M (Maxwell) — "signal
# arrived during cgo execution" al cargar cualquier modelo. En CPU funciona.
# El proveedor `ollama_local` de Atlas apunta a 11435 (inference_hub.py).
#
# Fix permanente alternativo (requiere sudo, deja el servicio de sistema útil):
#   sudo systemctl edit ollama
#     [Service]
#     Environment="CUDA_VISIBLE_DEVICES="
#   sudo systemctl restart ollama
# ...y entonces devolver base_url a 11434 y retirar este script.
set -euo pipefail

HOST="127.0.0.1:11435"
LOG="${HOME}/proyectos/atlas-core/logs/ollama_cpu.log"
PIDFILE="${HOME}/.ollama/ollama_cpu.pid"

case "${1:-status}" in
  start)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "ya corriendo (pid $(cat "$PIDFILE"))"; exit 0
    fi
    OLLAMA_HOST="$HOST" CUDA_VISIBLE_DEVICES="" nohup ollama serve >> "$LOG" 2>&1 &
    echo $! > "$PIDFILE"
    echo "arrancado en $HOST (pid $!)"
    ;;
  stop)
    [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null && rm -f "$PIDFILE" \
      && echo "parado" || echo "no corría"
    ;;
  status)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "corriendo (pid $(cat "$PIDFILE")) en $HOST"
      OLLAMA_HOST="$HOST" ollama list 2>/dev/null | head -5
    else
      echo "parado"
    fi
    ;;
  logs) tail -30 "$LOG" ;;
  *) echo "uso: $0 start|stop|status|logs"; exit 1 ;;
esac
