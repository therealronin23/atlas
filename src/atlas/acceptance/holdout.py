"""WP-EH-HOLDOUT: protected holdout and evaluator-isolation fixtures.

This in-process acceptance seam represents immutable holdout provenance,
candidate-denied access attempts, and contamination observations. It does not
authenticate actors, execute candidates, expose holdout contents, persist
criteria or verdict state, adjudicate an acceptance result, or grant authority.
"""

from __future__ import annotations

import hashlib
import json
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


class HoldoutInspectionStatus(str, Enum):
    """Whether contamination inspection evidence is complete enough to interpret."""

    INSPECTED = "INSPECTED"
    NOT_INSPECTED = "NOT_INSPECTED"
    INCOMPLETE = "INCOMPLETE"
    UNRESOLVED = "UNRESOLVED"


class HoldoutContaminationEpistemicState(str, Enum):
    """Knowledge state only; never an acceptance PASS/FAIL result."""

    KNOWN_CLEAR = "KNOWN_CLEAR"
    KNOWN_CONTAMINATED = "KNOWN_CONTAMINATED"
    UNKNOWN = "UNKNOWN"


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
    holdout_id: _OpaqueId
    policy_id: _OpaqueId
    evaluator_identity: _OpaqueId
    boundary_binding_sha256: _Sha256
    candidate_visibility: Literal["DENIED"] = "DENIED"
    access_granted: Literal[False] = False


def _boundary_binding_sha256(
    policy: EvaluatorIsolationPolicy,
    holdout: ProtectedHoldoutFixture,
) -> str:
    payload = {
        "binding_schema": "WP-EH-HOLDOUT-BOUNDARY-v1",
        "holdout": holdout.model_dump(mode="json"),
        "policy": policy.model_dump(mode="json"),
    }
    canonical = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class ProtectedHoldoutAccessBoundary:
    """Return denials only; this seam is not authentication or authority."""

    __slots__ = (
        "_candidate_identity",
        "_holdout_id",
        "_policy_id",
        "_evaluator_identity",
        "_boundary_binding_sha256",
    )
    _candidate_identity: str
    _holdout_id: str
    _policy_id: str
    _evaluator_identity: str
    _boundary_binding_sha256: str

    def __init__(
        self,
        policy: EvaluatorIsolationPolicy,
        holdout: ProtectedHoldoutFixture,
    ) -> None:
        validated_policy = EvaluatorIsolationPolicy.model_validate(policy)
        validated_holdout = ProtectedHoldoutFixture.model_validate(holdout)
        object.__setattr__(
            self,
            "_candidate_identity",
            validated_policy.candidate_identity,
        )
        object.__setattr__(self, "_holdout_id", validated_holdout.holdout_id)
        object.__setattr__(self, "_policy_id", validated_policy.policy_id)
        object.__setattr__(
            self,
            "_evaluator_identity",
            validated_policy.evaluator_identity,
        )
        object.__setattr__(
            self,
            "_boundary_binding_sha256",
            _boundary_binding_sha256(validated_policy, validated_holdout),
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
            holdout_id=self._holdout_id,
            policy_id=self._policy_id,
            evaluator_identity=self._evaluator_identity,
            boundary_binding_sha256=self._boundary_binding_sha256,
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
    inspection_status: HoldoutInspectionStatus
    epistemic_state: HoldoutContaminationEpistemicState
    finding_ids: tuple[_OpaqueId, ...]
    finding_kinds: tuple[HoldoutContaminationKind, ...]
    contamination_history: tuple[_NonEmptyText, ...]
    direct_candidate_exposure_detected: bool | None
    public_familiarity_risk_recorded: bool | None
    revalidation_required: bool | None

    @model_validator(mode="after")
    def _require_consistent_contamination_flags(self) -> Self:
        if len(set(self.finding_ids)) != len(self.finding_ids):
            raise ValueError("contamination finding identities must be unique")
        if len(self.finding_ids) != len(self.finding_kinds):
            raise ValueError("finding identities and kinds must remain derived together")
        if (
            self.inspection_status is HoldoutInspectionStatus.NOT_INSPECTED
            and self.finding_ids
        ):
            raise ValueError("NOT_INSPECTED cannot carry new inspection findings")

        expected = _derive_contamination_state(
            inspection_status=self.inspection_status,
            finding_kinds=self.finding_kinds,
            contamination_history=self.contamination_history,
        )
        actual = (
            self.epistemic_state,
            self.direct_candidate_exposure_detected,
            self.public_familiarity_risk_recorded,
            self.revalidation_required,
        )
        if actual != expected:
            raise ValueError(
                "epistemic state and derived contamination flags are inconsistent"
            )
        return self


def _derive_contamination_state(
    *,
    inspection_status: HoldoutInspectionStatus,
    finding_kinds: tuple[HoldoutContaminationKind, ...],
    contamination_history: tuple[str, ...],
) -> tuple[HoldoutContaminationEpistemicState, bool | None, bool | None, bool | None]:
    direct_finding = any(
        kind in _DIRECT_CANDIDATE_CONTAMINATION_KINDS for kind in finding_kinds
    )
    public_finding = any(
        kind is HoldoutContaminationKind.PUBLIC_OR_UPSTREAM_FAMILIARITY
        for kind in finding_kinds
    )
    has_untyped_history = bool(contamination_history)
    inspected = inspection_status is HoldoutInspectionStatus.INSPECTED

    if direct_finding:
        direct_exposure: bool | None = True
    elif inspected and not has_untyped_history:
        direct_exposure = False
    else:
        direct_exposure = None

    if public_finding:
        public_familiarity: bool | None = True
    elif inspected and not has_untyped_history:
        public_familiarity = False
    else:
        public_familiarity = None

    if direct_exposure is True:
        revalidation_required: bool | None = True
    elif direct_exposure is False:
        revalidation_required = False
    else:
        revalidation_required = None

    if finding_kinds or has_untyped_history:
        epistemic_state = HoldoutContaminationEpistemicState.KNOWN_CONTAMINATED
    elif inspected:
        epistemic_state = HoldoutContaminationEpistemicState.KNOWN_CLEAR
    else:
        epistemic_state = HoldoutContaminationEpistemicState.UNKNOWN

    return (
        epistemic_state,
        direct_exposure,
        public_familiarity,
        revalidation_required,
    )


class HoldoutContaminationChecker:
    """Record contamination without changing evaluator criteria or verdict."""

    __slots__ = ()

    def assess(
        self,
        holdout: ProtectedHoldoutFixture,
        findings: Iterable[HoldoutContaminationFinding],
        *,
        inspection_status: HoldoutInspectionStatus,
    ) -> HoldoutContaminationAssessment:
        """Preserve findings/history and never infer clean from an empty vector."""

        if isinstance(findings, (str, bytes)):
            raise ValueError("findings must be an iterable of contamination findings")
        if not isinstance(inspection_status, HoldoutInspectionStatus):
            raise TypeError("inspection_status must be HoldoutInspectionStatus")
        validated_holdout = ProtectedHoldoutFixture.model_validate(holdout)
        validated_findings = tuple(
            HoldoutContaminationFinding.model_validate(item) for item in findings
        )
        finding_ids = tuple(item.finding_id for item in validated_findings)
        finding_kinds = tuple(item.kind for item in validated_findings)
        if len(set(finding_ids)) != len(finding_ids):
            raise ValueError("contamination finding identities must be unique")
        if any(
            item.holdout_id != validated_holdout.holdout_id
            for item in validated_findings
        ):
            raise ValueError("contamination finding holdout identity must match")

        contamination_history = validated_holdout.provenance.contamination_history
        (
            epistemic_state,
            direct_exposure,
            public_familiarity,
            revalidation_required,
        ) = _derive_contamination_state(
            inspection_status=inspection_status,
            finding_kinds=finding_kinds,
            contamination_history=contamination_history,
        )
        return HoldoutContaminationAssessment(
            holdout_id=validated_holdout.holdout_id,
            inspection_status=inspection_status,
            epistemic_state=epistemic_state,
            finding_ids=finding_ids,
            finding_kinds=finding_kinds,
            contamination_history=contamination_history,
            direct_candidate_exposure_detected=direct_exposure,
            public_familiarity_risk_recorded=public_familiarity,
            revalidation_required=revalidation_required,
        )
