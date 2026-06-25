#!/usr/bin/env python3
"""Enriquece las entradas sembradas del catálogo con metadatos de su fuente.

Pieza 1 del plan de "capacidades usables":
  - Resuelve el tipo de fuente de cada entrada (github / npm).
  - Aplica enrich_entry con el fetcher real.
  - Reporta: enriquecidos / sin-metadatos / fuente-caída.
  - Reescribe los YAML sembrados con los campos nuevos.

Modo --offline: solo reporta (no hace red, no reescribe).

Fuente caída (network error, rate-limit) se aísla: no aborta el resto.
status NUNCA se toca (invariante Pieza 1).

Uso:
    python3 scripts/mcp_enrich.py [--offline] [--limit N] [--source github|npm]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from atlas.mcp.enrichment import (  # noqa: E402
    EnrichmentFetcher,
    GithubEnrichment,
    NpmEnrichment,
    enrich_entry,
)


# ---------------------------------------------------------------------------
# Resolución de fuente
# ---------------------------------------------------------------------------

_GH_RE = re.compile(r"^[a-zA-Z0-9_.\-]+/[a-zA-Z0-9_.\-]+$")
_NPM_RE = re.compile(r"^(@[a-zA-Z0-9\-_]+/)?[a-zA-Z0-9\-_.]+$")


def _resolve_fetcher(
    source: str,
    *,
    github_fetcher: GithubEnrichment,
    npm_fetcher: NpmEnrichment,
    only: str | None,
) -> tuple[EnrichmentFetcher, str] | None:
    """Devuelve (fetcher, tipo) o None si la fuente no es resoluble."""
    if not source:
        return None
    if only in (None, "github") and _GH_RE.match(source):
        return github_fetcher, "github"
    if only in (None, "npm") and _NPM_RE.match(source) and "npm" in source.lower():
        return npm_fetcher, "npm"
    return None


# ---------------------------------------------------------------------------
# Carga y reescritura de YAML
# ---------------------------------------------------------------------------


def _seeded_files() -> list[Path]:
    d = ROOT / "docs" / "design"
    return sorted(set(d.glob("*seeded*.yaml")) | set((d / "seeded").glob("*.yaml")))


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _save_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="Solo reporta; no hace red ni reescribe.")
    parser.add_argument("--limit", type=int, default=0, help="Procesar máximo N entradas (0=todas).")
    parser.add_argument("--source", choices=["github", "npm"], default=None, help="Filtrar por tipo de fuente.")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay entre peticiones (seg). Default: 0.5.")
    args = parser.parse_args(argv)

    # Fetchers reales (se comparten entre todas las entradas)
    github_fetcher = GithubEnrichment()
    npm_fetcher = NpmEnrichment()

    # Contadores
    counts: Counter[str] = Counter()
    errors_by_source: Counter[str] = Counter()
    isolated_sources: set[str] = set()

    total_processed = 0

    files = _seeded_files()
    if not files:
        print("No se encontraron archivos seeded.", file=sys.stderr)
        return 1

    for fpath in files:
        try:
            data = _load_yaml(fpath)
        except Exception as exc:
            print(f"  [ERROR] No se pudo leer {fpath.name}: {exc}", file=sys.stderr)
            counts["error_file"] += 1
            continue

        modified = False

        for sec_id, block in (data.get("sectors") or {}).items():
            for entry in (block or {}).get("entries", []) or []:
                if args.limit and total_processed >= args.limit:
                    break

                source = str(entry.get("source") or "")
                name = str(entry.get("name") or "")

                # ¿fuente ya aislada? → saltar
                if source in isolated_sources:
                    counts["aislado"] += 1
                    continue

                resolution = _resolve_fetcher(
                    source,
                    github_fetcher=github_fetcher,
                    npm_fetcher=npm_fetcher,
                    only=args.source,
                )
                if resolution is None:
                    counts["deuda"] += 1
                    continue

                fetcher_instance, src_type = resolution
                total_processed += 1

                if args.offline:
                    print(f"  [dry-run] {src_type}:{name} (source={source})")
                    counts["dry_run"] += 1
                    continue

                # Retraso entre peticiones para no disparar rate-limit
                if total_processed > 1:
                    time.sleep(args.delay)

                try:
                    enriched = enrich_entry(entry, fetcher_instance)
                except Exception as exc:
                    # Fuente caída → aislar, no abortar el resto
                    isolated_sources.add(source)
                    errors_by_source[source] += 1
                    print(
                        f"  [AISLADO] {src_type}:{name} source={source!r} → {exc}",
                        file=sys.stderr,
                    )
                    counts["aislado"] += 1
                    continue

                if enriched.get("purpose") and not entry.get("purpose"):
                    # Entrada efectivamente enriquecida
                    counts["enriquecido"] += 1
                    # status (y demás ejes) jamás se tocan: el filtro solo deja pasar
                    # purpose/purpose_claimed/signal (o claves nuevas que no existían).
                    entry.update({k: v for k, v in enriched.items() if k not in entry or k in ("purpose", "purpose_claimed", "signal")})
                    modified = True
                    print(f"  [OK] {src_type}:{name} — {enriched.get('purpose', '')[:60]!r}")
                else:
                    counts["sin_metadatos"] += 1

            if args.limit and total_processed >= args.limit:
                break

        if modified and not args.offline:
            try:
                _save_yaml(fpath, data)
                print(f"  [REESCRITO] {fpath.relative_to(ROOT)}")
            except Exception as exc:
                print(f"  [ERROR] No se pudo reescribir {fpath.name}: {exc}", file=sys.stderr)
                counts["error_file"] += 1

    # Reporte final
    print("\n=== Reporte de enriquecimiento ===")
    print(f"  Enriquecidos   : {counts['enriquecido']}")
    print(f"  Sin metadatos  : {counts['sin_metadatos']}")
    print(f"  Fuente aislada : {counts['aislado']}")
    print(f"  Deuda (no res.): {counts['deuda']}")
    if args.offline:
        print(f"  Dry-run        : {counts['dry_run']}")
    if isolated_sources:
        print(f"\n  Fuentes aisladas ({len(isolated_sources)}):")
        for src in sorted(isolated_sources):
            print(f"    - {src} ({errors_by_source[src]} errores)")
    if args.offline:
        print("\n  [offline] No se hicieron peticiones ni se reescribió nada.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
