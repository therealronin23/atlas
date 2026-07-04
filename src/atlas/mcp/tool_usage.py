import json
from pathlib import Path
from typing import Any


class ToolUsageCounter:
    def __init__(self, store_path: Path):
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        try:
            with open(self.store_path, 'r') as f:
                data: Any = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        # Migrate old format {tool_name: int} to new format {tool_name: {origin: int}}
        migrated = False
        for tool_name, value in list(data.items()):
            if isinstance(value, int):
                data[tool_name] = {'external': value}
                migrated = True
            elif not isinstance(value, dict):
                # Unexpected type, treat as empty
                data[tool_name] = {}
                migrated = True
        if migrated:
            self._save(data)
        return data

    def _save(self, data: dict[str, Any]) -> None:
        with open(self.store_path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def record(self, tool_name: str, *, origin: str = 'external') -> None:
        data = self._load()
        if tool_name not in data:
            data[tool_name] = {}
        if origin not in data[tool_name]:
            data[tool_name][origin] = 0
        data[tool_name][origin] += 1
        self._save(data)

    def counts(self) -> dict[str, dict[str, int]]:
        data = self._load()
        # Ensure we return dict[str, dict[str, int]] even if migration produced empty dicts
        result: dict[str, dict[str, int]] = {}
        for tool_name, origins in data.items():
            if isinstance(origins, dict):
                result[tool_name] = {k: v for k, v in origins.items() if isinstance(v, int)}
        return result

    def external_counts(self) -> dict[str, int]:
        data = self.counts()
        result: dict[str, int] = {}
        for tool_name, origins in data.items():
            if 'external' in origins:
                result[tool_name] = origins['external']
        return result