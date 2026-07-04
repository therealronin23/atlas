import json
from pathlib import Path
from typing import Any


class ToolUsageCounter:
    def __init__(self, store_path: Path):
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, tool_name: str) -> None:
        try:
            with open(self.store_path, 'r') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        data[tool_name] = data.get(tool_name, 0) + 1
        with open(self.store_path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def counts(self) -> dict[str, int]:
        try:
            with open(self.store_path, 'r') as f:
                data: Any = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        return dict(data) if isinstance(data, dict) else {}