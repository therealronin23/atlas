"""Contrato del escaneo local de admisión de cadena de suministro (A1)."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest


def _api() -> tuple[Any, Any, Any, Any]:
    scanner_module = importlib.import_module("atlas.security.supply_chain")
    models_module = importlib.import_module("atlas.security.supply_chain_models")
    return (
        scanner_module.SupplyChainScanner,
        scanner_module.ScanLimits,
        models_module.IndicatorCatalog,
        models_module.PackageIndicator,
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _benign_fixture(root: Path) -> None:
    _write(
        root / "package.json",
        json.dumps(
            {
                "name": "demo-js",
                "version": "1.2.3",
                "dependencies": {"left-pad": "^1.3.0"},
                "devDependencies": {"vitest": "~3.2.0"},
            },
            sort_keys=True,
        ),
    )
    _write(
        root / "pyproject.toml",
        """[project]
name = "demo-py"
version = "0.4.0"
dependencies = ["requests>=2.31", "typing-extensions; python_version < '3.12'"]

[project.optional-dependencies]
dev = ["pytest>=8"]
""",
    )
    _write(root / "requirements-dev.txt", "ruff==0.12.0\n# ignored comment\n")
    _write(
        root / "go.mod",
        """module example.com/demo

go 1.23

require (
    example.com/lib v1.2.3
    example.com/indirect v0.1.0 // indirect
)
""",
    )
    _write(root / "src" / "app.py", "print('data only; never executed')\n")
    _write(root / ".git" / "config", "must not be scanned\n")
    _write(root / "node_modules" / "dep" / "index.js", "must not be scanned\n")


def _dependency_rows(report: Any) -> set[tuple[str, str, str, str]]:
    return {
        (item.ecosystem, item.name, item.requested_version, item.scope)
        for item in report.dependencies
    }


def test_benign_npm_python_go_scan_completes_hashes_and_admits(tmp_path: Path) -> None:
    SupplyChainScanner, _, _, _ = _api()
    root = tmp_path / "artifact"
    _benign_fixture(root)

    report = SupplyChainScanner().scan(root)

    assert report.schema_version == "1.0"
    assert report.status == "complete"
    assert report.verdict == "admit"
    assert report.summary.terminal
    assert report.summary.files_hashed == 5
    assert report.summary.skipped_entries == 2
    assert {item.path for item in report.files} == {
        "go.mod",
        "package.json",
        "pyproject.toml",
        "requirements-dev.txt",
        "src/app.py",
    }
    package_json = next(item for item in report.files if item.path == "package.json")
    expected_hash = hashlib.sha256((root / "package.json").read_bytes()).hexdigest()
    assert package_json.sha256 == expected_hash
    assert package_json.size_bytes == (root / "package.json").stat().st_size

    assert {
        (item.ecosystem, item.name, item.version, item.source_manifest)
        for item in report.packages
    } == {
        ("npm", "demo-js", "1.2.3", "package.json"),
        ("python", "demo-py", "0.4.0", "pyproject.toml"),
        ("go", "example.com/demo", None, "go.mod"),
    }
    dependencies = _dependency_rows(report)
    assert ("npm", "left-pad", "^1.3.0", "runtime") in dependencies
    assert ("npm", "vitest", "~3.2.0", "development") in dependencies
    assert ("python", "requests", ">=2.31", "runtime") in dependencies
    assert ("python", "typing-extensions", "; python_version < '3.12'", "runtime") in dependencies
    assert ("python", "pytest", ">=8", "optional:dev") in dependencies
    assert ("python", "ruff", "==0.12.0", "development") in dependencies
    assert ("go", "example.com/lib", "v1.2.3", "direct") in dependencies
    assert ("go", "example.com/indirect", "v0.1.0", "indirect") in dependencies
    assert all(not item.path.startswith((".git/", "node_modules/")) for item in report.files)
    assert all(not diagnostic.blocking for diagnostic in report.diagnostics)


def test_equivalent_roots_have_stable_record_id_but_unique_run_identity(tmp_path: Path) -> None:
    SupplyChainScanner, _, _, _ = _api()
    first = tmp_path / "first"
    second = tmp_path / "second"
    _benign_fixture(first)
    _benign_fixture(second)

    first_report = SupplyChainScanner().scan(first)
    second_report = SupplyChainScanner().scan(second)

    assert first_report.record_id == second_report.record_id
    assert len(first_report.record_id) == 64
    int(first_report.record_id, 16)
    assert first_report.scan_id != second_report.scan_id
    assert first_report.root != second_report.root
    assert first_report.started_at != second_report.started_at
    assert first_report.completed_at != second_report.completed_at


def test_file_and_directory_symlinks_are_reported_blocked_and_never_followed(
    tmp_path: Path,
) -> None:
    SupplyChainScanner, _, _, _ = _api()
    outside = tmp_path / "outside"
    _write(outside / "secret.txt", "outside artifact")
    root = tmp_path / "artifact"
    _write(root / "safe.txt", "safe")
    (root / "file-link").symlink_to(outside / "secret.txt")
    (root / "dir-link").symlink_to(outside, target_is_directory=True)

    report = SupplyChainScanner().scan(root)

    assert report.status == "complete"
    assert report.verdict == "block"
    symlinks = [finding for finding in report.findings if finding.code == "symlink"]
    assert {finding.path for finding in symlinks} == {"dir-link", "file-link"}
    assert {item.path for item in report.files} == {"safe.txt"}
    assert "secret.txt" not in {item.path for item in report.files}


def test_root_path_through_a_parent_symlink_is_blocked_before_enumeration(
    tmp_path: Path,
) -> None:
    SupplyChainScanner, _, _, _ = _api()
    outside = tmp_path / "outside"
    _write(outside / "nested" / "secret.txt", "outside artifact")
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "linked").symlink_to(outside, target_is_directory=True)

    report = SupplyChainScanner().scan(staging / "linked" / "nested")

    assert report.status == "failed"
    assert report.verdict == "block"
    assert report.files == []
    assert any(item.code == "root_symlink" and item.blocking for item in report.diagnostics)


@pytest.mark.parametrize(
    ("limits", "expected_code"),
    [
        ({"max_files": 1}, "limit_file_count"),
        ({"max_total_bytes": 5}, "limit_total_bytes"),
        ({"max_file_bytes": 4}, "limit_file_bytes"),
    ],
)
def test_file_and_byte_bounds_are_partial_and_block(
    tmp_path: Path,
    limits: dict[str, int],
    expected_code: str,
) -> None:
    SupplyChainScanner, ScanLimits, _, _ = _api()
    root = tmp_path / "artifact"
    _write(root / "a.txt", "12345")
    _write(root / "b.txt", "67890")

    report = SupplyChainScanner(limits=ScanLimits(**limits)).scan(root)

    assert report.status == "partial"
    assert report.verdict == "block"
    assert any(
        item.code == expected_code and item.blocking for item in report.diagnostics
    )


def test_elapsed_time_bound_is_partial_and_block(tmp_path: Path) -> None:
    SupplyChainScanner, ScanLimits, _, _ = _api()
    root = tmp_path / "artifact"
    _write(root / "a.txt", "small")
    ticks = iter((0.0, 1.0, 2.0, 3.0))

    report = SupplyChainScanner(
        limits=ScanLimits(max_elapsed_seconds=0.5),
        clock=lambda: next(ticks),
    ).scan(root)

    assert report.status == "partial"
    assert report.verdict == "block"
    assert any(
        item.code == "limit_elapsed_time" and item.blocking
        for item in report.diagnostics
    )


def test_npm_lifecycle_scripts_are_named_without_execution_and_block(tmp_path: Path) -> None:
    SupplyChainScanner, _, _, _ = _api()
    root = tmp_path / "artifact"
    marker = tmp_path / "must-not-exist"
    _write(
        root / "package.json",
        json.dumps(
            {
                "name": "scripted",
                "scripts": {
                    "preinstall": f"touch {marker}",
                    "postinstall": "arbitrary third-party command",
                    "test": "safe because it is never run either",
                },
            }
        ),
    )

    report = SupplyChainScanner().scan(root)

    assert report.status == "complete"
    assert report.verdict == "block"
    lifecycle = [f for f in report.findings if f.code == "npm_lifecycle_script"]
    assert {finding.detail for finding in lifecycle} == {"preinstall", "postinstall"}
    assert not marker.exists()
    serialized = report.model_dump_json()
    assert f"touch {marker}" not in serialized
    assert "arbitrary third-party command" not in serialized


def test_exact_indicator_matching_is_normalized_non_substring_and_overlapping(
    tmp_path: Path,
) -> None:
    SupplyChainScanner, _, IndicatorCatalog, PackageIndicator = _api()
    root = tmp_path / "artifact"
    _write(
        root / "package.json",
        json.dumps(
            {
                "name": "consumer",
                "dependencies": {
                    "@scope/danger": "1.0.0",
                    "safe-danger-addon": "2.0.0",
                },
            }
        ),
    )
    indicators = [
        PackageIndicator(
            indicator_id="ioc-medium",
            ecosystem="npm",
            package_name="@SCOPE/DANGER",
            severity="medium",
            reason="first independent indicator",
        ),
        PackageIndicator(
            indicator_id="ioc-high",
            ecosystem="npm",
            package_name="@scope/danger",
            severity="high",
            reason="second independent indicator",
        ),
        PackageIndicator(
            indicator_id="ioc-substring",
            ecosystem="npm",
            package_name="danger",
            severity="critical",
            reason="must not substring-match",
        ),
    ]
    catalog = IndicatorCatalog(
        schema_version="1.0",
        source="unit-test",
        provenance="local pinned fixture",
        indicators=indicators,
    )
    reordered = catalog.model_copy(update={"indicators": list(reversed(indicators))})

    report = SupplyChainScanner().scan(root, catalog=catalog)

    matches = [finding for finding in report.findings if finding.code == "indicator_match"]
    assert report.verdict == "block"
    assert {finding.indicator_id for finding in matches} == {"ioc-medium", "ioc-high"}
    assert all(finding.package_name == "@scope/danger" for finding in matches)
    assert catalog.digest() == reordered.digest()
    assert report.catalog_digest == catalog.digest()


def test_medium_indicator_reviews_without_blocking(tmp_path: Path) -> None:
    SupplyChainScanner, _, IndicatorCatalog, PackageIndicator = _api()
    root = tmp_path / "artifact"
    _write(root / "requirements.txt", "Requests==2.32.0\n")
    catalog = IndicatorCatalog(
        schema_version="1.0",
        source="unit-test",
        provenance="local pinned fixture",
        indicators=[
            PackageIndicator(
                indicator_id="ioc-medium",
                ecosystem="python",
                package_name="requests",
                severity="medium",
                reason="review requested",
            )
        ],
    )

    report = SupplyChainScanner().scan(root, catalog=catalog)

    assert report.status == "complete"
    assert report.verdict == "review"


@pytest.mark.parametrize(
    ("manifest", "content"),
    [
        ("package.json", "{not-json"),
        ("pyproject.toml", "[project\nname = 'broken'"),
        ("go.mod", "go 1.23\nrequire malformed"),
    ],
)
def test_malformed_recognized_manifest_is_fail_closed(
    tmp_path: Path,
    manifest: str,
    content: str,
) -> None:
    SupplyChainScanner, _, _, _ = _api()
    root = tmp_path / "artifact"
    _write(root / manifest, content)

    report = SupplyChainScanner().scan(root)

    assert report.status == "partial"
    assert report.verdict == "block"
    assert any(
        finding.code == "malformed_manifest" and finding.path == manifest
        for finding in report.findings
    )


def test_missing_root_always_returns_terminal_failed_report(tmp_path: Path) -> None:
    SupplyChainScanner, _, _, _ = _api()

    report = SupplyChainScanner().scan(tmp_path / "missing")

    assert report.status == "failed"
    assert report.verdict == "block"
    assert report.summary.terminal
    assert any(item.blocking for item in report.diagnostics)
