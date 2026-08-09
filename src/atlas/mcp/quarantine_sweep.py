"""Retención de la cuarentena MCP: material de terceros con fecha de caducidad.

`workspace/mcp/quarantine/` acumulaba 583 MB de código descargado por el
pipeline de vetting (ADR-075/076): 207 candidatos, uno solo de 393 MB. Medido
el 2026-08-09, todos con mtime entre 14 y 30 días y ninguno tocado desde — la
campaña de julio, terminada.

No tenía dueño en el código. El `quarantine` de `mcp/registry.py` es un set en
memoria con nombres de servidor; el directorio de disco no lo gestionaba nadie
y no tenía política de retención. Código de terceros sin caducidad es deuda de
disco y superficie de riesgo a la vez.

Se reusa el idioma de `SelfBuildRunner.sweep_stale_worktrees`: TTL por mtime, y
un candidato EN VUELO tiene mtime fresco y queda protegido.

**mtime y no atime.** Con `relatime` —el defecto en Linux— el tiempo de acceso
no se actualiza de forma fiable: los 207 candidatos aparecían "accedidos hace
horas" sólo porque un `du` los había recorrido. mtime responde a "cuándo se
escribió esto por última vez", que es la pregunta real.

Lo descargado es REGENERABLE: el veredicto de cada candidato vive en el
catálogo, no en el tarball. Barrer no pierde conocimiento, sólo bytes.
"""

from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["QuarantineSweep", "sweep_quarantine", "DEFAULT_TTL_DAYS"]

logger = logging.getLogger(__name__)

#: Conservador a propósito: el vetting de un candidato dura minutos, no
#: semanas, así que 30 días sin escribir significa "nadie va a volver".
DEFAULT_TTL_DAYS = 30.0


@dataclass(frozen=True)
class QuarantineSweep:
    removed: list[str] = field(default_factory=list)
    freed_bytes: int = 0
    inspected: int = 0
    dry_run: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "removed": list(self.removed),
            "freed_bytes": self.freed_bytes,
            "inspected": self.inspected,
            "dry_run": self.dry_run,
            "reason": self.reason,
        }


def _size_of(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() and not item.is_symlink():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def sweep_quarantine(
    quarantine_dir: Path,
    *,
    ttl_days: float = DEFAULT_TTL_DAYS,
    dry_run: bool = False,
) -> QuarantineSweep:
    """Retira candidatos sin escribir desde hace `ttl_days`. Nunca lanza."""
    root = Path(quarantine_dir)
    if not root.is_dir():
        return QuarantineSweep(reason=f"cuarentena ausente: {root}")

    cutoff = time.time() - ttl_days * 86400
    removed: list[str] = []
    freed = 0
    inspected = 0
    for entry in sorted(root.iterdir()):
        # Sólo directorios hijos DIRECTOS. Un fichero suelto en la raíz de la
        # cuarentena es estado del pipeline, no un candidato descargado.
        if entry.is_symlink():
            # Un symlink viejo no puede arrastrar a su destino: se descarta el
            # enlace del barrido en vez de seguirlo.
            continue
        if not entry.is_dir():
            continue
        inspected += 1
        try:
            if entry.stat().st_mtime >= cutoff:
                continue
        except OSError:
            continue
        size = _size_of(entry)
        if not dry_run:
            try:
                shutil.rmtree(entry)
            except OSError as exc:
                logger.warning("no se pudo retirar %s: %s", entry.name, exc)
                continue
        removed.append(entry.name)
        freed += size

    return QuarantineSweep(
        removed=removed,
        freed_bytes=freed,
        inspected=inspected,
        dry_run=dry_run,
        reason=(
            f"{len(removed)} de {inspected} candidatos sin escribir en "
            f"{ttl_days:g} días ({freed / 1024 / 1024:.0f} MB)"
        ),
    )


def _main(argv: list[str] | None = None) -> int:  # pragma: no cover — entrypoint
    import argparse
    import json
    import os

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ttl-days", type=float, default=DEFAULT_TTL_DAYS)
    parser.add_argument("--apply", action="store_true", help="sin esto, dry-run")
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path(os.environ.get("ATLAS_HOME", "~/atlas")).expanduser()
        / "workspace" / "mcp" / "quarantine",
    )
    args = parser.parse_args(argv)
    result = sweep_quarantine(args.dir, ttl_days=args.ttl_days, dry_run=not args.apply)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False)[:2000])
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
