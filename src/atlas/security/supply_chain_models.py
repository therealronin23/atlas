"""Closed, data-only contracts for local supply-chain admission scans.

The scanner deliberately reports observations instead of executing an artifact.
These models are the stable boundary used by a future admission gate and by
human review; unknown fields are rejected on both sides of that boundary.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict


class _StrictModel(BaseModel):
    """Prevent a report consumer from silently accepting unreviewed fields."""

    model_config = ConfigDict(extra="forbid")


class FileRecord(_StrictModel):
    path: str
    sha256: str
    size_bytes: int


class PackageRecord(_StrictModel):
    ecosystem: str
    name: str
    version: str | None
    source_manifest: str


class DependencyRecord(_StrictModel):
    ecosystem: str
    name: str
    requested_version: str
    scope: str
    source_manifest: str


class Finding(_StrictModel):
    code: str
    path: str
    detail: str
    severity: Literal["info", "low", "medium", "high", "critical"]
    indicator_id: str | None
    package_name: str | None


class Diagnostic(_StrictModel):
    code: str
    detail: str
    blocking: bool


class ScanSummary(_StrictModel):
    files_hashed: int
    skipped_entries: int
    terminal: bool


class PackageIndicator(_StrictModel):
    """A pinned, exact-match package indicator supplied by a trusted caller."""

    indicator_id: str
    ecosystem: str
    package_name: str
    severity: Literal["info", "low", "medium", "high", "critical"]
    reason: str


class IndicatorCatalog(_StrictModel):
    schema_version: Literal["1.0"]
    source: str
    provenance: str
    indicators: list[PackageIndicator]

    def digest(self) -> str:
        """Return an order-independent identity for the pinned indicator set."""

        payload = self.model_dump(mode="json")
        payload["indicators"] = sorted(
            payload["indicators"],
            key=lambda item: (
                item["indicator_id"],
                item["ecosystem"],
                item["package_name"],
                item["severity"],
                item["reason"],
            ),
        )
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class SupplyChainReport(_StrictModel):
    """Terminal, serializable result of one metadata-only local scan."""

    schema_version: Literal["1.0"]
    scan_id: str
    record_id: str
    root: str
    catalog_digest: str
    status: Literal["complete", "partial", "failed"]
    verdict: Literal["admit", "review", "block"]
    started_at: str
    completed_at: str
    summary: ScanSummary
    files: list[FileRecord]
    packages: list[PackageRecord]
    dependencies: list[DependencyRecord]
    findings: list[Finding]
    diagnostics: list[Diagnostic]
