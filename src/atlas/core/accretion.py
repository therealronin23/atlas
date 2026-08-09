"""Ratio de acreción: cuánto entra por cada línea que sale.

Causa nº2 del postmortem de la auditoría 2026-08-06, y la única que seguía sin
tocarse. Medida sobre este repo:

    60 días  ->  14,7:1   (+149.753 / -10.192)
    30 días  ->  24,3:1   (+79.162  /  -3.259)

Acelerando, sobre una base de 81k loc en `src/`. Nada se retira nunca, así que
cada cambio cuesta más que el anterior; el final de esa curva es un proyecto en
el que no cabe ni una persona ni un modelo.

Este módulo SÓLO MIDE. No bloquea nada a propósito: el pre-commit ya tuvo esta
semana un fail-closed sobre un falso positivo —cancelaba cualquier commit de
sólo renombrados— y la lección es que una puerta se gana el derecho a bloquear
con datos, no de nacimiento. La regla dura va después, cuando haya histórico.

Vocabulario, y la distinción importa: ``unbounded`` (se añadió y no se borró
NADA) no es ``ok``, y ``unknown`` (no medible) tampoco. Confundir "no sé" con
"sano" es el defecto que esta misma auditoría encontró cuatro veces.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atlas.core.git_env import clean_git_env

__all__ = ["AccretionRatio", "accretion_ratio", "DEFAULT_THRESHOLD"]

#: Por encima de esto, el crecimiento deja de ser "un proyecto joven" y pasa a
#: ser deuda. 5:1 es generoso a propósito — el repo va por 24:1.
DEFAULT_THRESHOLD = 5.0
DEFAULT_PATHS: tuple[str, ...] = ("src", "tests")
_GIT_TIMEOUT_S = 60


@dataclass(frozen=True)
class AccretionRatio:
    """``added/deleted`` sobre una ventana. ``ratio=None`` = sin divisor."""

    added: int = 0
    deleted: int = 0
    days: int = 0
    ratio: float | None = None
    status: str = "unknown"
    reason: str = "no medido"

    def to_dict(self) -> dict[str, Any]:
        return {
            "added": self.added,
            "deleted": self.deleted,
            "days": self.days,
            "ratio": self.ratio,
            "status": self.status,
            "reason": self.reason,
        }


def accretion_ratio(
    repo_root: Path,
    *,
    days: int = 30,
    threshold: float = DEFAULT_THRESHOLD,
    paths: Sequence[str] = DEFAULT_PATHS,
) -> AccretionRatio:
    """Líneas añadidas y borradas en `paths` durante los últimos `days`.

    Nunca lanza: la consumen `atlas reality` y el hook de pre-commit.
    """
    try:
        result = subprocess.run(
            ["git", "log", f"--since={days} days ago", "--numstat", "--format=",
             "--", *paths],
            cwd=repo_root,
            env=clean_git_env(),
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return AccretionRatio(days=days, reason=f"git no ejecutable: {type(exc).__name__}")
    if result.returncode != 0:
        return AccretionRatio(
            days=days, reason=f"git log exit={result.returncode}: {result.stderr.strip()[:120]}"
        )

    added = deleted = 0
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        # '-' en binarios: no son líneas, no cuentan.
        if parts[0] == "-" or parts[1] == "-":
            continue
        try:
            added += int(parts[0])
            deleted += int(parts[1])
        except ValueError:
            continue

    if added == 0 and deleted == 0:
        return AccretionRatio(
            days=days, reason=f"sin cambios en {list(paths)} durante {days} días"
        )
    if deleted == 0:
        # No es ratio infinito ni es sano: es que no se ha retirado nada.
        return AccretionRatio(
            added=added, deleted=0, days=days, ratio=None, status="unbounded",
            reason=f"+{added} líneas y NINGUNA retirada en {days} días",
        )
    ratio = added / deleted
    status = "warn" if ratio > threshold else "ok"
    return AccretionRatio(
        added=added, deleted=deleted, days=days, ratio=round(ratio, 2), status=status,
        reason=(
            f"+{added} / -{deleted} = {ratio:.1f}:1 en {days} días "
            f"(umbral {threshold:g}:1)"
        ),
    )
