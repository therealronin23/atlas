"""Versioned, append-only projection for engineering findings.

This module deliberately does not verify code, execute commands, apply patches,
or authorize effects.  It composes those specialised systems later through a
single serializable finding contract.  A patch reference is evidence only;
promotion still belongs to the governed proposal and approval paths.
"""

from __future__ import annotations

import json
import os
import threading
from enum import Enum
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from atlas.events.schemas import Risk


SchemaVersion = Literal["1.0"]
SCHEMA_VERSION: SchemaVersion = "1.0"


class FindingSeverity(str, Enum):
    INFO = "INFO"
    MINOR = "MINOR"
    MAJOR = "MAJOR"
    BLOCKING = "BLOCKING"


class FindingStatus(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FIX_PROPOSED = "FIX_PROPOSED"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"
    BLOCKED = "BLOCKED"


class FindingLocation(BaseModel):
    """A source location supplied as review evidence, never a filesystem handle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    column: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def end_cannot_precede_start(self) -> FindingLocation:
        if (
            self.start_line is not None
            and self.end_line is not None
            and self.end_line < self.start_line
        ):
            raise ValueError("end_line cannot precede start_line")
        return self


class FindingEvidence(BaseModel):
    """A stable reference to evidence retained by its authoritative producer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    detail: str | None = None


class EngineeringFinding(BaseModel):
    """Public contract from Workbench Cut 1, version 1.0.

    Fields that may not be known for a system-level review are still present as
    explicit ``null`` values.  That distinction prevents an omitted field from
    being silently mistaken for a fact by a client or future coordinator.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^finding_[A-Za-z0-9_-]+$")
    schema_version: SchemaVersion = SCHEMA_VERSION
    run_id: str = Field(min_length=1)
    task_id: str | None
    repository: str = Field(min_length=1)
    base_revision: str | None
    candidate_revision: str | None
    source: str = Field(min_length=1)
    category: str = Field(min_length=1)
    severity: FindingSeverity
    status: FindingStatus
    summary: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    locations: tuple[FindingLocation, ...]
    evidence: tuple[FindingEvidence, ...]
    reproduction: str | None
    suggested_action: str | None
    patch_ref: str | None
    dedupe_key: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    risk: Risk = Risk.NONE
    owner: str | None = None
    approval_ref: str | None = None


class FindingJournalEntry(BaseModel):
    """One immutable fact in the local finding journal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Literal["recorded", "status_changed"]
    finding: EngineeringFinding
    at: str = Field(min_length=1)
    reason: str | None = None


# ``EngineeringFindingStore.list()`` is a required public API.  As in the
# existing plugin activator, an alias avoids its method name shadowing the
# builtin ``list`` while annotations inside the class are resolved by mypy.
FindingList = list[EngineeringFinding]
JournalEntries = list[FindingJournalEntry]


class _SelfAuditFindingLike(Protocol):
    """The stable subset projected from ``core.self_audit`` without a cycle."""

    id: str
    category: str
    severity: str
    title: str
    detail: str
    recommendation: str


_SELF_AUDIT_SEVERITIES: dict[str, tuple[FindingSeverity, Risk]] = {
    "critical": (FindingSeverity.BLOCKING, Risk.CRITICAL),
    "high": (FindingSeverity.MAJOR, Risk.HIGH),
    "medium": (FindingSeverity.MAJOR, Risk.MEDIUM),
    "low": (FindingSeverity.MINOR, Risk.LOW),
    "info": (FindingSeverity.INFO, Risk.NONE),
}


def from_self_audit_finding(
    finding: _SelfAuditFindingLike,
    *,
    run_id: str,
    repository: str,
    task_id: str | None,
    base_revision: str | None,
    candidate_revision: str | None,
    at: str,
) -> EngineeringFinding:
    """Project a self-audit observation without changing its native record.

    Severity is intentionally conservative: only the existing ``critical``
    self-audit classification becomes ``BLOCKING``.  A coordinator or policy
    may later attach routing and Merkle elevation; this adapter only preserves
    a serializable observation and its source reference.
    """

    severity, risk = _SELF_AUDIT_SEVERITIES.get(
        finding.severity.casefold(),
        (FindingSeverity.INFO, Risk.NONE),
    )
    safe_id = "".join(
        character if character.isalnum() or character in "_-" else "_"
        for character in finding.id
    )
    revision = candidate_revision or "unknown"
    return EngineeringFinding(
        id=f"finding_self_audit_{safe_id}",
        run_id=run_id,
        task_id=task_id,
        repository=repository,
        base_revision=base_revision,
        candidate_revision=candidate_revision,
        source="self_audit",
        category=finding.category,
        severity=severity,
        status=FindingStatus.OPEN,
        summary=finding.title,
        detail=finding.detail,
        locations=(),
        evidence=(
            FindingEvidence(
                kind="self_audit",
                reference=finding.id,
                detail=finding.detail,
            ),
        ),
        reproduction=None,
        suggested_action=finding.recommendation,
        patch_ref=None,
        dedupe_key=f"{repository}:{revision}:self_audit:{finding.id}",
        created_at=at,
        updated_at=at,
        risk=risk,
    )


class EngineeringFindingStore:
    """Append-only JSONL journal with deterministic deduplication and replay.

    The caller supplies the runtime-owned path.  The store neither knows a
    repository root nor opens a patch reference, which makes applying a patch
    structurally impossible at this boundary.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    def record(self, finding: EngineeringFinding) -> EngineeringFinding:
        """Record a new finding, or return the prior finding with its key.

        A repeated deterministic review must not create a fresh unresolved
        issue.  New evidence therefore needs a new dedupe key, rather than a
        hidden overwrite of the existing ledger entry.
        """

        with self._lock:
            findings = self._current_findings()
            for existing in findings:
                if existing.dedupe_key == finding.dedupe_key:
                    return existing
                if existing.id == finding.id:
                    raise ValueError(f"finding id already recorded: {finding.id}")
            self._append(
                FindingJournalEntry(
                    event="recorded",
                    finding=finding,
                    at=finding.created_at,
                )
            )
            return finding

    def transition(
        self,
        finding_id: str,
        status: FindingStatus,
        *,
        reason: str,
        at: str,
    ) -> EngineeringFinding:
        """Append a lifecycle transition; authorization remains outside this store."""

        if not reason.strip():
            raise ValueError("a finding status transition requires a reason")
        with self._lock:
            current = self.get(finding_id)
            if current is None:
                raise KeyError(f"unknown finding: {finding_id}")
            if current.status is status:
                raise ValueError(f"finding already has status {status.value}")
            updated = current.model_copy(update={"status": status, "updated_at": at})
            self._append(
                FindingJournalEntry(
                    event="status_changed",
                    finding=updated,
                    at=at,
                    reason=reason,
                )
            )
            return updated

    def get(self, finding_id: str) -> EngineeringFinding | None:
        with self._lock:
            return next(
                (finding for finding in self._current_findings() if finding.id == finding_id),
                None,
            )

    def list(self) -> FindingList:
        with self._lock:
            return self._current_findings()

    def history(self, finding_id: str) -> JournalEntries:
        with self._lock:
            return [entry for entry in self._entries() if entry.finding.id == finding_id]

    def count(self) -> int:
        return len(self.list())

    def _current_findings(self) -> FindingList:
        ordered_ids: list[str] = []
        current: dict[str, EngineeringFinding] = {}
        for entry in self._entries():
            finding_id = entry.finding.id
            if finding_id not in current:
                ordered_ids.append(finding_id)
            current[finding_id] = entry.finding
        return [current[finding_id] for finding_id in ordered_ids]

    def _entries(self) -> JournalEntries:
        if not self._path.exists():
            return []
        entries: list[FindingJournalEntry] = []
        with self._path.open(encoding="utf-8") as journal:
            for line_number, raw in enumerate(journal, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    entries.append(FindingJournalEntry.model_validate_json(line))
                except ValueError as exc:
                    raise ValueError(
                        f"invalid engineering finding journal at {self._path}:{line_number}"
                    ) from exc
        return entries

    def _append(self, entry: FindingJournalEntry) -> None:
        with self._path.open("a", encoding="utf-8") as journal:
            journal.write(entry.model_dump_json() + "\n")
            journal.flush()
            os.fsync(journal.fileno())
