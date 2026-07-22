"""Bounded, metadata-only supply-chain scanner for local admission.

It intentionally does not install, import, run, or resolve any artifact code.
The implementation is a clean-room adaptation of the useful safety shape found
in external scanners: deterministic records, bounded traversal, no symlink
following, and terminal fail-closed reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Callable, Iterable
import tomllib
from uuid import uuid4

from atlas.security.supply_chain_models import (
    DependencyRecord,
    Diagnostic,
    FileRecord,
    Finding,
    IndicatorCatalog,
    PackageIndicator,
    PackageRecord,
    ScanSummary,
    SupplyChainReport,
)


_SKIPPED_DIRECTORIES = frozenset(
    {".git", "node_modules", ".venv", "venv", "__pycache__", "build", "dist"}
)
_NPM_SCOPES = {
    "dependencies": "runtime",
    "devDependencies": "development",
    "optionalDependencies": "optional",
    "peerDependencies": "peer",
}
_NPM_LIFECYCLE_SCRIPTS = frozenset(
    {
        "preinstall",
        "install",
        "postinstall",
        "prepublish",
        "preprepare",
        "prepare",
        "postprepare",
        "prepack",
        "postpack",
        "prepublishOnly",
        "preversion",
        "version",
        "postversion",
    }
)
_PYTHON_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)(.*)$")
_GO_REQUIRE = re.compile(
    r"^([A-Za-z0-9._~/-]+)\s+(v[^\s]+)(?:\s+//\s*indirect)?$"
)


@dataclass(frozen=True, slots=True)
class ScanLimits:
    """Hard limits that turn a potentially incomplete result into a block."""

    max_files: int = 10_000
    max_total_bytes: int = 50 * 1024 * 1024
    max_file_bytes: int = 2 * 1024 * 1024
    max_elapsed_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_files < 1:
            raise ValueError("max_files must be at least one")
        if self.max_total_bytes < 1:
            raise ValueError("max_total_bytes must be at least one")
        if self.max_file_bytes < 1:
            raise ValueError("max_file_bytes must be at least one")
        if self.max_elapsed_seconds <= 0:
            raise ValueError("max_elapsed_seconds must be positive")


class SupplyChainScanner:
    """Inspect a directory without executing anything within it."""

    def __init__(
        self,
        *,
        limits: ScanLimits | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limits = limits or ScanLimits()
        self._clock = clock

    def scan(
        self,
        root: str | Path,
        *,
        catalog: IndicatorCatalog | None = None,
    ) -> SupplyChainReport:
        """Produce a terminal report for ``root`` without following symlinks."""

        started_at = _now()
        started_clock = self._clock()
        root_path = Path(root).absolute()
        active_catalog = catalog or _empty_catalog()
        files: list[FileRecord] = []
        packages: list[PackageRecord] = []
        dependencies: list[DependencyRecord] = []
        findings: list[Finding] = []
        diagnostics: list[Diagnostic] = []
        skipped_entries = 0
        partial = False
        total_bytes = 0

        if not root_path.exists() or not root_path.is_dir():
            diagnostics.append(
                Diagnostic(
                    code="root_missing",
                    detail="scan root does not exist as a readable directory",
                    blocking=True,
                )
            )
            return self._report(
                root_path=root_path,
                catalog=active_catalog,
                status="failed",
                started_at=started_at,
                files=files,
                packages=packages,
                dependencies=dependencies,
                findings=findings,
                diagnostics=diagnostics,
                skipped_entries=skipped_entries,
            )

        try:
            root_has_symlink_component = root_path.resolve(strict=False) != root_path
        except OSError:
            root_has_symlink_component = True
        if root_has_symlink_component:
            diagnostics.append(
                Diagnostic(
                    code="root_symlink",
                    detail="scan root contains a symlink component",
                    blocking=True,
                )
            )
            return self._report(
                root_path=root_path,
                catalog=active_catalog,
                status="failed",
                started_at=started_at,
                files=files,
                packages=packages,
                dependencies=dependencies,
                findings=findings,
                diagnostics=diagnostics,
                skipped_entries=skipped_entries,
            )

        candidates, skipped_entries, collection_partial = self._collect_files(
            root_path,
            started_clock,
            findings,
            diagnostics,
        )
        partial = partial or collection_partial

        for path in candidates:
            if self._clock() - started_clock > self._limits.max_elapsed_seconds:
                diagnostics.append(
                    Diagnostic(
                        code="limit_elapsed_time",
                        detail="scan time limit reached before all files were hashed",
                        blocking=True,
                    )
                )
                partial = True
                break
            if len(files) >= self._limits.max_files:
                diagnostics.append(
                    Diagnostic(
                        code="limit_file_count",
                        detail="file count limit reached before all files were hashed",
                        blocking=True,
                    )
                )
                partial = True
                break

            relative = path.relative_to(root_path).as_posix()
            try:
                initial_stat = path.stat(follow_symlinks=False)
                size_bytes = initial_stat.st_size
            except OSError:
                diagnostics.append(
                    Diagnostic(
                        code="unreadable_file",
                        detail=f"could not stat {relative}",
                        blocking=True,
                    )
                )
                partial = True
                continue
            if size_bytes > self._limits.max_file_bytes:
                diagnostics.append(
                    Diagnostic(
                        code="limit_file_bytes",
                        detail=f"file exceeds the configured byte limit: {relative}",
                        blocking=True,
                    )
                )
                partial = True
                break
            if total_bytes + size_bytes > self._limits.max_total_bytes:
                diagnostics.append(
                    Diagnostic(
                        code="limit_total_bytes",
                        detail="total byte limit reached before all files were hashed",
                        blocking=True,
                    )
                )
                partial = True
                break

            try:
                digest, content = _read_and_hash_without_following_symlinks(
                    path,
                    initial_stat,
                )
            except OSError:
                diagnostics.append(
                    Diagnostic(
                        code="unreadable_file",
                        detail=f"could not read {relative}",
                        blocking=True,
                    )
                )
                partial = True
                continue

            files.append(
                FileRecord(path=relative, sha256=digest, size_bytes=size_bytes)
            )
            total_bytes += size_bytes
            if _is_manifest(path.name):
                if not self._inspect_manifest(
                    relative,
                    path.name,
                    content,
                    packages,
                    dependencies,
                    findings,
                ):
                    partial = True

        self._apply_indicators(dependencies, active_catalog, findings)
        status = "partial" if partial else "complete"
        return self._report(
            root_path=root_path,
            catalog=active_catalog,
            status=status,
            started_at=started_at,
            files=files,
            packages=packages,
            dependencies=dependencies,
            findings=findings,
            diagnostics=diagnostics,
            skipped_entries=skipped_entries,
        )

    def _collect_files(
        self,
        root: Path,
        started_clock: float,
        findings: list[Finding],
        diagnostics: list[Diagnostic],
    ) -> tuple[list[Path], int, bool]:
        """Return regular files only; a discovered link is evidence, never input."""

        pending = [root]
        candidates: list[Path] = []
        skipped_entries = 0
        partial = False
        while pending:
            if self._clock() - started_clock > self._limits.max_elapsed_seconds:
                diagnostics.append(
                    Diagnostic(
                        code="limit_elapsed_time",
                        detail="scan time limit reached while enumerating files",
                        blocking=True,
                    )
                )
                return candidates, skipped_entries, True
            directory = pending.pop()
            try:
                with os.scandir(directory) as entries:
                    ordered_entries = sorted(entries, key=lambda entry: entry.name)
            except OSError:
                relative = directory.relative_to(root).as_posix()
                diagnostics.append(
                    Diagnostic(
                        code="unreadable_directory",
                        detail=f"could not enumerate {relative}",
                        blocking=True,
                    )
                )
                partial = True
                continue
            for entry in ordered_entries:
                if self._clock() - started_clock > self._limits.max_elapsed_seconds:
                    diagnostics.append(
                        Diagnostic(
                            code="limit_elapsed_time",
                            detail="scan time limit reached while enumerating files",
                            blocking=True,
                        )
                    )
                    return candidates, skipped_entries, True
                candidate = Path(entry.path)
                relative = candidate.relative_to(root).as_posix()
                try:
                    if entry.is_symlink():
                        findings.append(
                            Finding(
                                code="symlink",
                                path=relative,
                                detail="symlink was not followed",
                                severity="high",
                                indicator_id=None,
                                package_name=None,
                            )
                        )
                    elif entry.is_dir(follow_symlinks=False):
                        if entry.name in _SKIPPED_DIRECTORIES:
                            skipped_entries += 1
                        else:
                            pending.append(candidate)
                    elif entry.is_file(follow_symlinks=False):
                        if len(candidates) >= self._limits.max_files:
                            diagnostics.append(
                                Diagnostic(
                                    code="limit_file_count",
                                    detail="file count limit reached while enumerating files",
                                    blocking=True,
                                )
                            )
                            return candidates, skipped_entries, True
                        candidates.append(candidate)
                except OSError:
                    diagnostics.append(
                        Diagnostic(
                            code="unreadable_entry",
                            detail=f"could not inspect {relative}",
                            blocking=True,
                        )
                    )
                    partial = True
        return sorted(candidates), skipped_entries, partial

    def _inspect_manifest(
        self,
        relative: str,
        filename: str,
        content: bytes,
        packages: list[PackageRecord],
        dependencies: list[DependencyRecord],
        findings: list[Finding],
    ) -> bool:
        try:
            if filename == "package.json":
                _parse_package_json(relative, content, packages, dependencies, findings)
            elif filename == "pyproject.toml":
                _parse_pyproject(relative, content, packages, dependencies)
            elif filename == "go.mod":
                _parse_go_mod(relative, content, packages, dependencies)
            else:
                _parse_requirements(relative, content, dependencies)
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError):
            findings.append(
                Finding(
                    code="malformed_manifest",
                    path=relative,
                    detail="recognized manifest could not be parsed",
                    severity="high",
                    indicator_id=None,
                    package_name=None,
                )
            )
            return False
        return True

    def _apply_indicators(
        self,
        dependencies: Iterable[DependencyRecord],
        catalog: IndicatorCatalog,
        findings: list[Finding],
    ) -> None:
        normalized: dict[tuple[str, str], list[PackageIndicator]] = {}
        for indicator in catalog.indicators:
            key = (
                indicator.ecosystem.lower(),
                _normalize_package_name(indicator.ecosystem, indicator.package_name),
            )
            normalized.setdefault(key, []).append(indicator)
        for dependency in dependencies:
            key = (
                dependency.ecosystem.lower(),
                _normalize_package_name(dependency.ecosystem, dependency.name),
            )
            for indicator in normalized.get(key, []):
                findings.append(
                    Finding(
                        code="indicator_match",
                        path=dependency.source_manifest,
                        detail="exact package indicator matched",
                        severity=indicator.severity,
                        indicator_id=indicator.indicator_id,
                        package_name=dependency.name,
                    )
                )

    def _report(
        self,
        *,
        root_path: Path,
        catalog: IndicatorCatalog,
        status: str,
        started_at: str,
        files: list[FileRecord],
        packages: list[PackageRecord],
        dependencies: list[DependencyRecord],
        findings: list[Finding],
        diagnostics: list[Diagnostic],
        skipped_entries: int,
    ) -> SupplyChainReport:
        ordered_files = sorted(files, key=lambda item: item.path)
        ordered_packages = sorted(
            packages,
            key=lambda item: (item.ecosystem, item.name, item.version or "", item.source_manifest),
        )
        ordered_dependencies = sorted(
            dependencies,
            key=lambda item: (
                item.ecosystem,
                item.name,
                item.requested_version,
                item.scope,
                item.source_manifest,
            ),
        )
        ordered_findings = sorted(
            findings,
            key=lambda item: (
                item.code,
                item.path,
                item.indicator_id or "",
                item.package_name or "",
            ),
        )
        ordered_diagnostics = sorted(
            diagnostics,
            key=lambda item: (item.code, item.detail, item.blocking),
        )
        verdict = _verdict(status, ordered_findings)
        completed_at = _now()
        record_id = _record_id(
            catalog_digest=catalog.digest(),
            status=status,
            verdict=verdict,
            files=ordered_files,
            packages=ordered_packages,
            dependencies=ordered_dependencies,
            findings=ordered_findings,
            diagnostics=ordered_diagnostics,
            skipped_entries=skipped_entries,
        )
        return SupplyChainReport(
            schema_version="1.0",
            scan_id=uuid4().hex,
            record_id=record_id,
            root=str(root_path),
            catalog_digest=catalog.digest(),
            status=status,  # type: ignore[arg-type]
            verdict=verdict,  # type: ignore[arg-type]
            started_at=started_at,
            completed_at=completed_at,
            summary=ScanSummary(
                files_hashed=len(ordered_files),
                skipped_entries=skipped_entries,
                terminal=True,
            ),
            files=ordered_files,
            packages=ordered_packages,
            dependencies=ordered_dependencies,
            findings=ordered_findings,
            diagnostics=ordered_diagnostics,
        )


def _read_and_hash_without_following_symlinks(
    path: Path,
    expected_stat: os.stat_result,
) -> tuple[str, bytes]:
    """Read one regular file through an fd that rejects a replaced symlink."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        stat_before = os.fstat(descriptor)
        if not stat.S_ISREG(stat_before.st_mode):
            raise OSError("not a regular file")
        if not _same_file_version(expected_stat, stat_before):
            raise OSError("file changed while opening")
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            while chunk := stream.read(64 * 1024):
                digest.update(chunk)
                chunks.append(chunk)
        if not _same_file_version(stat_before, os.fstat(descriptor)):
            raise OSError("file changed while reading")
        return digest.hexdigest(), b"".join(chunks)
    finally:
        os.close(descriptor)


def _same_file_version(first: os.stat_result, second: os.stat_result) -> bool:
    """Reject an observation if its path changed between lstat and fd reads."""

    return (
        first.st_dev,
        first.st_ino,
        first.st_size,
        first.st_mtime_ns,
    ) == (
        second.st_dev,
        second.st_ino,
        second.st_size,
        second.st_mtime_ns,
    )


def _parse_package_json(
    relative: str,
    content: bytes,
    packages: list[PackageRecord],
    dependencies: list[DependencyRecord],
    findings: list[Finding],
) -> None:
    document = json.loads(content.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("package.json root must be an object")
    name = document.get("name")
    version = document.get("version")
    if isinstance(name, str):
        packages.append(
            PackageRecord(
                ecosystem="npm",
                name=name,
                version=version if isinstance(version, str) else None,
                source_manifest=relative,
            )
        )
    for source_key, scope in _NPM_SCOPES.items():
        declared = document.get(source_key, {})
        if declared is None:
            declared = {}
        elif not isinstance(declared, dict):
            raise ValueError(f"{source_key} must be an object")
        for package_name, requested_version in declared.items():
            if not isinstance(package_name, str) or not isinstance(requested_version, str):
                raise ValueError(f"{source_key} entries must be string pairs")
            dependencies.append(
                DependencyRecord(
                    ecosystem="npm",
                    name=package_name,
                    requested_version=requested_version,
                    scope=scope,
                    source_manifest=relative,
                )
            )
    scripts = document.get("scripts", {})
    if scripts is None:
        scripts = {}
    elif not isinstance(scripts, dict):
        raise ValueError("scripts must be an object")
    for script_name in sorted(scripts):
        if script_name in _NPM_LIFECYCLE_SCRIPTS:
            findings.append(
                Finding(
                    code="npm_lifecycle_script",
                    path=relative,
                    detail=script_name,
                    severity="high",
                    indicator_id=None,
                    package_name=None,
                )
            )


def _parse_pyproject(
    relative: str,
    content: bytes,
    packages: list[PackageRecord],
    dependencies: list[DependencyRecord],
) -> None:
    document = tomllib.loads(content.decode("utf-8"))
    project = document.get("project", {})
    if project is not None and not isinstance(project, dict):
        raise ValueError("[project] must be a table")
    if not project:
        return
    name = project.get("name")
    version = project.get("version")
    if isinstance(name, str):
        packages.append(
            PackageRecord(
                ecosystem="python",
                name=_normalize_package_name("python", name),
                version=version if isinstance(version, str) else None,
                source_manifest=relative,
            )
        )
    _append_python_dependencies(
        project.get("dependencies", []),
        "runtime",
        relative,
        dependencies,
    )
    optional = project.get("optional-dependencies", {})
    if optional is None:
        optional = {}
    elif not isinstance(optional, dict):
        raise ValueError("optional-dependencies must be a table")
    for group, declared in optional.items():
        _append_python_dependencies(
            declared,
            f"optional:{group}",
            relative,
            dependencies,
        )


def _append_python_dependencies(
    declared: object,
    scope: str,
    relative: str,
    dependencies: list[DependencyRecord],
) -> None:
    if declared is None:
        return
    if not isinstance(declared, list) or not all(isinstance(item, str) for item in declared):
        raise ValueError("Python dependencies must be a string list")
    for entry in declared:
        parsed = _parse_python_requirement(entry)
        if parsed is None:
            raise ValueError("invalid Python dependency")
        name, requested_version = parsed
        dependencies.append(
            DependencyRecord(
                ecosystem="python",
                name=name,
                requested_version=requested_version,
                scope=scope,
                source_manifest=relative,
            )
        )


def _parse_requirements(
    relative: str,
    content: bytes,
    dependencies: list[DependencyRecord],
) -> None:
    for raw_line in content.decode("utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-", "--")):
            continue
        parsed = _parse_python_requirement(line)
        if parsed is None:
            raise ValueError("invalid requirements entry")
        name, requested_version = parsed
        dependencies.append(
            DependencyRecord(
                ecosystem="python",
                name=name,
                requested_version=requested_version,
                scope="development" if "dev" in Path(relative).stem else "runtime",
                source_manifest=relative,
            )
        )


def _parse_python_requirement(entry: str) -> tuple[str, str] | None:
    match = _PYTHON_NAME.match(entry.strip())
    if not match:
        return None
    name, requested_version = match.groups()
    return _normalize_package_name("python", name), requested_version.strip()


def _parse_go_mod(
    relative: str,
    content: bytes,
    packages: list[PackageRecord],
    dependencies: list[DependencyRecord],
) -> None:
    module_seen = False
    in_require_block = False
    for raw_line in content.decode("utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("module "):
            module_name = line.removeprefix("module ").strip()
            if not module_name or " " in module_name:
                raise ValueError("invalid module declaration")
            packages.append(
                PackageRecord(
                    ecosystem="go",
                    name=module_name,
                    version=None,
                    source_manifest=relative,
                )
            )
            module_seen = True
            continue
        if line.startswith("go ") or line.startswith("toolchain "):
            continue
        if line == "require (":
            if in_require_block:
                raise ValueError("nested require block")
            in_require_block = True
            continue
        if line == ")":
            if not in_require_block:
                raise ValueError("unexpected close")
            in_require_block = False
            continue
        requirement = line.removeprefix("require ").strip() if line.startswith("require ") else line
        if in_require_block or line.startswith("require "):
            match = _GO_REQUIRE.fullmatch(requirement)
            if not match:
                raise ValueError("invalid require declaration")
            package_name, requested_version = match.groups()
            scope = "indirect" if "// indirect" in requirement else "direct"
            dependencies.append(
                DependencyRecord(
                    ecosystem="go",
                    name=package_name,
                    requested_version=requested_version,
                    scope=scope,
                    source_manifest=relative,
                )
            )
            continue
        raise ValueError("unrecognized go.mod declaration")
    if in_require_block:
        raise ValueError("unterminated require block")
    if not module_seen:
        raise ValueError("go.mod has no module declaration")


def _is_manifest(filename: str) -> bool:
    return filename in {"package.json", "pyproject.toml", "go.mod"} or (
        filename.startswith("requirements") and filename.endswith(".txt")
    )


def _normalize_package_name(ecosystem: str, package_name: str) -> str:
    normalized = package_name.strip().lower()
    if ecosystem.lower() == "python":
        return re.sub(r"[-_.]+", "-", normalized)
    return normalized


def _empty_catalog() -> IndicatorCatalog:
    return IndicatorCatalog(
        schema_version="1.0",
        source="atlas-default",
        provenance="built-in empty catalog",
        indicators=[],
    )


def _verdict(status: str, findings: Iterable[Finding]) -> str:
    if status != "complete":
        return "block"
    all_findings = list(findings)
    if any(
        finding.code in {"symlink", "npm_lifecycle_script", "malformed_manifest"}
        or finding.severity in {"high", "critical"}
        for finding in all_findings
    ):
        return "block"
    if any(finding.severity == "medium" for finding in all_findings):
        return "review"
    return "admit"


def _record_id(
    *,
    catalog_digest: str,
    status: str,
    verdict: str,
    files: list[FileRecord],
    packages: list[PackageRecord],
    dependencies: list[DependencyRecord],
    findings: list[Finding],
    diagnostics: list[Diagnostic],
    skipped_entries: int,
) -> str:
    payload = {
        "schema_version": "1.0",
        "catalog_digest": catalog_digest,
        "status": status,
        "verdict": verdict,
        "summary": {
            "files_hashed": len(files),
            "skipped_entries": skipped_entries,
            "terminal": True,
        },
        "files": [item.model_dump(mode="json") for item in files],
        "packages": [item.model_dump(mode="json") for item in packages],
        "dependencies": [item.model_dump(mode="json") for item in dependencies],
        "findings": [item.model_dump(mode="json") for item in findings],
        "diagnostics": [item.model_dump(mode="json") for item in diagnostics],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
