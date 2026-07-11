"""ConnectorPackEngine — packs de conexiones por sector."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from atlas.fabric.models import ConnectorPack
from atlas.fabric.recipes import RecipeEngine


def validate_pack(pack: ConnectorPack, recipes: RecipeEngine) -> list[str]:
    problems: list[str] = []
    known = {r.connector_id for r in recipes.all()}
    for cid in pack.connectors:
        if cid not in known:
            problems.append(f"conector sin receta: {cid}")
    stray = set(pack.setup_order) - set(pack.connectors) - set(pack.optional_connectors)
    if stray:
        problems.append(f"setup_order referencia conectores fuera del pack: {sorted(stray)}")
    return problems


class PackEngine:
    def __init__(self, packs_dir: Path, recipes: RecipeEngine) -> None:
        self._packs: dict[str, ConnectorPack] = {}
        self._rejected: dict[str, list[str]] = {}
        if packs_dir.exists():
            for path in sorted(packs_dir.glob("*_pack.json")):
                try:
                    pack = ConnectorPack.model_validate(
                        json.loads(path.read_text(encoding="utf-8"))
                    )
                except (ValidationError, json.JSONDecodeError) as exc:
                    self._rejected[path.stem] = [f"schema: {exc}"]
                    continue
                problems = validate_pack(pack, recipes)
                if problems:
                    self._rejected[pack.pack_id] = problems
                else:
                    self._packs[pack.pack_id] = pack

    @property
    def rejected(self) -> dict[str, list[str]]:
        return dict(self._rejected)

    def all(self) -> list[ConnectorPack]:
        return list(self._packs.values())

    def get(self, pack_id: str) -> ConnectorPack | None:
        return self._packs.get(pack_id)

    def for_sector(self, sector_id: str) -> list[ConnectorPack]:
        return [p for p in self._packs.values() if p.sector_id == sector_id]
