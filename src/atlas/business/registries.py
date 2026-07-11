"""Sector Registry + Objective Registry — la autoridad son schemas/sector.schema.json
y schemas/objective.schema.json.

Hoy `sector_id` es un string suelto compartido por convención entre
question_packs y connector_packs, sin catálogo que valide que existe. Estos
registries cierran ese hueco: `SectorRegistry` es el catálogo, y
`unknown_sectors` deja caza-able el drift (un pack que referencia un sector
que nadie registró).

No importa `atlas.api.*` — evita el ciclo real business↔api.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

__all__ = [
    "Objective",
    "ObjectiveRegistry",
    "Sector",
    "SectorRegistry",
    "unknown_sectors",
]


class Sector(BaseModel):
    """schemas/sector.schema.json."""

    model_config = ConfigDict(extra="forbid")

    sector_id: str = Field(pattern=r"^[a-z0-9_]+$")
    display_name: str = Field(min_length=1)
    description: str | None = None
    default_workbenches: list[str] = Field(default_factory=list)
    default_capabilities: list[str] = Field(default_factory=list)
    question_pack_id: str | None = None
    connector_pack_id: str | None = None


class Objective(BaseModel):
    """schemas/objective.schema.json."""

    model_config = ConfigDict(extra="forbid")

    objective_id: str = Field(pattern=r"^obj_[a-z0-9_]+$")
    sector_id: str = Field(pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1)
    required_entities: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    workbenches: list[str] = Field(default_factory=list)
    gates: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)


class SectorRegistry:
    """Catálogo de sectores conocidos. Un sector inválido se excluye y se
    reporta (mismo patrón fail-closed que RecipeEngine/PackEngine)."""

    def __init__(self, sectors_dir: Path) -> None:
        self._sectors: dict[str, Sector] = {}
        self._rejected: dict[str, list[str]] = {}
        if sectors_dir.exists():
            for path in sorted(sectors_dir.glob("*.json")):
                try:
                    sector = Sector.model_validate(
                        json.loads(path.read_text(encoding="utf-8"))
                    )
                except (ValidationError, json.JSONDecodeError) as exc:
                    self._rejected[path.stem] = [f"schema: {exc}"]
                    continue
                self._sectors[sector.sector_id] = sector

    @property
    def rejected(self) -> dict[str, list[str]]:
        return dict(self._rejected)

    def all(self) -> list[Sector]:
        return list(self._sectors.values())

    def get(self, sector_id: str) -> Sector | None:
        return self._sectors.get(sector_id)

    def exists(self, sector_id: str) -> bool:
        return sector_id in self._sectors


class ObjectiveRegistry:
    """Catálogo de objetivos. Rechaza (no sirve a medias) cualquier objetivo
    cuyo sector_id no exista en el SectorRegistry pasado."""

    def __init__(self, objectives_dir: Path, sector_registry: SectorRegistry) -> None:
        self._objectives: dict[str, Objective] = {}
        self._rejected: dict[str, list[str]] = {}
        if objectives_dir.exists():
            for path in sorted(objectives_dir.glob("*.json")):
                try:
                    objective = Objective.model_validate(
                        json.loads(path.read_text(encoding="utf-8"))
                    )
                except (ValidationError, json.JSONDecodeError) as exc:
                    self._rejected[path.stem] = [f"schema: {exc}"]
                    continue
                if not sector_registry.exists(objective.sector_id):
                    self._rejected[objective.objective_id] = [
                        f"sector desconocido: {objective.sector_id}"
                    ]
                    continue
                self._objectives[objective.objective_id] = objective

    @property
    def rejected(self) -> dict[str, list[str]]:
        return dict(self._rejected)

    def all(self) -> list[Objective]:
        return list(self._objectives.values())

    def get(self, objective_id: str) -> Objective | None:
        return self._objectives.get(objective_id)

    def exists(self, objective_id: str) -> bool:
        return objective_id in self._objectives


def unknown_sectors(sector_ids: Iterable[str], registry: SectorRegistry) -> list[str]:
    """sector_id referenciados que NO están en el SectorRegistry — caza drift
    entre question_packs/connector_packs y el catálogo real de sectores."""
    return sorted({sid for sid in sector_ids if not registry.exists(sid)})
