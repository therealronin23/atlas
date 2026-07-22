"""Fail-closed admission of an already-staged declarative plugin.

This gate neither downloads nor activates a plugin. It binds a strict manifest,
the supply-chain report, and static contribution checks into one data-only
result that a later Merkle/approval executor can consume.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from atlas.mcp.plugin_manifest import PluginManifest
from atlas.security.static_content import scan_static_content
from atlas.security.supply_chain import SupplyChainScanner
from atlas.security.supply_chain_models import IndicatorCatalog, SupplyChainReport


PLUGIN_MANIFEST_FILENAME = "atlas-plugin.json"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PluginAdmission(_StrictModel):
    schema_version: Literal["1.0"]
    status: Literal["admit", "review", "block"]
    plugin_id: str | None
    manifest_sha256: str | None
    reason_codes: list[str]
    scan: SupplyChainReport | None


class PluginAdmissionGate:
    """Evaluate a local staging child without treating it as executable code."""

    def __init__(
        self,
        *,
        staging_root: Path,
        scanner: SupplyChainScanner | None = None,
    ) -> None:
        self._staging_root = staging_root.absolute()
        self._scanner = scanner or SupplyChainScanner()

    def admit(
        self,
        root: Path,
        *,
        expected_plugin_id: str | None = None,
        catalog: IndicatorCatalog | None = None,
    ) -> PluginAdmission:
        """Return an admission decision; no result grants activation authority."""

        root_path = root.absolute()
        if self._staging_root.is_symlink() or not _is_staging_child(
            root_path,
            self._staging_root,
        ):
            return _blocked("staging_root_escape")

        scan = self._scanner.scan(root_path, catalog=catalog)
        if scan.status != "complete" or scan.verdict == "block":
            return _blocked(
                "supply_chain_block",
                scan=scan,
            )

        manifest_path = root_path / PLUGIN_MANIFEST_FILENAME
        manifest_record = next(
            (item for item in scan.files if item.path == PLUGIN_MANIFEST_FILENAME),
            None,
        )
        if manifest_record is None or manifest_path.is_symlink() or not manifest_path.is_file():
            return _blocked("manifest_missing", scan=scan)
        try:
            raw_manifest = manifest_path.read_bytes()
        except OSError:
            return _blocked("manifest_unreadable", scan=scan)
        manifest_sha256 = hashlib.sha256(raw_manifest).hexdigest()
        if manifest_sha256 != manifest_record.sha256:
            return _blocked("manifest_changed_after_scan", scan=scan)
        try:
            manifest = PluginManifest.model_validate_json(raw_manifest)
        except (UnicodeDecodeError, ValidationError, ValueError):
            return _blocked("manifest_invalid", manifest_sha256=manifest_sha256, scan=scan)
        if expected_plugin_id is not None and manifest.plugin_id != expected_plugin_id:
            return _blocked(
                "manifest_plugin_id_mismatch",
                plugin_id=manifest.plugin_id,
                manifest_sha256=manifest_sha256,
                scan=scan,
            )

        records = {item.path: item.sha256 for item in scan.files}
        for contribution in manifest.contributions:
            veto = _verify_contribution(root_path, contribution.path, records)
            if veto is not None:
                return _blocked(
                    veto,
                    plugin_id=manifest.plugin_id,
                    manifest_sha256=manifest_sha256,
                    scan=scan,
                )

        if scan.verdict == "review":
            return PluginAdmission(
                schema_version="1.0",
                status="review",
                plugin_id=manifest.plugin_id,
                manifest_sha256=manifest_sha256,
                reason_codes=["supply_chain_review"],
                scan=scan,
            )
        return PluginAdmission(
            schema_version="1.0",
            status="admit",
            plugin_id=manifest.plugin_id,
            manifest_sha256=manifest_sha256,
            reason_codes=[],
            scan=scan,
        )


def _is_staging_child(root: Path, staging_root: Path) -> bool:
    try:
        canonical_root = root.resolve(strict=False)
        canonical_staging = staging_root.resolve(strict=False)
        if canonical_root != root or canonical_staging != staging_root:
            return False
        relative = canonical_root.relative_to(canonical_staging)
    except OSError:
        return False
    except ValueError:
        return False
    return bool(relative.parts)


def _verify_contribution(
    root: Path,
    relative: str,
    records: dict[str, str],
) -> str | None:
    expected_sha256 = records.get(relative)
    if expected_sha256 is None:
        return "contribution_missing_or_unscanned"
    path = root / relative
    if path.is_symlink() or not path.is_file():
        return "contribution_missing_or_unscanned"
    try:
        raw = path.read_bytes()
    except OSError:
        return "contribution_unreadable"
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        return "contribution_changed_after_scan"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return "contribution_not_utf8"
    if scan_static_content(text) is not None:
        return "contribution_content_veto"
    return None


def _blocked(
    code: str,
    *,
    plugin_id: str | None = None,
    manifest_sha256: str | None = None,
    scan: SupplyChainReport | None = None,
) -> PluginAdmission:
    return PluginAdmission(
        schema_version="1.0",
        status="block",
        plugin_id=plugin_id,
        manifest_sha256=manifest_sha256,
        reason_codes=[code],
        scan=scan,
    )
