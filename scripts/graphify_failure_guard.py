"""Guard de fallos repetidos de extraccion Graphify (Bug 4, plan F1 2026-07-15).

Un fichero que revienta GRAPHIFY_MAX_OUTPUT_TOKENS en cada corrida se
reintenta para siempre sin este guard. Parsea un log de
run-graphify-quality-pipeline.sh buscando los dos patrones confirmados que
emite graphify.llm (ver .venv/lib/python3.12/site-packages/graphify/llm.py):

  1. "single-file chunk <PATH> truncated at max_completion_tokens" (linea
     1771) -- el path va explicito justo tras "single-file chunk ".
  2. "LLM returned invalid JSON" (linea 876-880) -- el path, si esta
     disponible, va embebido como "source_file":"..." en el JSON parcial de
     la MISMA linea (repr de los primeros 200 chars del raw content).

Acumula un contador por fichero en un counts-file JSON (persistente entre
corridas) y, cuando un fichero llega a FAILURE_THRESHOLD fallos, lo presenta
como candidatura. Nunca cambia cobertura semantica por defecto: modificar
.graphifyignore requiere ``--apply-ignore`` explicito y una ruta relativa
segura. La salida del LLM no es autoridad para excluir fuentes.

Scoping por marcador de corrida: run-graphify-quality-pipeline.sh (Tarea 6
del mismo plan) escribe el log en modo append y marca el inicio de cada
corrida con una linea "--- run started ...". Si este guard reescaneara el
fichero completo en cada invocacion, los fallos de corridas anteriores (ya
contados) se sumarian de nuevo cada vez -- el mismo problema que el Bug 3 del
monitor. Por eso, si el log contiene una o mas cabeceras, solo se escanea el
contenido posterior a la ULTIMA cabecera. Logs sin cabecera (p.ej. en tests
aislados) se escanean completos.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path, PurePosixPath

FAILURE_THRESHOLD = 3
RUN_STARTED_MARKER = "--- run started"

_TRUNCATED_RE = re.compile(r"single-file chunk (\S+) truncated at max_completion_tokens")
_INVALID_JSON_MARKER = "LLM returned invalid JSON"
_SOURCE_FILE_RE = re.compile(r'"source_file"\s*:\s*"([^"]*)"')


def _relevant_lines(log_text: str) -> list[str]:
    """Devuelve las lineas a escanear: solo las posteriores a la ULTIMA
    cabecera "--- run started" si hay alguna, o el fichero completo si no."""
    lines = log_text.splitlines()
    last_marker_idx = None
    for i, line in enumerate(lines):
        if line.startswith(RUN_STARTED_MARKER):
            last_marker_idx = i
    if last_marker_idx is not None:
        return lines[last_marker_idx + 1 :]
    return lines


def scan_log(log_path: Path) -> dict[str, int]:
    """Cuenta fallos nuevos por fichero fuente en este log (o en la porcion
    posterior al ultimo marcador de corrida). No lee ningun estado previo."""
    if not log_path.exists():
        return {}
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    counts: dict[str, int] = {}
    for line in _relevant_lines(log_text):
        truncated_match = _TRUNCATED_RE.search(line)
        if truncated_match:
            path = truncated_match.group(1)
            counts[path] = counts.get(path, 0) + 1
            continue
        if _INVALID_JSON_MARKER in line:
            for source_match in _SOURCE_FILE_RE.finditer(line):
                path = source_match.group(1)
                if path:
                    counts[path] = counts.get(path, 0) + 1
    return counts


def _load_counts(counts_file: Path) -> dict[str, int]:
    if not counts_file.exists():
        return {}
    try:
        data = json.loads(counts_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): int(v) for k, v in data.items()}


def _write_counts(counts_file: Path, counts: dict[str, int]) -> None:
    counts_file.parent.mkdir(parents=True, exist_ok=True)
    counts_file.write_text(json.dumps(counts, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def merge_counts(counts_file: Path, new_counts: dict[str, int]) -> dict[str, int]:
    """Suma new_counts sobre el estado persistido y escribe el resultado."""
    total = _load_counts(counts_file)
    for path, delta in new_counts.items():
        total[path] = total.get(path, 0) + delta
    _write_counts(counts_file, total)
    return total


def _ignored_paths(ignore_file: Path) -> set[str]:
    if not ignore_file.exists():
        return set()
    paths = set()
    for raw in ignore_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        paths.add(line)
    return paths


def _append_to_ignore(ignore_file: Path, path: str, *, count: int) -> None:
    existing = ignore_file.read_text(encoding="utf-8") if ignore_file.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    existing += f"\n# auto: failure_guard ({count} fallos de extraccion acumulados)\n{path}\n"
    ignore_file.write_text(existing, encoding="utf-8")


def _safe_ignore_path(path: str) -> bool:
    """Accept only inert, repository-relative Graphify ignore entries."""
    if not path or path[0] in {"#", "!"} or "\\" in path:
        return False
    if any(ord(character) < 32 for character in path):
        return False
    candidate = PurePosixPath(path)
    return not candidate.is_absolute() and all(
        part not in {"", ".", ".."} for part in candidate.parts
    )


def apply_threshold(ignore_file: Path, total_counts: dict[str, int]) -> list[str]:
    """Anade a ignore_file (idempotente) cada fichero que cruzo el umbral.
    Devuelve la lista de ficheros recien anadidos en esta llamada."""
    already_ignored = _ignored_paths(ignore_file)
    newly_added = []
    for path, count in sorted(total_counts.items()):
        if (
            count >= FAILURE_THRESHOLD
            and path not in already_ignored
            and _safe_ignore_path(path)
        ):
            _append_to_ignore(ignore_file, path, count=count)
            already_ignored.add(path)
            newly_added.append(path)
    return newly_added


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_path", help="Log de run-graphify-quality-pipeline.sh a escanear")
    parser.add_argument(
        "--ignore-file",
        default=".graphifyignore",
        help="Fichero .graphifyignore a actualizar (default: .graphifyignore)",
    )
    parser.add_argument(
        "--counts-file",
        default="graphify-out/.graphify_failure_counts.json",
        help="Fichero JSON de contadores persistentes por fichero",
    )
    parser.add_argument(
        "--apply-ignore",
        action="store_true",
        help=(
            "Aplicar candidaturas seguras a .graphifyignore; por defecto solo "
            "se informan"
        ),
    )
    args = parser.parse_args(argv)

    log_path = Path(args.log_path)
    ignore_file = Path(args.ignore_file)
    counts_file = Path(args.counts_file)

    new_counts = scan_log(log_path)
    total_counts = merge_counts(counts_file, new_counts)
    threshold_paths = [
        path
        for path, count in sorted(total_counts.items())
        if count >= FAILURE_THRESHOLD
    ]
    unsafe_paths = [path for path in threshold_paths if not _safe_ignore_path(path)]
    newly_added = (
        apply_threshold(ignore_file, total_counts) if args.apply_ignore else []
    )

    for path in newly_added:
        print(f"[failure_guard] {path} cruzo el umbral de {FAILURE_THRESHOLD} fallos -> anadido a {ignore_file}")
    for path in unsafe_paths:
        print(f"[failure_guard] unsafe ignore candidate rejected: {path!r}")
    if not args.apply_ignore:
        for path in threshold_paths:
            if _safe_ignore_path(path):
                print(
                    f"[failure_guard] candidate only: {path} has "
                    f"{total_counts[path]} accumulated extraction failures; "
                    "review before using --apply-ignore"
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
