"""Audited, minimal publication of engineering-plane events.

This is an opt-in bridge: callers decide when a newly-recorded finding or a
completed review becomes observable.  The bridge never applies a patch, creates
a task, invokes an Orchestrator, or serializes reviewer prose/diffs into an
event.  Merkle auditing happens before EventBus publication so an audit failure
is fail-closed for the observable event.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from atlas.core.contracts import Event, EventType
from atlas.core.event_bus import EventBus
from atlas.core.verify import Verdict
from atlas.engineering.findings import EngineeringFinding
from atlas.engineering.review import EngineeringReviewReport
from atlas.events.schemas import Risk
from atlas.logging.merkle_logger import AuditRecord


class MerkleAuditLogger(Protocol):
    """Narrow audit seam used to make event publication fail closed."""

    def log(
        self,
        action: str,
        agent: str,
        result: str,
        risk_level: str = "safe",
        payload: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> AuditRecord: ...


@dataclass(frozen=True)
class EngineeringEventReceipt:
    """The emitted event linked to the real audit receipt that preceded it."""

    event: Event
    audit_hash: str


_MERKLE_RISK: dict[Risk, str] = {
    Risk.NONE: "safe",
    Risk.LOW: "safe",
    Risk.MEDIUM: "moderate",
    Risk.HIGH: "high",
    Risk.CRITICAL: "critical",
}
_RISK_ORDER: dict[Risk, int] = {
    Risk.NONE: 0,
    Risk.LOW: 1,
    Risk.MEDIUM: 2,
    Risk.HIGH: 3,
    Risk.CRITICAL: 4,
}


class EngineeringEventPublisher:
    """Publish safe metadata only after a chained Merkle audit record exists."""

    def __init__(self, *, bus: EventBus, merkle: MerkleAuditLogger) -> None:
        self._bus = bus
        self._merkle = merkle

    def publish_finding(self, finding: EngineeringFinding) -> EngineeringEventReceipt:
        """Expose a finding's identity/status, never reviewer content or a patch."""

        payload = _finding_payload(finding)
        audit = self._merkle.log(
            action="engineering.finding.recorded",
            agent="engineering.event_publisher",
            result="success",
            risk_level=_MERKLE_RISK[finding.risk],
            payload=payload,
            task_id=finding.task_id,
        )
        event = self._bus.publish_type(
            EventType.ENGINEERING_FINDING,
            {**payload, "audit_ref": audit.hash_self},
            task_id=finding.task_id,
            producer="atlas.engineering",
        )
        return EngineeringEventReceipt(event=event, audit_hash=audit.hash_self)

    def publish_review_completed(
        self,
        report: EngineeringReviewReport,
    ) -> EngineeringEventReceipt:
        """Expose review outcome metadata after its independent audit receipt."""

        payload = _review_payload(report)
        risk = _max_risk(report.findings)
        audit = self._merkle.log(
            action="engineering.review.completed",
            agent="engineering.event_publisher",
            result=_audit_result(report.verdict),
            risk_level=_MERKLE_RISK[risk],
            payload=payload,
            task_id=report.request.task_id,
        )
        event = self._bus.publish_type(
            EventType.ENGINEERING_REVIEW_COMPLETED,
            {**payload, "audit_ref": audit.hash_self},
            task_id=report.request.task_id,
            producer="atlas.engineering",
        )
        return EngineeringEventReceipt(event=event, audit_hash=audit.hash_self)


def _finding_payload(finding: EngineeringFinding) -> dict[str, Any]:
    """Projection safe for the event plane; content remains with its producer."""

    return {
        "finding_id": finding.id,
        "run_id": finding.run_id,
        "repository": finding.repository,
        "base_revision": finding.base_revision,
        "candidate_revision": finding.candidate_revision,
        "source": finding.source,
        "category": finding.category,
        "severity": finding.severity.value,
        "status": finding.status.value,
        "risk": finding.risk.value,
        "location_count": len(finding.locations),
        "evidence_count": len(finding.evidence),
    }


def _review_payload(report: EngineeringReviewReport) -> dict[str, Any]:
    """Metadata-only review projection; never include a diff or adapter prose."""

    risk = _max_risk(report.findings)
    return {
        "run_id": report.request.run_id,
        "repository": report.request.repository,
        "base_revision": report.request.base_revision,
        "candidate_revision": report.request.candidate_revision,
        "verdict": report.verdict.value,
        "adapter_ids": [outcome.adapter_id for outcome in report.outcomes],
        "outcome_count": len(report.outcomes),
        "finding_ids": [finding.id for finding in report.findings],
        "finding_count": len(report.findings),
        "risk": risk.value,
    }


def _max_risk(findings: tuple[EngineeringFinding, ...]) -> Risk:
    if not findings:
        return Risk.LOW
    return max((finding.risk for finding in findings), key=_RISK_ORDER.__getitem__)


def _audit_result(verdict: Verdict) -> str:
    if verdict is Verdict.PASS:
        return "success"
    if verdict is Verdict.FAIL:
        return "failure"
    return "pending"
