"""Contract tests for the append-only Engineering Finding projection.

The production break these tests prevent is a review plane that either loses
its typed evidence/lifecycle or inflates the ledger by recording the same
review repeatedly.  The store deliberately receives only a journal path: a
finding may reference a patch but can never apply it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from atlas.core.self_audit import SelfAuditFinding
from atlas.engineering.findings import (
    EngineeringFinding,
    EngineeringFindingStore,
    FindingEvidence,
    FindingLocation,
    FindingSeverity,
    FindingStatus,
    from_self_audit_finding,
)


REPO = Path(__file__).resolve().parent.parent
FINDING_SCHEMA = json.loads(
    (REPO / "schemas" / "engineering_finding.schema.json").read_text(encoding="utf-8")
)


def _finding(
    *,
    finding_id: str = "finding_static_001",
    status: FindingStatus = FindingStatus.OPEN,
    dedupe_key: str = "atlas-core:abc123:ast-guard:src/atlas/core/example.py:7",
) -> EngineeringFinding:
    return EngineeringFinding(
        id=finding_id,
        run_id="run_review_001",
        task_id="task_001",
        repository="atlas-core",
        base_revision="a" * 40,
        candidate_revision="b" * 40,
        source="ast_guard",
        category="security",
        severity=FindingSeverity.MAJOR,
        status=status,
        summary="Generated import requires review",
        detail="The generated patch imports a disallowed module.",
        locations=(
            FindingLocation(
                path="src/atlas/core/example.py",
                start_line=7,
                end_line=7,
            ),
        ),
        evidence=(
            FindingEvidence(
                kind="test",
                reference="tests/test_verify.py::TestStaticCodeVerifier::test_fail_carries_violations",
                detail="AST Guard rejected the import.",
            ),
        ),
        reproduction="PYTHONPATH=src python -m pytest tests/test_verify.py -q",
        suggested_action="Remove the disallowed import before proposing a patch.",
        patch_ref="patches/candidate.diff",
        dedupe_key=dedupe_key,
        created_at="2026-07-29T09:00:00+00:00",
        updated_at="2026-07-29T09:00:00+00:00",
    )


def test_contract_matches_the_versioned_public_schema() -> None:
    finding = _finding()

    payload = json.loads(finding.model_dump_json())

    assert payload["schema_version"] == "1.0"
    assert payload["severity"] == "MAJOR"
    assert payload["status"] == "OPEN"
    assert payload["locations"] == [
        {"path": "src/atlas/core/example.py", "start_line": 7, "end_line": 7, "column": None}
    ]
    assert set(FINDING_SCHEMA["required"]) - {"schema_version"} == {
        name for name, field in EngineeringFinding.model_fields.items() if field.is_required()
    }
    assert set(FINDING_SCHEMA["properties"]) == set(EngineeringFinding.model_fields)


def test_contract_rejects_a_finding_without_a_stable_dedupe_key() -> None:
    data = _finding().model_dump()
    data["dedupe_key"] = ""

    with pytest.raises(ValidationError):
        EngineeringFinding.model_validate(data)


def test_store_deduplicates_a_repeat_review_without_applying_its_patch(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("safe = True\n", encoding="utf-8")
    store = EngineeringFindingStore(tmp_path / "engineering-findings.jsonl")
    original = _finding()
    repeat = _finding(finding_id="finding_static_repeat")

    recorded = store.record(original)
    duplicate = store.record(repeat)

    assert recorded.id == "finding_static_001"
    assert duplicate.id == "finding_static_001"
    assert store.count() == 1
    assert store.list() == [original]
    assert candidate.read_text(encoding="utf-8") == "safe = True\n"
    journal = [json.loads(line) for line in store.path.read_text(encoding="utf-8").splitlines()]
    assert [entry["event"] for entry in journal] == ["recorded"]


def test_status_transition_keeps_an_append_only_lifecycle_history(tmp_path: Path) -> None:
    store = EngineeringFindingStore(tmp_path / "engineering-findings.jsonl")
    store.record(_finding())

    updated = store.transition(
        "finding_static_001",
        FindingStatus.FIX_PROPOSED,
        reason="A governed proposal now references the finding.",
        at="2026-07-29T10:00:00+00:00",
    )

    assert updated.status is FindingStatus.FIX_PROPOSED
    assert updated.updated_at == "2026-07-29T10:00:00+00:00"
    history = store.history("finding_static_001")
    assert [entry.event for entry in history] == ["recorded", "status_changed"]
    assert history[0].finding.status is FindingStatus.OPEN
    assert history[-1].finding.status is FindingStatus.FIX_PROPOSED


def test_self_audit_adapter_projects_critical_evidence_without_rewriting_it() -> None:
    audit_finding = SelfAuditFinding(
        id="agents-missing",
        category="docs_drift",
        severity="critical",
        title="AGENTS.md missing",
        detail="The operating contract is absent.",
        recommendation="Restore AGENTS.md before autonomous audit cycles.",
    )

    projected = from_self_audit_finding(
        audit_finding,
        run_id="run_self_audit_001",
        repository="atlas-core",
        task_id=None,
        base_revision="a" * 40,
        candidate_revision="b" * 40,
        at="2026-07-29T11:00:00+00:00",
    )

    assert projected.id == "finding_self_audit_agents-missing"
    assert projected.source == "self_audit"
    assert projected.severity is FindingSeverity.BLOCKING
    assert projected.risk.value == "critical"
    assert projected.evidence[0].reference == "agents-missing"
    assert projected.suggested_action == "Restore AGENTS.md before autonomous audit cycles."
    assert audit_finding.severity == "critical"
