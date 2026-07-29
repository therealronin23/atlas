"""Explicit-acceptance baselines for bounded incremental engineering review.

The store records a base only after an external authority supplies an opaque
acceptance reference.  A PASS verdict alone is not an acceptance.  This module
never opens Git, computes a diff, promotes a candidate, or changes a finding;
the caller still verifies ancestry and constructs the bounded diff.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from atlas.core.verify import Verdict
from atlas.engineering.findings import EngineeringFinding, FindingStatus
from atlas.engineering.review import EngineeringReviewReport, EngineeringReviewRequest


class ReviewBaselineSource(str, Enum):
    """How a caller obtained the base to use when it later computes a diff."""

    REQUESTED_BASE = "REQUESTED_BASE"
    ACCEPTED_BASELINE = "ACCEPTED_BASELINE"
    ALREADY_ACCEPTED = "ALREADY_ACCEPTED"


class BaselineFindingState(BaseModel):
    """A minimal immutable snapshot used to preserve prior finding lifecycle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    finding_id: str = Field(pattern=r"^finding_[A-Za-z0-9_-]+$")
    dedupe_key: str = Field(min_length=1)
    status: FindingStatus
    updated_at: str = Field(min_length=1)


class EngineeringReviewBaseline(BaseModel):
    """One externally accepted candidate revision for one repository."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^review_baseline_[A-Za-z0-9_-]+$")
    schema_version: Literal["1.0"] = "1.0"
    repository: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    reviewed_from_revision: str | None
    run_id: str = Field(min_length=1)
    acceptance_ref: str = Field(min_length=1)
    accepted_by: str = Field(min_length=1)
    accepted_at: str = Field(min_length=1)
    finding_state: tuple[BaselineFindingState, ...]


class ReviewBaselineEntry(BaseModel):
    """Append-only journal record; later entries never rewrite an acceptance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Literal["accepted"]
    baseline: EngineeringReviewBaseline
    at: str = Field(min_length=1)


@dataclass(frozen=True)
class IncrementalReviewSelection:
    """A deterministic base selection, not a proof that Git ancestry holds."""

    source: ReviewBaselineSource
    base_revision: str | None
    accepted_baseline: EngineeringReviewBaseline | None
    prior_finding_state: tuple[BaselineFindingState, ...]
    review_required: bool
    requires_ancestry_verification: bool = True


_SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9_.:@/-]{1,160}$")


class EngineeringReviewBaselineStore:
    """Append-only acceptance journal owned by a caller-provided runtime path."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    def record_accepted(
        self,
        report: EngineeringReviewReport,
        *,
        acceptance_ref: str,
        accepted_by: str,
        at: str,
        finding_snapshot: tuple[EngineeringFinding, ...] = (),
    ) -> EngineeringReviewBaseline:
        """Record an explicit acceptance; a green report alone is insufficient."""

        self._validate_acceptable_report(report)
        self._validate_reference("acceptance_ref", acceptance_ref)
        self._validate_reference("accepted_by", accepted_by)
        candidate_revision = report.request.candidate_revision
        if candidate_revision is None or not candidate_revision.strip():
            raise ValueError("an accepted review baseline requires candidate_revision")
        finding_state = self._snapshot_finding_state(
            finding_snapshot,
            repository=report.request.repository,
            candidate_revision=candidate_revision,
        )
        fingerprint_source = "\x00".join(
            (report.request.repository, candidate_revision, acceptance_ref)
        )
        fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()[:16]
        baseline = EngineeringReviewBaseline(
            id=f"review_baseline_{fingerprint}",
            repository=report.request.repository,
            revision=candidate_revision,
            reviewed_from_revision=report.request.base_revision,
            run_id=report.request.run_id,
            acceptance_ref=acceptance_ref,
            accepted_by=accepted_by,
            accepted_at=at,
            finding_state=finding_state,
        )
        with self._lock:
            for existing in self._baselines():
                if (
                    existing.repository == baseline.repository
                    and existing.revision == baseline.revision
                ):
                    if existing.acceptance_ref == baseline.acceptance_ref:
                        return existing
                    raise ValueError(
                        "candidate revision already has an accepted baseline with a different "
                        "acceptance_ref"
                    )
            self._append(ReviewBaselineEntry(event="accepted", baseline=baseline, at=at))
        return baseline

    def latest(self, repository: str) -> EngineeringReviewBaseline | None:
        """Return the last append-only acceptance for the named repository."""

        with self._lock:
            matching = [
                baseline for baseline in self._baselines() if baseline.repository == repository
            ]
        return matching[-1] if matching else None

    def select(self, request: EngineeringReviewRequest) -> IncrementalReviewSelection:
        """Select an explicit accepted base without inferring Git ancestry."""

        candidate_revision = request.candidate_revision
        if candidate_revision is None or not candidate_revision.strip():
            raise ValueError("incremental review selection requires candidate_revision")
        baseline = self.latest(request.repository)
        if baseline is None:
            return IncrementalReviewSelection(
                source=ReviewBaselineSource.REQUESTED_BASE,
                base_revision=request.base_revision,
                accepted_baseline=None,
                prior_finding_state=(),
                review_required=True,
            )
        if baseline.revision == candidate_revision:
            return IncrementalReviewSelection(
                source=ReviewBaselineSource.ALREADY_ACCEPTED,
                base_revision=baseline.revision,
                accepted_baseline=baseline,
                prior_finding_state=baseline.finding_state,
                review_required=False,
                requires_ancestry_verification=False,
            )
        return IncrementalReviewSelection(
            source=ReviewBaselineSource.ACCEPTED_BASELINE,
            base_revision=baseline.revision,
            accepted_baseline=baseline,
            prior_finding_state=baseline.finding_state,
            review_required=True,
        )

    def count(self) -> int:
        with self._lock:
            return len(self._baselines())

    @staticmethod
    def _validate_acceptable_report(report: EngineeringReviewReport) -> None:
        if report.verdict is not Verdict.PASS:
            raise ValueError("only a PASS review can become an accepted baseline")
        if report.findings:
            raise ValueError("a review with findings cannot become an accepted baseline")
        if not report.outcomes:
            raise ValueError("at least one review outcome is required before acceptance")
        if any(outcome.verdict is not Verdict.PASS for outcome in report.outcomes):
            raise ValueError("all review outcomes must be PASS before acceptance")

    @staticmethod
    def _validate_reference(name: str, value: str) -> None:
        if not _SAFE_REFERENCE.fullmatch(value):
            raise ValueError(f"{name} must be a safe opaque reference")

    @staticmethod
    def _snapshot_finding_state(
        findings: tuple[EngineeringFinding, ...],
        *,
        repository: str,
        candidate_revision: str,
    ) -> tuple[BaselineFindingState, ...]:
        states: list[BaselineFindingState] = []
        seen_dedupe_keys: set[str] = set()
        for finding in findings:
            if (
                finding.repository != repository
                or finding.candidate_revision != candidate_revision
            ):
                raise ValueError("finding snapshot is outside accepted review context")
            if finding.dedupe_key in seen_dedupe_keys:
                raise ValueError("finding snapshot contains duplicate finding dedupe_key")
            seen_dedupe_keys.add(finding.dedupe_key)
            states.append(
                BaselineFindingState(
                    finding_id=finding.id,
                    dedupe_key=finding.dedupe_key,
                    status=finding.status,
                    updated_at=finding.updated_at,
                )
            )
        return tuple(sorted(states, key=lambda state: state.finding_id))

    def _baselines(self) -> list[EngineeringReviewBaseline]:
        if not self._path.exists():
            return []
        baselines: list[EngineeringReviewBaseline] = []
        with self._path.open(encoding="utf-8") as journal:
            for line_number, raw in enumerate(journal, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    baselines.append(ReviewBaselineEntry.model_validate_json(line).baseline)
                except ValueError as exc:
                    raise ValueError(
                        f"invalid engineering review baseline journal at {self._path}:{line_number}"
                    ) from exc
        return baselines

    def _append(self, entry: ReviewBaselineEntry) -> None:
        with self._path.open("a", encoding="utf-8") as journal:
            journal.write(entry.model_dump_json() + "\n")
            journal.flush()
            os.fsync(journal.fileno())
