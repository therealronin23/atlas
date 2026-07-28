"""Behavioral contract for the definitive canon integrity gate.

Each test runs the real command against an isolated miniature repository.
The gate protects relationships and evidence semantics, not prose wording.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_canon.py"
ROOT_DOCS = (
    "ATLAS.md",
    "VISION.md",
    "ARCHITECTURE.md",
    "PROGRAMS.md",
    "PLAN.md",
    "STATUS.md",
)
PROGRAMS = tuple(f"P{i:02d}" for i in range(13))
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


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _critical_decisions() -> list[dict[str, object]]:
    return [
        {
            "id": "ADR-076-A",
            "adr": "ADR-076",
            "part": "A",
            "disposition": "ACCEPTED",
            "implementation": "CODE_PRESENT",
            "activation": "OPT_IN",
        },
        {
            "id": "ADR-076-B",
            "adr": "ADR-076",
            "part": "B",
            "disposition": "ACCEPTED",
            "implementation": "CODE_PRESENT",
            "activation": "OPT_IN",
        },
        {
            "id": "ADR-076-C",
            "adr": "ADR-076",
            "part": "C",
            "disposition": "REJECTED",
            "implementation": "NOT_IMPLEMENTED",
            "activation": "ABSENT",
        },
        {
            "id": "ADR-077-A",
            "adr": "ADR-077",
            "part": "A",
            "disposition": "ACCEPTED",
            "implementation": "CODE_PRESENT",
            "activation": "OPT_IN",
        },
        {
            "id": "ADR-077-B",
            "adr": "ADR-077",
            "part": "B",
            "disposition": "ACCEPTED",
            "implementation": "RUNTIME_CONFIGURED",
            "activation": "OPT_IN_DEFAULT_OFF",
            "live_verified": False,
        },
        {
            "id": "ADR-077-C",
            "adr": "ADR-077",
            "part": "C",
            "disposition": "ACCEPTED_LIMITATION",
            "implementation": "NOT_IMPLEMENTED",
            "activation": "ABSENT",
        },
        {
            "id": "ADR-077-D",
            "adr": "ADR-077",
            "part": "D",
            "disposition": "ACCEPTED_LIMITATION",
            "implementation": "CODE_PRESENT",
            "activation": "HUMAN_COMMAND",
        },
        {
            "id": "ADR-077-BOUNDARY",
            "adr": "ADR-077",
            "part": "BOUNDARY",
            "disposition": "ACCEPTED",
            "implementation": "NOT_APPLICABLE",
            "activation": "NOT_APPLICABLE",
            "constraints": [
                "HIGH_SENSITIVITY_REQUIRES_HUMAN_OR_DENY",
                "ADR_076_C_REMAINS_REJECTED",
            ],
        },
    ]


def _product_lineages() -> list[dict[str, object]]:
    return [
        {
            "id": "LINEAGE-CANONICAL",
            "name": "Atlas definitive candidate",
            "kind": "repository",
            "path_hint": "~/atlas-definitive-convergence",
            "branch": "codex/atlas-definitive-convergence",
            "head": "a" * 40,
            "upstream": "therealronin23/atlas",
            "authority": "CANONICAL_REPOSITORY",
            "capabilities": ["definitive_candidate"],
            "disposition": "CANONICAL_TARGET",
            "target_cut": "CUT-0",
            "evidence": ["git rev-parse HEAD"],
        },
        {
            "id": "LINEAGE-DONOR",
            "name": "Product donor",
            "kind": "repository",
            "path_hint": "~/atlas-donor",
            "branch": "main",
            "head": "b" * 40,
            "upstream": "upstream/donor",
            "authority": "UPSTREAM_REFERENCE",
            "capabilities": ["interaction_patterns"],
            "disposition": "PATTERN_DONOR",
            "target_cut": "CUT-2",
            "evidence": ["git rev-parse HEAD"],
        },
    ]


def _make_candidate(tmp_path: Path) -> Path:
    for name in ROOT_DOCS:
        (tmp_path / name).write_text(f"# {name}\n", encoding="utf-8")

    for relative in (
        "src/atlas/cli/reality.py",
        "src/atlas/logging/verify.py",
        "tests/test_reality.py",
        "tests/test_merkle.py",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# evidence fixture\n", encoding="utf-8")

    canon = tmp_path / "docs" / "canon"
    canon.mkdir(parents=True)
    adr_dir = tmp_path / "docs" / "decisions" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "adr_001_test.md").write_text(
        "# ADR-001 — Test decision\n", encoding="utf-8"
    )
    (canon / "implementation_registry.yaml").write_text(
        "schema_version: 1\ncandidate: ATLAS_DEFINITIVE_CANDIDATE\nwork_orders: []\n",
        encoding="utf-8",
    )
    programs_yaml = "\n".join(f"  - {program}" for program in PROGRAMS)
    (canon / "authority_registry.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "candidate: ATLAS_DEFINITIVE_CANDIDATE",
                f"compiled_at: {date.today().isoformat()}",
                "entrypoints:",
                "  human: ATLAS.md",
                "  machine: docs/canon/authority_registry.yaml",
                "constitution:",
                "  mode: DISTRIBUTED",
                "  decision: ADR-067",
                "permanent_programs:",
                programs_yaml,
                "",
            ]
        ),
        encoding="utf-8",
    )

    _write_jsonl(
        canon / "source_registry.jsonl",
        [{"id": "SRC-TEST", "disposition": "CURRENT", "path": "ATLAS.md"}],
    )
    _write_jsonl(
        canon / "decision_registry.jsonl",
        _critical_decisions()
        + [
            {
                "id": "ADR-001",
                "status": "ACCEPTED",
                "sources": [
                    {
                        "member": "docs/decisions/adr/adr_001_test.md",
                        "locator": "whole-file",
                    }
                ],
            }
        ],
    )
    _write_jsonl(
        canon / "conflict_registry.jsonl",
        [
            {
                "id": "CONFLICT-TEST",
                "status": "RESOLVED",
                "resolution_status": "RESOLVED",
                "resolution_owner": "P00",
                "resolution_note": "Primary evidence reconciled in the test fixture.",
                "resolution": "test",
            }
        ],
    )
    _write_jsonl(
        canon / "supersession_registry.jsonl",
        [
            {
                "id": "SUPERSESSION-TEST",
                "previous": "ADR-059",
                "new": "ADR-071",
                "scope": "final product UX only",
                "date": "2026-07-13",
                "authority": "operator accepted ADR",
                "preserved": ["web validation harness"],
                "annulled": ["web-first final UX"],
            }
        ],
    )
    _write_jsonl(
        canon / "component_registry.jsonl",
        [{"id": "CMP-REALITY", "program": "P00", "name": "Reality Kernel"}],
    )
    _write_jsonl(
        canon / "capability_registry.jsonl",
        [{"id": "CAP-AUDIT", "program": "P09", "name": "Audit verification"}],
    )
    _write_jsonl(
        canon / "contract_registry.jsonl",
        [
            {
                "id": "CONTRACT-EFFECTS",
                "program": "P09",
                "status": "ACCEPTED",
                "statement": "Every external effect is auditable.",
            }
        ],
    )
    _write_jsonl(
        canon / "open_questions.jsonl",
        [
            {
                "id": "OPEN-PRODUCT",
                "program": "P08",
                "status": "REQUIRES_OPERATOR",
                "question": "Which final dedicated shell?",
            }
        ],
    )
    _write_jsonl(
        canon / "component_reality_matrix.jsonl",
        [
            {
                "id": "CMP-REALITY",
                "record_type": "component",
                "program": "P00",
                "statuses": ["CODE_PRESENT", "TESTED"],
                "decision": ["ADR-067"],
                "code": ["src/atlas/cli/reality.py"],
                "tests": ["tests/test_reality.py"],
                "configuration": [],
                "documentation": ["ATLAS.md"],
                "runtime": [],
                "target_state": "PRODUCT_ACCEPTED",
                "next_action": "Keep validation current.",
            },
            {
                "id": "CAP-AUDIT",
                "record_type": "capability",
                "program": "P09",
                "statuses": ["CODE_PRESENT", "TESTED"],
                "decision": [],
                "code": ["src/atlas/logging/verify.py"],
                "tests": ["tests/test_merkle.py"],
                "configuration": [],
                "documentation": ["STATUS.md"],
                "runtime": [],
                "target_state": "LIVE_VERIFIED",
                "next_action": "Run a dated audit check.",
            },
        ],
    )
    _write_jsonl(
        canon / "product_lineage_registry.jsonl",
        _product_lineages(),
    )

    for name in JSONL_REGISTRIES:
        assert (canon / name).is_file()
    return tmp_path


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_valid_candidate_passes(tmp_path: Path) -> None:
    """Break caught: a coherent candidate must not be rejected by its gate."""
    result = _run(_make_candidate(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "canon integrity: PASS" in result.stdout


def test_unknown_reality_state_fails_with_record_id(tmp_path: Path) -> None:
    """Break caught: an invented status can otherwise create false reality."""
    root = _make_candidate(tmp_path)
    matrix = root / "docs" / "canon" / "component_reality_matrix.jsonl"
    rows = [json.loads(line) for line in matrix.read_text(encoding="utf-8").splitlines()]
    rows[0]["statuses"] = ["MAGICALLY_LIVE"]
    _write_jsonl(matrix, rows)

    result = _run(root)
    assert result.returncode == 1
    assert "CMP-REALITY" in result.stdout
    assert "MAGICALLY_LIVE" in result.stdout


def test_live_verified_requires_dated_passing_runtime_evidence(tmp_path: Path) -> None:
    """Break caught: config or a test must never masquerade as a live check."""
    root = _make_candidate(tmp_path)
    matrix = root / "docs" / "canon" / "component_reality_matrix.jsonl"
    rows = [json.loads(line) for line in matrix.read_text(encoding="utf-8").splitlines()]
    rows[1]["statuses"] = ["CODE_PRESENT", "TESTED", "LIVE_VERIFIED"]
    rows[1]["runtime"] = [{"kind": "configuration", "result": "pass"}]
    _write_jsonl(matrix, rows)

    result = _run(root)
    assert result.returncode == 1
    assert "CAP-AUDIT" in result.stdout
    assert "LIVE_VERIFIED requires" in result.stdout


def test_every_registered_component_and_capability_needs_reality_record(
    tmp_path: Path,
) -> None:
    """Break caught: registry additions cannot disappear from status reporting."""
    root = _make_candidate(tmp_path)
    _write_jsonl(
        root / "docs" / "canon" / "capability_registry.jsonl",
        [
            {"id": "CAP-AUDIT", "program": "P09", "name": "Audit verification"},
            {"id": "CAP-ORPHAN", "program": "P03", "name": "Unclassified capability"},
        ],
    )

    result = _run(root)
    assert result.returncode == 1
    assert "CAP-ORPHAN" in result.stdout
    assert "missing reality record" in result.stdout


def test_critical_rejected_and_human_control_boundaries_are_enforced(
    tmp_path: Path,
) -> None:
    """Break caught: canon cannot silently reopen ADR-076 C or weaken rule 4."""
    root = _make_candidate(tmp_path)
    registry = root / "docs" / "canon" / "decision_registry.jsonl"
    rows = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines()]
    for row in rows:
        if row["id"] == "ADR-076-C":
            row["disposition"] = "ACCEPTED"
            row["implementation"] = "CODE_PRESENT"
        if row["id"] == "ADR-077-BOUNDARY":
            row["constraints"] = []
    _write_jsonl(registry, rows)

    result = _run(root)
    assert result.returncode == 1
    assert "ADR-076-C" in result.stdout
    assert "ADR-077-BOUNDARY" in result.stdout


def test_permanent_program_set_cannot_be_replaced_by_waves(tmp_path: Path) -> None:
    """Break caught: omitting a permanent line silently erases architecture."""
    root = _make_candidate(tmp_path)
    authority = root / "docs" / "canon" / "authority_registry.yaml"
    authority.write_text(
        authority.read_text(encoding="utf-8").replace("  - P12\n", ""),
        encoding="utf-8",
    )

    result = _run(root)
    assert result.returncode == 1
    assert "permanent_programs" in result.stdout
    assert "P12" in result.stdout


def test_every_repository_adr_needs_an_explicit_decision_disposition(
    tmp_path: Path,
) -> None:
    """Break caught: an ADR file cannot silently disappear from canon."""
    root = _make_candidate(tmp_path)
    missing = root / "docs" / "decisions" / "adr" / "adr_002_missing.md"
    missing.write_text("# ADR-002 — Missing disposition\n", encoding="utf-8")

    result = _run(root)
    assert result.returncode == 1
    assert "adr_002_missing.md" in result.stdout
    assert "has no decision-registry disposition" in result.stdout


def test_every_conflict_is_resolved_or_explicitly_elevated(tmp_path: Path) -> None:
    """Break caught: imported conflicts cannot remain an unowned ambiguity pile."""
    root = _make_candidate(tmp_path)
    conflicts = root / "docs" / "canon" / "conflict_registry.jsonl"
    rows = [
        json.loads(line)
        for line in conflicts.read_text(encoding="utf-8").splitlines()
    ]
    rows[0].pop("resolution_status")
    _write_jsonl(conflicts, rows)

    result = _run(root)
    assert result.returncode == 1
    assert "CONFLICT-TEST" in result.stdout
    assert "resolved or explicitly elevated" in result.stdout


def test_code_and_test_states_require_existing_repository_evidence(
    tmp_path: Path,
) -> None:
    """Break caught: state labels cannot point to invented files."""
    root = _make_candidate(tmp_path)
    matrix = root / "docs" / "canon" / "component_reality_matrix.jsonl"
    rows = [json.loads(line) for line in matrix.read_text(encoding="utf-8").splitlines()]
    rows[0]["code"] = ["src/atlas/does_not_exist.py"]
    rows[1]["tests"] = []
    _write_jsonl(matrix, rows)

    result = _run(root)
    assert result.returncode == 1
    assert "src/atlas/does_not_exist.py" in result.stdout
    assert "CAP-AUDIT" in result.stdout
    assert "TESTED requires" in result.stdout


def test_runtime_configured_requires_explicit_configuration_evidence(
    tmp_path: Path,
) -> None:
    """Break caught: wiring cannot masquerade as observed configuration."""
    root = _make_candidate(tmp_path)
    matrix = root / "docs" / "canon" / "component_reality_matrix.jsonl"
    rows = [json.loads(line) for line in matrix.read_text(encoding="utf-8").splitlines()]
    rows[0]["statuses"].append("RUNTIME_CONFIGURED")
    rows[0]["configuration"] = []
    _write_jsonl(matrix, rows)

    result = _run(root)
    assert result.returncode == 1
    assert "CMP-REALITY" in result.stdout
    assert "RUNTIME_CONFIGURED requires" in result.stdout


def test_all_atomic_adr_076_077_dispositions_are_exact(tmp_path: Path) -> None:
    """Break caught: accepted, limited and human-only parts cannot drift."""
    root = _make_candidate(tmp_path)
    registry = root / "docs" / "canon" / "decision_registry.jsonl"
    rows = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines()]
    mutations = {
        "ADR-076-A": ("activation", "DEFAULT_ON"),
        "ADR-077-A": ("implementation", "NOT_IMPLEMENTED"),
        "ADR-077-C": ("implementation", "CODE_PRESENT"),
        "ADR-077-D": ("activation", "AUTONOMOUS"),
    }
    for row in rows:
        if row["id"] in mutations:
            key, value = mutations[row["id"]]
            row[key] = value
    _write_jsonl(registry, rows)

    result = _run(root)
    assert result.returncode == 1
    for decision_id in mutations:
        assert decision_id in result.stdout


def test_product_lineage_ids_must_be_unique(tmp_path: Path) -> None:
    """Break caught: two physical sources cannot collapse into one lineage ID."""
    root = _make_candidate(tmp_path)
    registry = root / "docs" / "canon" / "product_lineage_registry.jsonl"
    rows = _product_lineages()
    rows[1]["id"] = rows[0]["id"]
    _write_jsonl(registry, rows)

    result = _run(root)

    assert result.returncode == 1
    assert "DUPLICATE_ID" in result.stdout
    assert "LINEAGE-CANONICAL" in result.stdout


def test_product_lineage_requires_valid_head_and_disposition(tmp_path: Path) -> None:
    """Break caught: unverifiable commits and invented dispositions look authoritative."""
    root = _make_candidate(tmp_path)
    registry = root / "docs" / "canon" / "product_lineage_registry.jsonl"
    rows = _product_lineages()
    rows[0]["head"] = "short"
    rows[1]["disposition"] = "MAGIC_MERGE"
    _write_jsonl(registry, rows)

    result = _run(root)

    assert result.returncode == 1
    assert "INVALID_LINEAGE_HEAD" in result.stdout
    assert "INVALID_LINEAGE_DISPOSITION" in result.stdout


def test_only_canonical_repository_authority_can_be_target(tmp_path: Path) -> None:
    """Break caught: a donor cannot acquire canonical authority by relabelling."""
    root = _make_candidate(tmp_path)
    registry = root / "docs" / "canon" / "product_lineage_registry.jsonl"
    rows = _product_lineages()
    rows[0]["authority"] = "UPSTREAM_REFERENCE"
    _write_jsonl(registry, rows)

    result = _run(root)

    assert result.returncode == 1
    assert "INVALID_CANONICAL_LINEAGE" in result.stdout
    assert "LINEAGE-CANONICAL" in result.stdout


def test_lineage_path_cannot_be_presented_as_runtime_proof(tmp_path: Path) -> None:
    """Break caught: a checkout path proves presence, never live behavior."""
    root = _make_candidate(tmp_path)
    registry = root / "docs" / "canon" / "product_lineage_registry.jsonl"
    rows = _product_lineages()
    rows[1]["evidence"] = [
        {
            "kind": "live_runtime",
            "path": "/tmp/atlas-donor",
            "result": "pass",
        }
    ]
    _write_jsonl(registry, rows)

    result = _run(root)

    assert result.returncode == 1
    assert "LINEAGE_PATH_IS_NOT_RUNTIME_EVIDENCE" in result.stdout
    assert "LINEAGE-DONOR" in result.stdout
