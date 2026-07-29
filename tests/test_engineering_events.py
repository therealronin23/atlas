"""Tests for audited, minimal engineering event publication."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.contracts import EventType
from atlas.core.event_bus import EventBus
from atlas.core.verify import Verdict
from atlas.engineering.events import EngineeringEventPublisher
from atlas.engineering.findings import (
    EngineeringFinding,
    FindingEvidence,
    FindingSeverity,
    FindingStatus,
)
from atlas.engineering.review import (
    EngineeringReviewReport,
    EngineeringReviewRequest,
    ReviewOutcome,
)
from atlas.events.core_bridge import CoreEventBridge
from atlas.events.schemas import Risk
from atlas.events.store import OsEventStore
from atlas.logging.merkle_logger import MerkleLogger


def _finding() -> EngineeringFinding:
    return EngineeringFinding(
        id="finding_event_001",
        run_id="run_event_001",
        task_id="task_001",
        repository="atlas-core",
        base_revision="a" * 40,
        candidate_revision="b" * 40,
        source="deterministic_review",
        category="security",
        severity=FindingSeverity.MAJOR,
        status=FindingStatus.OPEN,
        summary="Candidate contains a problem",
        detail="token=do-not-publish reviewer explanation",
        locations=(),
        evidence=(FindingEvidence(kind="review", reference="secret-reference"),),
        reproduction="never publish this reproduction text",
        suggested_action="never publish this action text",
        patch_ref="never publish this patch reference",
        dedupe_key="event-dedupe",
        created_at="2026-07-29T14:00:00+00:00",
        updated_at="2026-07-29T14:00:00+00:00",
        risk=Risk.HIGH,
    )


def _review_report(finding: EngineeringFinding) -> EngineeringReviewReport:
    request = EngineeringReviewRequest(
        run_id=finding.run_id,
        task_id=finding.task_id,
        mission_id=None,
        repository=finding.repository,
        base_revision=finding.base_revision,
        candidate_revision=finding.candidate_revision,
        diff="TOP_SECRET_DIFF_CONTENT",
        scope=("src/atlas/example.py",),
        acceptance_criteria=("No secret diff reaches the event plane.",),
        at=finding.created_at,
    )
    return EngineeringReviewReport(
        request=request,
        verdict=Verdict.FAIL,
        outcomes=(
            ReviewOutcome(
                adapter_id="deterministic_review",
                verdict=Verdict.FAIL,
                findings=(finding,),
            ),
        ),
        findings=(finding,),
    )


def test_finding_event_is_merkle_audited_before_projection_and_never_copies_detail(tmp_path: Path) -> None:
    bus = EventBus()
    store = OsEventStore(tmp_path / "events.jsonl")
    CoreEventBridge(bus, store).attach()
    merkle = MerkleLogger(tmp_path / "audit")
    publisher = EngineeringEventPublisher(bus=bus, merkle=merkle)

    receipt = publisher.publish_finding(_finding())

    assert receipt.event.type is EventType.ENGINEERING_FINDING
    assert receipt.event.payload["finding_id"] == "finding_event_001"
    assert receipt.event.payload["audit_ref"] == receipt.audit_hash
    assert receipt.event.payload["risk"] == Risk.HIGH.value
    assert "detail" not in receipt.event.payload
    assert "patch_ref" not in receipt.event.payload
    assert "do-not-publish" not in str(receipt.event.payload)
    ok, reason = merkle.verify_chain()
    assert ok, reason
    record = merkle.read_all()[0]
    assert record.action == "engineering.finding.recorded"
    expected_audit_payload = dict(receipt.event.payload)
    expected_audit_payload.pop("audit_ref")
    assert record.payload == expected_audit_payload

    projected = store.read()[0]
    assert projected.type == EventType.ENGINEERING_FINDING.value
    assert projected.risk is Risk.HIGH
    assert projected.audit is None


def test_review_completed_event_exposes_only_review_metadata(tmp_path: Path) -> None:
    bus = EventBus()
    merkle = MerkleLogger(tmp_path / "audit")
    publisher = EngineeringEventPublisher(bus=bus, merkle=merkle)

    receipt = publisher.publish_review_completed(_review_report(_finding()))

    assert receipt.event.type is EventType.ENGINEERING_REVIEW_COMPLETED
    assert receipt.event.payload["verdict"] == Verdict.FAIL.value
    assert receipt.event.payload["finding_ids"] == ["finding_event_001"]
    assert receipt.event.payload["risk"] == Risk.HIGH.value
    assert "TOP_SECRET_DIFF_CONTENT" not in str(receipt.event.payload)
    assert "do-not-publish" not in str(receipt.event.payload)
    assert merkle.read_all()[0].action == "engineering.review.completed"


class _FailingMerkle:
    def log(
        self,
        action: str,
        agent: str,
        result: str,
        risk_level: str = "safe",
        payload: dict[str, object] | None = None,
        task_id: str | None = None,
    ) -> object:
        raise OSError("audit storage unavailable")


def test_audit_failure_is_fail_closed_and_does_not_publish(tmp_path: Path) -> None:
    bus = EventBus()
    received: list[object] = []
    bus.subscribe(EventType.ENGINEERING_FINDING, received.append)
    publisher = EngineeringEventPublisher(bus=bus, merkle=_FailingMerkle())

    with pytest.raises(OSError, match="audit storage unavailable"):
        publisher.publish_finding(_finding())

    assert received == []
