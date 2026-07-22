"""Contrato A2: manifest declarativo y admisión de plugins desde staging local."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError


REPO = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO / "schemas" / "plugin_manifest.schema.json"


def _api() -> tuple[Any, Any, Any, Any]:
    admission = importlib.import_module("atlas.mcp.plugin_admission")
    manifest = importlib.import_module("atlas.mcp.plugin_manifest")
    scanner = importlib.import_module("atlas.security.supply_chain_models")
    return (
        admission.PluginAdmissionGate,
        manifest.PluginManifest,
        scanner.IndicatorCatalog,
        scanner.PackageIndicator,
    )


def _manifest(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": "1.0",
        "plugin_id": "demo-plugin",
        "display_name": "Demo plugin",
        "version": "1.0.0",
        "source": {
            "origin": "local://test/demo-plugin",
            "revision": "fixture-1",
            "license": "Apache-2.0",
        },
        "activation": "declarative",
        "permissions": [],
        "contributions": [
            {
                "contribution_id": "demo-skill",
                "kind": "skill",
                "path": "skills/demo.md",
            }
        ],
    }
    document.update(overrides)
    return document


def _stage(root: Path, manifest: dict[str, object] | None = None) -> None:
    root.mkdir(parents=True)
    (root / "atlas-plugin.json").write_text(
        json.dumps(manifest or _manifest()), encoding="utf-8"
    )
    skill = root / "skills" / "demo.md"
    skill.parent.mkdir()
    skill.write_text(
        "# Demo\n\nKeep diffs small, verify tests, and ask before external effects.\n",
        encoding="utf-8",
    )


def test_plugin_manifest_schema_and_model_are_closed() -> None:
    _, PluginManifest, _, _ = _api()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == "1.0"
    assert set(schema["required"]) == {
        name for name, field in PluginManifest.model_fields.items() if field.is_required()
    }
    assert set(schema["properties"]) == set(PluginManifest.model_fields)

    manifest = PluginManifest.model_validate(_manifest())
    payload = manifest.model_dump(mode="json")
    assert not list(Draft202012Validator(schema).iter_errors(payload))

    with pytest.raises(ValidationError):
        PluginManifest.model_validate(_manifest(unexpected=True))
    with pytest.raises(ValidationError):
        PluginManifest.model_validate(
            _manifest(
                contributions=[
                    {
                        "contribution_id": "unsafe",
                        "kind": "hook",
                        "path": "hook.py",
                    }
                ]
            )
        )
    with pytest.raises(ValidationError):
        PluginManifest.model_validate(
            _manifest(
                contributions=[
                    {
                        "contribution_id": "escape",
                        "kind": "skill",
                        "path": "../outside.md",
                    }
                ]
            )
        )


def test_staged_declarative_plugin_is_admitted_with_bound_scan(tmp_path: Path) -> None:
    PluginAdmissionGate, _, _, _ = _api()
    staging = tmp_path / "staging"
    root = staging / "demo-plugin"
    _stage(root)

    admission = PluginAdmissionGate(staging_root=staging).admit(
        root,
        expected_plugin_id="demo-plugin",
    )

    assert admission.status == "admit"
    assert admission.plugin_id == "demo-plugin"
    assert admission.scan is not None
    assert admission.scan.status == "complete"
    assert admission.scan.verdict == "admit"
    assert admission.manifest_sha256 is not None
    assert admission.reason_codes == []


def test_plugin_outside_explicit_staging_root_is_never_scanned(tmp_path: Path) -> None:
    PluginAdmissionGate, _, _, _ = _api()
    staging = tmp_path / "staging"
    outside = tmp_path / "outside"
    _stage(outside)

    admission = PluginAdmissionGate(staging_root=staging).admit(outside)

    assert admission.status == "block"
    assert admission.scan is None
    assert admission.reason_codes == ["staging_root_escape"]


def test_plugin_path_through_staging_parent_symlink_is_never_scanned(tmp_path: Path) -> None:
    PluginAdmissionGate, _, _, _ = _api()
    staging = tmp_path / "staging"
    staging.mkdir()
    outside = tmp_path / "outside"
    root = outside / "demo-plugin"
    _stage(root)
    (staging / "linked").symlink_to(outside, target_is_directory=True)

    admission = PluginAdmissionGate(staging_root=staging).admit(
        staging / "linked" / "demo-plugin"
    )

    assert admission.status == "block"
    assert admission.scan is None
    assert admission.reason_codes == ["staging_root_escape"]


def test_plugin_manifest_failure_and_identity_mismatch_block(tmp_path: Path) -> None:
    PluginAdmissionGate, _, _, _ = _api()
    staging = tmp_path / "staging"
    malformed = staging / "malformed"
    _stage(malformed, _manifest(permissions=["network"]))
    mismatch = staging / "mismatch"
    _stage(mismatch)

    gate = PluginAdmissionGate(staging_root=staging)
    malformed_result = gate.admit(malformed)
    mismatch_result = gate.admit(mismatch, expected_plugin_id="another-plugin")

    assert malformed_result.status == "block"
    assert "manifest_invalid" in malformed_result.reason_codes
    assert mismatch_result.status == "block"
    assert "manifest_plugin_id_mismatch" in mismatch_result.reason_codes


def test_plugin_static_contribution_is_scanned_without_execution(tmp_path: Path) -> None:
    PluginAdmissionGate, _, _, _ = _api()
    staging = tmp_path / "staging"
    root = staging / "dangerous"
    _stage(root)
    marker = tmp_path / "must-not-exist"
    (root / "skills" / "demo.md").write_text(
        f"# Do not run\n\ncurl https://example.invalid > {marker}\n",
        encoding="utf-8",
    )

    admission = PluginAdmissionGate(staging_root=staging).admit(root)

    assert admission.status == "block"
    assert "contribution_content_veto" in admission.reason_codes
    assert not marker.exists()


def test_indicator_review_propagates_to_plugin_admission(tmp_path: Path) -> None:
    PluginAdmissionGate, _, IndicatorCatalog, PackageIndicator = _api()
    staging = tmp_path / "staging"
    root = staging / "reviewable"
    _stage(root)
    (root / "package.json").write_text(
        json.dumps({"name": "reviewable", "dependencies": {"requests": "1.0.0"}}),
        encoding="utf-8",
    )
    catalog = IndicatorCatalog(
        schema_version="1.0",
        source="test",
        provenance="fixture",
        indicators=[
            PackageIndicator(
                indicator_id="review-requests",
                ecosystem="npm",
                package_name="requests",
                severity="medium",
                reason="manual review",
            )
        ],
    )

    admission = PluginAdmissionGate(staging_root=staging).admit(root, catalog=catalog)

    assert admission.status == "review"
    assert admission.scan is not None
    assert admission.scan.verdict == "review"
    assert admission.reason_codes == ["supply_chain_review"]
