from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class SotaSnapshot:
    benchmark_name: str
    atlas_score: float
    reference_url: str
    reference_excerpt: str
    captured_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SotaSnapshotRecorder:
    def __init__(self, *, crawler: Any, store_path: Path) -> None:
        self._crawler = crawler
        self._store_path = store_path
        self._store_path.parent.mkdir(parents=True, exist_ok=True)

    def capture(
        self,
        *,
        benchmark_name: str,
        atlas_score: float,
        reference_url: str,
    ) -> SotaSnapshot:
        try:
            result = self._crawler.crawl(reference_url)
            if result.success:
                reference_excerpt = result.markdown[:2000]
            else:
                reference_excerpt = f"fetch fallido: {result.error}"
        except Exception as exc:
            reference_excerpt = f"fetch fallido: {exc}"

        snapshot = SotaSnapshot(
            benchmark_name=benchmark_name,
            atlas_score=atlas_score,
            reference_url=reference_url,
            reference_excerpt=reference_excerpt,
        )

        entries: list[dict[str, Any]] = []
        if self._store_path.exists():
            try:
                with self._store_path.open("r", encoding="utf-8") as f:
                    raw = f.read()
                if raw.strip():
                    entries = json.loads(raw)
                    if not isinstance(entries, list):
                        entries = []
            except (json.JSONDecodeError, OSError):
                entries = []

        entries.append(snapshot.to_dict())

        with self._store_path.open("w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

        return snapshot

    def history(self, benchmark_name: str | None = None) -> list[SotaSnapshot]:
        entries: list[dict[str, Any]] = []
        if self._store_path.exists():
            try:
                with self._store_path.open("r", encoding="utf-8") as f:
                    raw = f.read()
                if raw.strip():
                    entries = json.loads(raw)
                    if not isinstance(entries, list):
                        entries = []
            except (json.JSONDecodeError, OSError):
                entries = []

        known_fields = {f.name for f in fields(SotaSnapshot)}
        snapshots: list[SotaSnapshot] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            filtered = {k: v for k, v in item.items() if k in known_fields}
            try:
                snapshots.append(SotaSnapshot(**filtered))
            except TypeError:
                continue

        if benchmark_name is not None:
            snapshots = [s for s in snapshots if s.benchmark_name == benchmark_name]

        return snapshots
