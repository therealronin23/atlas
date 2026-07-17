#!/usr/bin/env bash
# Hook SessionStart: aviso de frescura del pack de sucesión (B+C, T0.1).
#
# Silencioso mientras el pack siga reflejando sus fuentes — solo habla si
# alguna cambió desde que se generó, o si el pack no existe, para que cada
# driver lo sepa al arrancar sin acordarse de correr `atlas handoff --check`
# (capability routing estructural: decide el hook, no la memoria del modelo).
#
# Criterio deliberadamente distinto al de `atlas handoff --check`: el CLI
# compara head_sha con HEAD (gate duro, útil en CI), pero como aviso de sesión
# saltaría SIEMPRE — el pack se proyecta del árbol de trabajo, así que su
# head_sha es el commit ANTERIOR al que lo publica. Aquí re-hasheamos las
# fuentes que el propio MANIFEST lista en "sources" (ver
# atlas.core.handoff.source_hashes): sin git, sin autorreferencia, sin
# duplicar la lista de fuentes. 03_MEMORIA_CLAVE viene del sustrato (no está
# en git ni se hashea): eso lo cubre regenerar el pack, no este aviso.
#
# Siempre exit 0: un pack viejo es un aviso, jamás bloquea la sesión.
set -uo pipefail

ROOT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
MANIFEST="$ROOT_DIR/docs/handoff/GENERATED/MANIFEST.json"
REGEN="Regenera con: PYTHONPATH=src .venv/bin/python -m atlas.interfaces.cli handoff"

if [[ ! -f "$MANIFEST" ]]; then
  printf '### Pack de sucesión: NUNCA GENERADO — %s\n' "$REGEN"
  exit 0
fi

stale="$(ROOT_DIR="$ROOT_DIR" MANIFEST="$MANIFEST" python3 - <<'PY' 2>/dev/null || echo "__error__"
import hashlib, json, os, pathlib, sys

root = pathlib.Path(os.environ["ROOT_DIR"])
try:
    manifest = json.loads(pathlib.Path(os.environ["MANIFEST"]).read_text(encoding="utf-8"))
    sources = manifest["sources"]
    if not isinstance(sources, dict):
        raise ValueError("sources no es un objeto")
except Exception:
    print("__error__")
    sys.exit(0)

changed = []
for rel, recorded in sources.items():
    path = root / rel
    current = (
        hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "MISSING"
    )
    if current != recorded:
        changed.append(rel)
print(" ".join(changed))
PY
)"

if [[ "$stale" == "__error__" ]]; then
  printf '### Pack de sucesión: MANIFEST sin "sources" o ilegible (¿pack anterior al contrato de frescura?) — %s\n' "$REGEN"
elif [[ -n "$stale" ]]; then
  printf '### Pack de sucesión DESFASADO: cambiaron sus fuentes (%s) — %s\n' "$stale" "$REGEN"
fi

exit 0
