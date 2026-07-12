#!/usr/bin/env python3
"""fetch_longmemeval.py — Descarga LongMemEval_S (variante limpia) desde el
dataset público de Hugging Face xiaowu0162/longmemeval-cleaned (MIT, sin
token) al destino que ya usan scripts/eval_longmemeval.py:351 y
src/atlas/core/self_maintenance/benchmark_gate.py:73:
data/longmemeval/longmemeval_s_cleaned.json.

NUNCA descarga la variante _m (longmemeval_m_cleaned.json, ~2.7GB) — solo _s.

Idempotente: si el destino ya existe con el tamaño exacto esperado
(EXPECTED_SIZE_BYTES), no hace nada e imprime que ya está (exit 0).
--force fuerza re-descarga.

Estrategia de descarga (default_fetcher, en orden):
  1. huggingface_hub.hf_hub_download (ya está en el venv, dep transitiva de
     fastembed) — copia/enlaza el fichero cacheado al destino.
  2. Fallback si (1) falla por lo que sea (import, red, etc.): urllib.request
     directo contra la URL resolve/main, con progreso simple por stderr.

La descarga real es inyectable vía el parámetro `fetcher` de ensure_dataset()
para poder testear la lógica de idempotencia/orquestación sin red.

Uso:
    python scripts/fetch_longmemeval.py [--dest RUTA] [--force]
"""

from __future__ import annotations

import argparse
import shutil
import sys
import urllib.request
from pathlib import Path
from typing import Callable

REPO_ID = "xiaowu0162/longmemeval-cleaned"
FILENAME = "longmemeval_s_cleaned.json"
HF_RESOLVE_URL = f"https://huggingface.co/datasets/{REPO_ID}/resolve/main/{FILENAME}"

_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEST = _REPO_ROOT / "data" / "longmemeval" / "longmemeval_s_cleaned.json"

# Tamaño exacto (bytes) del longmemeval_s_cleaned.json publicado — firma de
# idempotencia: si el destino ya tiene este tamaño, no se re-descarga.
EXPECTED_SIZE_BYTES = 277383467

Fetcher = Callable[[Path], None]


def _fetch_via_hf_hub(dest: Path) -> None:
    """Descarga vía huggingface_hub.hf_hub_download y copia/enlaza a `dest`."""
    from huggingface_hub import hf_hub_download

    cached_path = hf_hub_download(repo_id=REPO_ID, filename=FILENAME, repo_type="dataset")
    # El cache de HF entrega un SYMLINK relativo a blobs/ — hardlinkearlo tal
    # cual duplica el symlink (roto fuera del cache). resolve() primero.
    # Bug real 2026-07-10: dest quedó como enlace a ../../blobs/<hash> y el
    # eval moría con FileNotFoundError.
    real_path = Path(cached_path).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    try:
        Path(dest).hardlink_to(real_path)
    except OSError:
        shutil.copyfile(real_path, dest)


def _fetch_via_urllib(dest: Path) -> None:
    """Fallback sin huggingface_hub: descarga HTTP directa con progreso simple."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_dest = dest.with_suffix(dest.suffix + ".part")

    def _report(block_num: int, block_size: int, total_size: int) -> None:
        if total_size <= 0:
            return
        pct = min(100.0, block_num * block_size / total_size * 100)
        print(f"\r  {pct:5.1f}%", end="", file=sys.stderr)

    try:
        urllib.request.urlretrieve(HF_RESOLVE_URL, tmp_dest, reporthook=_report)
    except OSError as exc:
        if tmp_dest.exists():
            tmp_dest.unlink()
        raise RuntimeError(
            f"fallo de red descargando {HF_RESOLVE_URL}: {exc}. "
            "Revisa conectividad, o descarga manual desde "
            f"https://huggingface.co/datasets/{REPO_ID} a {dest}."
        ) from exc
    print(file=sys.stderr)
    tmp_dest.replace(dest)


def default_fetcher(dest: Path) -> None:
    """Intenta huggingface_hub primero; si falla, cae a urllib directo."""
    try:
        _fetch_via_hf_hub(dest)
        return
    except Exception as exc:  # noqa: BLE001 — cualquier fallo cae al fallback
        print(f"huggingface_hub falló ({exc}); probando descarga directa...", file=sys.stderr)
    _fetch_via_urllib(dest)


def ensure_dataset(
    dest: Path = DEFAULT_DEST,
    *,
    force: bool = False,
    fetcher: Fetcher = default_fetcher,
) -> bool:
    """Garantiza que `dest` tenga LongMemEval_S limpio. Devuelve True si
    descargó, False si ya estaba presente (idempotencia por tamaño exacto).

    No traga excepciones de `fetcher`: se propagan tal cual para que el
    llamador decida (el CLI las convierte en exit != 0 con mensaje claro).
    """
    if not force and dest.exists() and dest.stat().st_size == EXPECTED_SIZE_BYTES:
        print(f"ya está: {dest} ({EXPECTED_SIZE_BYTES} bytes) — usa --force para re-descargar")
        return False

    fetcher(dest)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    try:
        downloaded = ensure_dataset(args.dest, force=args.force, fetcher=default_fetcher)
    except Exception as exc:  # noqa: BLE001 — reportar y salir != 0, no traza cruda
        print(f"error descargando LongMemEval_S: {exc}", file=sys.stderr)
        return 1

    if downloaded:
        print(f"descargado: {args.dest} ({args.dest.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
