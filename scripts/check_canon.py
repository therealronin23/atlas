#!/usr/bin/env python3
"""Fail-fast integrity gate for the Atlas Definitive Candidate.

This command validates machine-readable relationships. It deliberately does
not try to approve human prose or promote the candidate to accepted canon.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent

ROOT_DOCS = (
    "ATLAS.md",
    "VISION.md",
    "ARCHITECTURE.md",
    "PROGRAMS.md",
    "PLAN.md",
    "STATUS.md",
)
JSONL_REGISTRIES = (
    "source_registry.jsonl",
    "decision_registry.jsonl",
    "conflict_registry.jsonl",
    "supersession_registry.jsonl",
    "component_registry.jsonl",
    "capability_registry.jsonl",
    "contract_registry.jsonl",
    "open_questions.jsonl",
    "component_reality_matrix.jsonl",
    "product_lineage_registry.jsonl",
)
PERMANENT_PROGRAMS = {f"P{i:02d}" for i in range(13)}
REALITY_STATES = {
    "MISSING",
    "HISTORICAL",
    "RESEARCH",
    "PROPOSED_DESIGN",
    "ACCEPTED_DESIGN",
    "PROTOTYPE",
    "VALIDATION_HARNESS",
    "CODE_PRESENT",
    "TESTED",
    "WIRED",
    "RUNTIME_CONFIGURED",
    "LIVE_VERIFIED",
    "PRODUCT_ACCEPTED",
    "PARKED",
    "SUPERSEDED",
    "CONTRADICTED",
}
WORK_ORDER_STATES = {
    "READY",
    "BLOCKED",
    "REQUIRES_OPERATOR",
    "SUPERSEDED",
    "REJECTED",
    "DONE",
}
CONFLICT_RESOLUTION_STATES = {
    "RESOLVED",
    "ELEVATED_TO_PROGRAM",
    "ELEVATED_TO_OPERATOR",
    "SUPERSEDED",
}
WORK_ORDER_FIELDS = {
    "id",
    "program",
    "title",
    "problem",
    "evidence",
    "source_decisions",
    "current_state",
    "target_state",
    "scope",
    "files",
    "tests",
    "risks",
    "rollback",
    "dependencies",
    "acceptance",
    "operator_decision_required",
    "status",
}
LINEAGE_FIELDS = {
    "id",
    "name",
    "kind",
    "path_hint",
    "branch",
    "head",
    "upstream",
    "authority",
    "capabilities",
    "disposition",
    "target_cut",
    "evidence",
}
LINEAGE_DISPOSITIONS = {
    "CANONICAL_TARGET",
    "ALREADY_INTEGRATED",
    "PORT_SOURCE",
    "HOST_BASELINE",
    "PATTERN_DONOR",
    "RESEARCH_REFERENCE",
    "HISTORICAL_PRECURSOR",
    "SUPERSEDED",
}


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    message: str


def _yaml(path: Path, root: Path, findings: list[Finding]) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        findings.append(
            Finding("INVALID_YAML", _relative(path, root), f"cannot parse YAML: {exc}")
        )
        return None


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _jsonl(
    path: Path, root: Path, findings: list[Finding]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ids: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        findings.append(
            Finding("INVALID_JSONL", _relative(path, root), f"cannot read JSONL: {exc}")
        )
        return rows

    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            findings.append(
                Finding(
                    "INVALID_JSONL",
                    f"{_relative(path, root)}:{lineno}",
                    f"cannot parse JSON object: {exc.msg}",
                )
            )
            continue
        if not isinstance(row, dict):
            findings.append(
                Finding(
                    "INVALID_JSONL",
                    f"{_relative(path, root)}:{lineno}",
                    "each line must be a JSON object",
                )
            )
            continue
        # The immutable R2.1 source ledger intentionally reuses ``source_id``
        # for equal/derived content across archive occurrences. Its record
        # identity is therefore the occurrence, not the content id.
        if path.name == "source_registry.jsonl" and "id" not in row:
            source_id = row.get("source_id")
            archive = row.get("archive")
            member = row.get("member", row.get("preserved_path"))
            record_id = (
                f"{source_id}:{archive}:{member}"
                if isinstance(source_id, str) and source_id
                else None
            )
        else:
            record_id = row.get("id")
        if not isinstance(record_id, str) or not record_id:
            findings.append(
                Finding(
                    "MISSING_ID",
                    f"{_relative(path, root)}:{lineno}",
                    "record has no non-empty string id",
                )
            )
        elif record_id in ids:
            findings.append(
                Finding(
                    "DUPLICATE_ID",
                    f"{_relative(path, root)}:{lineno}",
                    f"duplicate id {record_id}",
                )
            )
        else:
            ids.add(record_id)
        rows.append(row)
    return rows


def _program_of(row: dict[str, Any]) -> str | None:
    value = row.get("program", row.get("program_primary"))
    return value if isinstance(value, str) else None


def _validate_program_reference(
    row: dict[str, Any], registry_name: str, findings: list[Finding]
) -> None:
    program = _program_of(row)
    if program is not None and program not in PERMANENT_PROGRAMS:
        findings.append(
            Finding(
                "INVALID_PROGRAM",
                registry_name,
                f"{row.get('id', '<unknown>')} references {program!r}",
            )
        )


def _has_live_evidence(runtime: Any) -> bool:
    if not isinstance(runtime, list):
        return False
    for evidence in runtime:
        if not isinstance(evidence, dict):
            continue
        if evidence.get("kind") != "live_runtime" or evidence.get("result") != "pass":
            continue
        observed_at = evidence.get("observed_at")
        if not isinstance(observed_at, str):
            continue
        try:
            observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                observed = date.fromisoformat(observed_at)
            except ValueError:
                continue
        if observed <= date.today():
            return True
    return False


def _validate_critical_decisions(
    rows: list[dict[str, Any]], findings: list[Finding]
) -> None:
    by_id = {
        row["id"]: row
        for row in rows
        if isinstance(row.get("id"), str) and row["id"]
    }
    required = {
        "ADR-076-A",
        "ADR-076-B",
        "ADR-076-C",
        "ADR-077-A",
        "ADR-077-B",
        "ADR-077-C",
        "ADR-077-D",
        "ADR-077-BOUNDARY",
    }
    for decision_id in sorted(required - set(by_id)):
        findings.append(
            Finding(
                "MISSING_CRITICAL_DECISION",
                "docs/canon/decision_registry.jsonl",
                f"missing atomic decision {decision_id}",
            )
        )

    expected_fields = {
        "ADR-076-A": {
            "disposition": "ACCEPTED",
            "implementation": "CODE_PRESENT",
            "activation": "OPT_IN",
        },
        "ADR-076-B": {
            "disposition": "ACCEPTED",
            "implementation": "CODE_PRESENT",
            "activation": "OPT_IN",
        },
        "ADR-076-C": {
            "disposition": "REJECTED",
            "implementation": "NOT_IMPLEMENTED",
            "activation": "ABSENT",
        },
        "ADR-077-A": {
            "disposition": "ACCEPTED",
            "implementation": "CODE_PRESENT",
            "activation": "OPT_IN",
        },
        "ADR-077-B": {
            "disposition": "ACCEPTED",
            "implementation": "RUNTIME_CONFIGURED",
            "activation": "OPT_IN_DEFAULT_OFF",
            "live_verified": False,
        },
        "ADR-077-C": {
            "disposition": "ACCEPTED_LIMITATION",
            "implementation": "NOT_IMPLEMENTED",
            "activation": "ABSENT",
        },
        "ADR-077-D": {
            "disposition": "ACCEPTED_LIMITATION",
            "implementation": "CODE_PRESENT",
            "activation": "HUMAN_COMMAND",
        },
    }
    for decision_id, expected in expected_fields.items():
        row = by_id.get(decision_id)
        if row is None:
            continue
        drift = {
            key: (row.get(key), value)
            for key, value in expected.items()
            if row.get(key) != value
        }
        if drift:
            details = ", ".join(
                f"{key}={actual!r} (expected {wanted!r})"
                for key, (actual, wanted) in sorted(drift.items())
            )
            findings.append(
                Finding(
                    "CRITICAL_DECISION_DRIFT",
                    "docs/canon/decision_registry.jsonl",
                    f"{decision_id}: {details}",
                )
            )

    boundary = by_id.get("ADR-077-BOUNDARY", {})
    constraints = boundary.get("constraints", [])
    required_constraints = {
        "HIGH_SENSITIVITY_REQUIRES_HUMAN_OR_DENY",
        "ADR_076_C_REMAINS_REJECTED",
    }
    actual_constraints = set(constraints) if isinstance(constraints, list) else set()
    missing = required_constraints - actual_constraints
    if missing:
        findings.append(
            Finding(
                "ADR_077_BOUNDARY_WEAKENED",
                "docs/canon/decision_registry.jsonl",
                "ADR-077-BOUNDARY is missing constraints: " + ", ".join(sorted(missing)),
            )
        )

def _validate_supersessions(
    rows: list[dict[str, Any]], findings: list[Finding]
) -> None:
    required = {
        "previous",
        "new",
        "scope",
        "date",
        "authority",
        "preserved",
        "annulled",
    }
    for row in rows:
        missing = sorted(key for key in required if key not in row)
        if missing:
            findings.append(
                Finding(
                    "INCOMPLETE_SUPERSESSION",
                    "docs/canon/supersession_registry.jsonl",
                    f"{row.get('id', '<unknown>')} missing: {', '.join(missing)}",
                )
            )


def _validate_adr_coverage(
    root: Path, rows: list[dict[str, Any]], findings: list[Finding]
) -> None:
    referenced_paths: set[str] = set()
    for row in rows:
        direct_path = row.get("path")
        if isinstance(direct_path, str):
            referenced_paths.add(direct_path)
        sources = row.get("sources")
        if not isinstance(sources, list):
            continue
        for source in sources:
            if not isinstance(source, dict):
                continue
            member = source.get("member")
            if isinstance(member, str):
                referenced_paths.add(member)

    adr_dir = root / "docs" / "decisions" / "adr"
    if not adr_dir.is_dir():
        return
    for adr_path in sorted(adr_dir.glob("*.md")):
        relative = _relative(adr_path, root)
        if relative not in referenced_paths:
            findings.append(
                Finding(
                    "MISSING_ADR_DISPOSITION",
                    relative,
                    f"{adr_path.name} has no decision-registry disposition",
                )
            )


def _validate_conflicts(
    rows: list[dict[str, Any]], findings: list[Finding]
) -> None:
    for row in rows:
        resolution_status = row.get("resolution_status")
        owner = row.get("resolution_owner")
        note = row.get("resolution_note")
        if (
            resolution_status not in CONFLICT_RESOLUTION_STATES
            or not isinstance(owner, str)
            or not owner
            or not isinstance(note, str)
            or not note.strip()
        ):
            findings.append(
                Finding(
                    "UNOWNED_CONFLICT",
                    "docs/canon/conflict_registry.jsonl",
                    f"{row.get('id', '<unknown>')} must be resolved or explicitly elevated",
                )
            )


def _validate_matrix_evidence(
    root: Path,
    row: dict[str, Any],
    statuses: list[Any],
    findings: list[Finding],
) -> None:
    record_id = str(row.get("id", "<unknown>"))
    requirements = {
        "CODE_PRESENT": "code",
        "TESTED": "tests",
        "RUNTIME_CONFIGURED": "configuration",
    }
    for state, field_name in requirements.items():
        evidence = row.get(field_name)
        if state in statuses and (not isinstance(evidence, list) or not evidence):
            findings.append(
                Finding(
                    "MISSING_STATE_EVIDENCE",
                    "docs/canon/component_reality_matrix.jsonl",
                    f"{record_id}: {state} requires non-empty {field_name} evidence",
                )
            )

    for field_name in ("code", "tests", "documentation"):
        evidence = row.get(field_name, [])
        if not isinstance(evidence, list):
            findings.append(
                Finding(
                    "INVALID_EVIDENCE_LIST",
                    "docs/canon/component_reality_matrix.jsonl",
                    f"{record_id}: {field_name} must be a list",
                )
            )
            continue
        for value in evidence:
            if not isinstance(value, str) or not value:
                findings.append(
                    Finding(
                        "INVALID_EVIDENCE_PATH",
                        "docs/canon/component_reality_matrix.jsonl",
                        f"{record_id}: invalid {field_name} evidence {value!r}",
                    )
                )
                continue
            candidate = Path(value)
            if candidate.is_absolute() or ".." in candidate.parts or not (root / candidate).exists():
                findings.append(
                    Finding(
                        "MISSING_EVIDENCE_PATH",
                        "docs/canon/component_reality_matrix.jsonl",
                        f"{record_id}: {field_name} path does not exist: {value}",
                    )
                )


def _validate_implementation_registry(
    data: Any, findings: list[Finding]
) -> None:
    path = "docs/canon/implementation_registry.yaml"
    if not isinstance(data, dict):
        return
    if data.get("candidate") != "ATLAS_DEFINITIVE_CANDIDATE":
        findings.append(
            Finding(
                "INVALID_CANDIDATE",
                path,
                "candidate must be ATLAS_DEFINITIVE_CANDIDATE",
            )
        )
    work_orders = data.get("work_orders")
    if not isinstance(work_orders, list):
        findings.append(Finding("INVALID_WORK_ORDERS", path, "work_orders must be a list"))
        return
    ids: set[str] = set()
    for index, item in enumerate(work_orders):
        if not isinstance(item, dict):
            findings.append(
                Finding("INVALID_WORK_ORDER", path, f"work_orders[{index}] is not a map")
            )
            continue
        missing = sorted(WORK_ORDER_FIELDS - item.keys())
        if missing:
            findings.append(
                Finding(
                    "INCOMPLETE_WORK_ORDER",
                    path,
                    f"{item.get('id', index)} missing: {', '.join(missing)}",
                )
            )
        work_id = item.get("id")
        if isinstance(work_id, str):
            if work_id in ids:
                findings.append(
                    Finding("DUPLICATE_WORK_ORDER", path, f"duplicate id {work_id}")
                )
            ids.add(work_id)
        status = item.get("status")
        if status not in WORK_ORDER_STATES:
            findings.append(
                Finding(
                    "INVALID_WORK_ORDER_STATE",
                    path,
                    f"{work_id or index} has invalid status {status!r}",
                )
            )
        _validate_program_reference(item, path, findings)


def _validate_product_lineages(
    rows: list[dict[str, Any]], findings: list[Finding]
) -> None:
    path = "docs/canon/product_lineage_registry.jsonl"
    canonical_targets: list[str] = []
    for row in rows:
        record_id = str(row.get("id", "<unknown>"))
        missing = sorted(LINEAGE_FIELDS - row.keys())
        if missing:
            findings.append(
                Finding(
                    "INCOMPLETE_LINEAGE",
                    path,
                    f"{record_id} missing: {', '.join(missing)}",
                )
            )
        head = row.get("head")
        if (
            not isinstance(head, str)
            or len(head) != 40
            or any(char not in "0123456789abcdef" for char in head.lower())
        ):
            findings.append(
                Finding(
                    "INVALID_LINEAGE_HEAD",
                    path,
                    f"{record_id} needs an exact 40-character Git commit",
                )
            )
        disposition = row.get("disposition")
        if disposition not in LINEAGE_DISPOSITIONS:
            findings.append(
                Finding(
                    "INVALID_LINEAGE_DISPOSITION",
                    path,
                    f"{record_id} has unknown disposition {disposition!r}",
                )
            )
        if disposition == "CANONICAL_TARGET":
            canonical_targets.append(record_id)
            if row.get("authority") != "CANONICAL_REPOSITORY":
                findings.append(
                    Finding(
                        "INVALID_CANONICAL_LINEAGE",
                        path,
                        f"{record_id} cannot be CANONICAL_TARGET without CANONICAL_REPOSITORY authority",
                    )
                )
        elif row.get("authority") == "CANONICAL_REPOSITORY":
            findings.append(
                Finding(
                    "INVALID_CANONICAL_LINEAGE",
                    path,
                    f"{record_id} claims canonical authority without CANONICAL_TARGET disposition",
                )
            )
        for field_name in ("name", "kind", "path_hint", "target_cut"):
            value = row.get(field_name)
            if not isinstance(value, str) or not value.strip():
                findings.append(
                    Finding(
                        "INVALID_LINEAGE_FIELD",
                        path,
                        f"{record_id} needs a non-empty {field_name}",
                    )
                )
        for field_name in ("branch", "upstream"):
            value = row.get(field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                findings.append(
                    Finding(
                        "INVALID_LINEAGE_FIELD",
                        path,
                        f"{record_id} {field_name} must be a non-empty string or null",
                    )
                )
        capabilities = row.get("capabilities")
        if not isinstance(capabilities, list) or not all(
            isinstance(item, str) and item for item in capabilities
        ):
            findings.append(
                Finding(
                    "INVALID_LINEAGE_CAPABILITIES",
                    path,
                    f"{record_id} capabilities must be a list of strings",
                )
            )
        evidence = row.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            findings.append(
                Finding(
                    "MISSING_LINEAGE_EVIDENCE",
                    path,
                    f"{record_id} needs source evidence",
                )
            )
            continue
        for item in evidence:
            if (
                isinstance(item, dict)
                and item.get("kind") == "live_runtime"
                and "path" in item
            ):
                findings.append(
                    Finding(
                        "LINEAGE_PATH_IS_NOT_RUNTIME_EVIDENCE",
                        path,
                        f"{record_id} presents a checkout path as live runtime proof",
                    )
                )
    if len(canonical_targets) != 1:
        findings.append(
            Finding(
                "INVALID_CANONICAL_LINEAGE_COUNT",
                path,
                "exactly one CANONICAL_TARGET is required; found "
                + str(len(canonical_targets)),
            )
        )


def validate_repo(root: Path) -> tuple[list[Finding], int]:
    root = root.resolve()
    findings: list[Finding] = []
    canon = root / "docs" / "canon"

    for rel in ROOT_DOCS:
        if not (root / rel).is_file():
            findings.append(Finding("MISSING_ROOT_DOC", rel, "required candidate document"))

    authority_path = canon / "authority_registry.yaml"
    implementation_path = canon / "implementation_registry.yaml"
    for path in (authority_path, implementation_path):
        if not path.is_file():
            findings.append(
                Finding("MISSING_REGISTRY", _relative(path, root), "required YAML registry")
            )

    authority = (
        _yaml(authority_path, root, findings) if authority_path.is_file() else None
    )
    implementation = (
        _yaml(implementation_path, root, findings)
        if implementation_path.is_file()
        else None
    )
    if isinstance(authority, dict):
        if authority.get("candidate") != "ATLAS_DEFINITIVE_CANDIDATE":
            findings.append(
                Finding(
                    "INVALID_CANDIDATE",
                    "docs/canon/authority_registry.yaml",
                    "candidate must be ATLAS_DEFINITIVE_CANDIDATE",
                )
            )
        entrypoints = authority.get("entrypoints", {})
        if not isinstance(entrypoints, dict) or entrypoints.get("human") != "ATLAS.md":
            findings.append(
                Finding(
                    "INVALID_ENTRYPOINT",
                    "docs/canon/authority_registry.yaml",
                    "the single human entrypoint must be ATLAS.md",
                )
            )
        constitution = authority.get("constitution", {})
        if not isinstance(constitution, dict) or (
            constitution.get("mode") != "DISTRIBUTED"
            or constitution.get("decision") != "ADR-067"
        ):
            findings.append(
                Finding(
                    "CONSTITUTION_DUPLICATED",
                    "docs/canon/authority_registry.yaml",
                    "constitution must remain distributed under ADR-067",
                )
            )
        programs = authority.get("permanent_programs", [])
        actual = set(programs) if isinstance(programs, list) else set()
        if actual != PERMANENT_PROGRAMS or len(programs) != len(PERMANENT_PROGRAMS):
            missing = sorted(PERMANENT_PROGRAMS - actual)
            extra = sorted(actual - PERMANENT_PROGRAMS)
            findings.append(
                Finding(
                    "INVALID_PROGRAM_SET",
                    "docs/canon/authority_registry.yaml",
                    "permanent_programs must be exactly P00..P12"
                    + (f"; missing {', '.join(missing)}" if missing else "")
                    + (f"; extra {', '.join(extra)}" if extra else ""),
                )
            )
    _validate_implementation_registry(implementation, findings)

    registries: dict[str, list[dict[str, Any]]] = {}
    record_count = 0
    for name in JSONL_REGISTRIES:
        path = canon / name
        if not path.is_file():
            findings.append(
                Finding("MISSING_REGISTRY", _relative(path, root), "required JSONL registry")
            )
            registries[name] = []
            continue
        rows = _jsonl(path, root, findings)
        registries[name] = rows
        record_count += len(rows)
        for row in rows:
            _validate_program_reference(row, f"docs/canon/{name}", findings)

    _validate_critical_decisions(registries.get("decision_registry.jsonl", []), findings)
    _validate_adr_coverage(
        root, registries.get("decision_registry.jsonl", []), findings
    )
    _validate_conflicts(registries.get("conflict_registry.jsonl", []), findings)
    _validate_supersessions(
        registries.get("supersession_registry.jsonl", []), findings
    )
    _validate_product_lineages(
        registries.get("product_lineage_registry.jsonl", []), findings
    )

    component_ids = {
        row["id"]
        for row in registries.get("component_registry.jsonl", [])
        if isinstance(row.get("id"), str)
    }
    capability_ids = {
        row["id"]
        for row in registries.get("capability_registry.jsonl", [])
        if isinstance(row.get("id"), str)
    }
    expected_reality_ids = component_ids | capability_ids
    matrix_rows = registries.get("component_reality_matrix.jsonl", [])
    matrix_ids = {
        row["id"] for row in matrix_rows if isinstance(row.get("id"), str)
    }
    for record_id in sorted(expected_reality_ids - matrix_ids):
        findings.append(
            Finding(
                "MISSING_REALITY_RECORD",
                "docs/canon/component_reality_matrix.jsonl",
                f"{record_id} missing reality record",
            )
        )
    for record_id in sorted(matrix_ids - expected_reality_ids):
        findings.append(
            Finding(
                "ORPHAN_REALITY_RECORD",
                "docs/canon/component_reality_matrix.jsonl",
                f"{record_id} is not in component or capability registry",
            )
        )

    for row in matrix_rows:
        record_id = str(row.get("id", "<unknown>"))
        expected_type = (
            "component"
            if record_id in component_ids
            else "capability"
            if record_id in capability_ids
            else None
        )
        if expected_type and row.get("record_type") != expected_type:
            findings.append(
                Finding(
                    "REALITY_TYPE_MISMATCH",
                    "docs/canon/component_reality_matrix.jsonl",
                    f"{record_id} must have record_type {expected_type}",
                )
            )
        statuses = row.get("statuses")
        if not isinstance(statuses, list) or not statuses:
            findings.append(
                Finding(
                    "MISSING_REALITY_STATE",
                    "docs/canon/component_reality_matrix.jsonl",
                    f"{record_id} needs at least one status",
                )
            )
            continue
        _validate_matrix_evidence(root, row, statuses, findings)
        unknown = sorted({str(item) for item in statuses} - REALITY_STATES)
        if unknown:
            findings.append(
                Finding(
                    "INVALID_REALITY_STATE",
                    "docs/canon/component_reality_matrix.jsonl",
                    f"{record_id} uses unknown states: {', '.join(unknown)}",
                )
            )
        target = row.get("target_state")
        if target not in REALITY_STATES:
            findings.append(
                Finding(
                    "INVALID_TARGET_STATE",
                    "docs/canon/component_reality_matrix.jsonl",
                    f"{record_id} has invalid target_state {target!r}",
                )
            )
        next_action = row.get("next_action")
        if not isinstance(next_action, str) or not next_action.strip():
            findings.append(
                Finding(
                    "MISSING_NEXT_ACTION",
                    "docs/canon/component_reality_matrix.jsonl",
                    f"{record_id} needs a non-empty next_action",
                )
            )
        if "LIVE_VERIFIED" in statuses and not _has_live_evidence(row.get("runtime")):
            findings.append(
                Finding(
                    "UNSUPPORTED_LIVE_VERIFIED",
                    "docs/canon/component_reality_matrix.jsonl",
                    f"{record_id}: LIVE_VERIFIED requires dated passing live_runtime evidence",
                )
            )

    return findings, record_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="repository root to validate (defaults to the script checkout)",
    )
    args = parser.parse_args(argv)
    findings, record_count = validate_repo(args.root)
    if findings:
        print(f"canon integrity: FAIL ({len(findings)} findings)")
        for finding in findings:
            print(f"[{finding.code}] {finding.path}: {finding.message}")
        return 1
    print(f"canon integrity: PASS ({record_count} JSONL records)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
