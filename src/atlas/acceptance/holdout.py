"""WP-EH-HOLDOUT: protected holdout and evaluator-isolation fixtures.

This in-process acceptance seam represents immutable holdout provenance,
candidate-denied access attempts, and contamination observations. It does not
authenticate actors, execute candidates, expose holdout contents, persist
criteria or verdict state, adjudicate an acceptance result, or grant authority.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
from typing import Literal, Self

from pydantic import field_validator, model_validator

from atlas.acceptance.core import _FrozenStrictModel, _NonEmptyText, _OpaqueId, _Sha256


HOLDOUT_RETENTION_METADATA = (
    "Retain corpus identity/version and raw evidence as long as dependent "
    "acceptance/rollback/audit claims remain valid; no unratified numeric "
    "duration invented."
)


class CandidateIdentityMismatchError(ValueError):
    """Raised when a request identity is not the policy's declared candidate."""


class HoldoutCandidateSurface(str, Enum):
    """Candidate-controlled surfaces that remain denied for a protected holdout."""

    INSPECT_HOLDOUT = "INSPECT_HOLDOUT"
    MUTATE_HOLDOUT = "MUTATE_HOLDOUT"
    READ_EVALUATOR_CRITERIA = "READ_EVALUATOR_CRITERIA"
    WRITE_EVALUATOR_CRITERIA = "WRITE_EVALUATOR_CRITERIA"
    READ_EVALUATOR_VERDICT = "READ_EVALUATOR_VERDICT"
    WRITE_EVALUATOR_VERDICT = "WRITE_EVALUATOR_VERDICT"
    SELECT_EVALUATOR_SUBSET = "SELECT_EVALUATOR_SUBSET"
    TRAIN_OR_TUNE_ON_HOLDOUT = "TRAIN_OR_TUNE_ON_HOLDOUT"


class HoldoutContaminationKind(str, Enum):
    """Frozen contamination categories recorded without an acceptance verdict."""

    CANDIDATE_TRAINING_OR_TUNING = "CANDIDATE_TRAINING_OR_TUNING"
    CANDIDATE_EVALUATOR_SUBSET_MUTATION = "CANDIDATE_EVALUATOR_SUBSET_MUTATION"
    PUBLIC_OR_UPSTREAM_FAMILIARITY = "PUBLIC_OR_UPSTREAM_FAMILIARITY"


_DIRECT_CANDIDATE_CONTAMINATION_KINDS = frozenset(
    {
        HoldoutContaminationKind.CANDIDATE_TRAINING_OR_TUNING,
        HoldoutContaminationKind.CANDIDATE_EVALUATOR_SUBSET_MUTATION,
    }
)


class HoldoutProvenance(_FrozenStrictModel):
    """Versioned, content-bound holdout provenance without a protected case."""

    corpus_class_id: Literal["CORPUS-HOLDOUT"]
    corpus_version: _NonEmptyText
    content_sha256: _Sha256
    source_canon_ids: tuple[_OpaqueId, ...]
    creator_identity: _NonEmptyText
    import_source: _NonEmptyText
    generation_method: _NonEmptyText
    contamination_history: tuple[_NonEmptyText, ...]
    retention_metadata: _NonEmptyText
    supersedes_corpus_version: _NonEmptyText | None = None
    supersedes_content_sha256: _Sha256 | None = None

    @field_validator("source_canon_ids")
    @classmethod
    def _require_source_provenance(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("source_canon_ids must name at least one source")
        if len(set(value)) != len(value):
            raise ValueError("source_canon_ids must be unique")
        return value

    @field_validator("contamination_history")
    @classmethod
    def _require_unique_contamination_history(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("contamination_history entries must be unique")
        return value

    @field_validator("retention_metadata")
    @classmethod
    def _require_frozen_retention_metadata(cls, value: str) -> str:
        if value != HOLDOUT_RETENTION_METADATA:
            raise ValueError("retention_metadata must use the frozen instruction")
        return value

    @model_validator(mode="after")
    def _require_complete_new_version_provenance(self) -> Self:
        has_prior_version = self.supersedes_corpus_version is not None
        has_prior_hash = self.supersedes_content_sha256 is not None
        if has_prior_version != has_prior_hash:
            raise ValueError(
                "supersedes_corpus_version and supersedes_content_sha256 must both "
                "be present or absent"
            )
        if has_prior_version and self.supersedes_corpus_version == self.corpus_version:
            raise ValueError(
                "a corrected corpus version must differ from its predecessor"
            )
        if has_prior_hash and self.supersedes_content_sha256 == self.content_sha256:
            raise ValueError(
                "a corrected corpus content hash must differ from its predecessor"
            )
        return self


class ProtectedHoldoutFixture(_FrozenStrictModel):
    """A protected holdout identity and provenance, never its case contents."""

    holdout_id: _OpaqueId
    provenance: HoldoutProvenance


class EvaluatorIsolationPolicy(_FrozenStrictModel):
    """Declarative candidate denial owned by one evaluator identity."""

    policy_id: _OpaqueId
    candidate_identity: _OpaqueId
    evaluator_identity: _OpaqueId
    evaluator_criteria_owner_identity: _OpaqueId
    evaluator_verdict_state_owner_identity: _OpaqueId
    candidate_visibility: Literal["DENIED"] = "DENIED"
    candidate_can_train_or_tune_on_holdout: Literal[False] = False
    candidate_can_select_or_mutate_evaluator_subsets: Literal[False] = False
    candidate_can_write_evaluator_criteria: Literal[False] = False
    candidate_can_write_evaluator_verdict_state: Literal[False] = False

    @model_validator(mode="after")
    def _require_evaluator_owned_non_candidate_surfaces(self) -> Self:
        if self.candidate_identity == self.evaluator_identity:
            raise ValueError("candidate_identity and evaluator_identity must differ")
        if self.evaluator_criteria_owner_identity != self.evaluator_identity:
            raise ValueError(
                "evaluator criteria must remain owned by evaluator_identity"
            )
        if self.evaluator_verdict_state_owner_identity != self.evaluator_identity:
            raise ValueError(
                "evaluator verdict state must remain owned by evaluator_identity"
            )
        return self


class CandidateHoldoutRequest(_FrozenStrictModel):
    """An attempted candidate access to a surface that remains denied."""

    request_id: _OpaqueId
    candidate_identity: _OpaqueId
    requested_surface: HoldoutCandidateSurface


class CandidateHoldoutAccessDenial(_FrozenStrictModel):
    """A denial record containing no protected corpus or evaluator data."""

    request_id: _OpaqueId
    candidate_identity: _OpaqueId
    requested_surface: HoldoutCandidateSurface
    candidate_visibility: Literal["DENIED"] = "DENIED"
    access_granted: Literal[False] = False


class ProtectedHoldoutAccessBoundary:
    """Return denials only; this seam is not authentication or authority."""

    __slots__ = ("_candidate_identity",)
    _candidate_identity: str

    def __init__(
        self,
        policy: EvaluatorIsolationPolicy,
        holdout: ProtectedHoldoutFixture,
    ) -> None:
        validated_policy = EvaluatorIsolationPolicy.model_validate(policy)
        ProtectedHoldoutFixture.model_validate(holdout)
        object.__setattr__(
            self,
            "_candidate_identity",
            validated_policy.candidate_identity,
        )

    def __setattr__(self, name: str, value: object) -> None:
        raise TypeError("protected holdout boundaries are immutable")

    def deny_candidate_access(
        self,
        request: CandidateHoldoutRequest,
    ) -> CandidateHoldoutAccessDenial:
        """Revalidate and deny a candidate request without revealing a holdout."""

        validated_request = CandidateHoldoutRequest.model_validate(request)
        if validated_request.candidate_identity != self._candidate_identity:
            raise CandidateIdentityMismatchError(
                "candidate identity does not match protected holdout policy: "
                f"{validated_request.candidate_identity} != {self._candidate_identity}"
            )
        return CandidateHoldoutAccessDenial(
            request_id=validated_request.request_id,
            candidate_identity=validated_request.candidate_identity,
            requested_surface=validated_request.requested_surface,
        )


class HoldoutContaminationFinding(_FrozenStrictModel):
    """One evidence-referenced contamination observation for a holdout."""

    finding_id: _OpaqueId
    holdout_id: _OpaqueId
    kind: HoldoutContaminationKind
    evidence_reference: _NonEmptyText


class HoldoutContaminationAssessment(_FrozenStrictModel):
    """A retained contamination state, not a PASS/FAIL acceptance decision."""

    holdout_id: _OpaqueId
    finding_ids: tuple[_OpaqueId, ...]
    direct_candidate_exposure_detected: bool
    public_familiarity_risk_recorded: bool
    revalidation_required: bool

    @model_validator(mode="after")
    def _require_consistent_contamination_flags(self) -> Self:
        if len(set(self.finding_ids)) != len(self.finding_ids):
            raise ValueError("contamination finding identities must be unique")
        if not self.finding_ids and (
            self.direct_candidate_exposure_detected
            or self.public_familiarity_risk_recorded
            or self.revalidation_required
        ):
            raise ValueError("contamination flags require at least one finding")
        if self.direct_candidate_exposure_detected != self.revalidation_required:
            raise ValueError(
                "direct candidate exposure and revalidation_required must agree"
            )
        return self


class HoldoutContaminationChecker:
    """Record contamination without changing evaluator criteria or verdict."""

    __slots__ = ()

    def assess(
        self,
        holdout: ProtectedHoldoutFixture,
        findings: Iterable[HoldoutContaminationFinding],
    ) -> HoldoutContaminationAssessment:
        """Preserve finding order and require revalidation on direct leakage."""

        if isinstance(findings, (str, bytes)):
            raise ValueError("findings must be an iterable of contamination findings")
        validated_holdout = ProtectedHoldoutFixture.model_validate(holdout)
        validated_findings = tuple(
            HoldoutContaminationFinding.model_validate(item) for item in findings
        )
        finding_ids = tuple(item.finding_id for item in validated_findings)
        if len(set(finding_ids)) != len(finding_ids):
            raise ValueError("contamination finding identities must be unique")
        if any(
            item.holdout_id != validated_holdout.holdout_id
            for item in validated_findings
        ):
            raise ValueError("contamination finding holdout identity must match")

        direct_exposure = any(
            item.kind in _DIRECT_CANDIDATE_CONTAMINATION_KINDS
            for item in validated_findings
        )
        public_familiarity = any(
            item.kind is HoldoutContaminationKind.PUBLIC_OR_UPSTREAM_FAMILIARITY
            for item in validated_findings
        )
        return HoldoutContaminationAssessment(
            holdout_id=validated_holdout.holdout_id,
            finding_ids=finding_ids,
            direct_candidate_exposure_detected=direct_exposure,
            public_familiarity_risk_recorded=public_familiarity,
            revalidation_required=direct_exposure,
        )
