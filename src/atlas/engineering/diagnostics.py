"""Bounded diagnostic composition for validation failures.

This module joins existing validation and root-cause seams to the versioned
EngineeringFinding contract.  It deliberately does not run commands, create a
worktree, apply a correction, emit an event, or contact an Orchestrator.  Those
actions retain their own governed owners; this boundary only records the
evidence and preserves uncertainty when a cause cannot be established.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Protocol

from atlas.core.validation_runner import ValidationReport
from atlas.engineering.findings import (
    EngineeringFinding,
    EngineeringFindingStore,
    FindingEvidence,
    FindingLocation,
    FindingSeverity,
    FindingStatus,
)
from atlas.events.schemas import Risk


class DiagnosticClassification(str, Enum):
    """The canonical diagnosis vocabulary from the Workbench design."""

    INTRODUCED_REGRESSION = "INTRODUCED_REGRESSION"
    PRE_EXISTING = "PRE_EXISTING"
    ENVIRONMENTAL = "ENVIRONMENTAL"
    OPTIONAL_DEPENDENCY_MISSING = "OPTIONAL_DEPENDENCY_MISSING"
    RUNTIME_UNAVAILABLE = "RUNTIME_UNAVAILABLE"
    FLAKY = "FLAKY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class EngineeringDiagnosticRequest:
    """A captured failed validation run; it never opens the repository itself."""

    run_id: str
    task_id: str | None
    mission_id: str | None
    repository: str
    base_revision: str
    candidate_revision: str
    correlation_id: str
    command: tuple[str, ...]
    pytest_exit: int
    mypy_exit: int
    pytest_summary: str
    mypy_summary: str
    environment: tuple[tuple[str, str], ...]
    at: str
    severity: FindingSeverity
    risk: Risk

    @classmethod
    def from_validation_report(
        cls,
        *,
        validation: ValidationReport,
        run_id: str,
        task_id: str | None,
        mission_id: str | None,
        repository: str,
        base_revision: str,
        candidate_revision: str,
        correlation_id: str,
        command: tuple[str, ...],
        environment: tuple[tuple[str, str], ...],
        at: str,
        severity: FindingSeverity,
        risk: Risk,
    ) -> EngineeringDiagnosticRequest:
        """Capture an existing runner result without rerunning validation."""

        return cls(
            run_id=run_id,
            task_id=task_id,
            mission_id=mission_id,
            repository=repository,
            base_revision=base_revision,
            candidate_revision=candidate_revision,
            correlation_id=correlation_id,
            command=command,
            pytest_exit=validation.pytest_exit,
            mypy_exit=validation.mypy_exit,
            pytest_summary=validation.pytest_summary,
            mypy_summary=validation.mypy_summary,
            environment=environment,
            at=at,
            severity=severity,
            risk=risk,
        )

    @property
    def failed(self) -> bool:
        return self.pytest_exit != 0 or self.mypy_exit != 0


class _RootCauseVerdictLike(Protocol):
    classification: str
    reason: str
    evidence_paths: list[str]
    used_llm: bool


class RootCauseClassifierLike(Protocol):
    """The stable seam implemented by ``RootCauseClassifier`` today."""

    def classify(
        self,
        *,
        pytest_summary: str,
        mypy_summary: str,
        base_ref: str,
    ) -> _RootCauseVerdictLike: ...


@dataclass(frozen=True)
class EngineeringDiagnosticReport:
    """Safe diagnostic projection returned to the caller and journaled as a finding."""

    request: EngineeringDiagnosticRequest
    classification: DiagnosticClassification
    reason: str
    evidence_paths: tuple[str, ...]
    used_model: bool
    sanitized_environment: tuple[tuple[str, str], ...]
    finding: EngineeringFinding


_CLASSIFICATIONS: dict[str, DiagnosticClassification] = {
    "causado_por_diff": DiagnosticClassification.INTRODUCED_REGRESSION,
    "introduced_regression": DiagnosticClassification.INTRODUCED_REGRESSION,
    "pre_existing": DiagnosticClassification.PRE_EXISTING,
    "ambiental": DiagnosticClassification.ENVIRONMENTAL,
    "environmental": DiagnosticClassification.ENVIRONMENTAL,
    "optional_dependency_missing": DiagnosticClassification.OPTIONAL_DEPENDENCY_MISSING,
    "runtime_unavailable": DiagnosticClassification.RUNTIME_UNAVAILABLE,
    "flaky": DiagnosticClassification.FLAKY,
    "unknown": DiagnosticClassification.UNKNOWN,
}

_SUGGESTED_ACTIONS: dict[DiagnosticClassification, str] = {
    DiagnosticClassification.INTRODUCED_REGRESSION: (
        "Reproduce in a clean worktree, inspect the candidate diff, and propose any correction "
        "through the governed path."
    ),
    DiagnosticClassification.PRE_EXISTING: (
        "Confirm the failure against the base revision before attributing it to the candidate."
    ),
    DiagnosticClassification.ENVIRONMENTAL: (
        "Capture environment evidence and retry validation only through its governed runner."
    ),
    DiagnosticClassification.OPTIONAL_DEPENDENCY_MISSING: (
        "Classify the missing dependency as optional or provision it only through the approved "
        "dependency path."
    ),
    DiagnosticClassification.RUNTIME_UNAVAILABLE: (
        "Verify the required runtime or service availability; do not treat the candidate as "
        "repaired without fresh evidence."
    ),
    DiagnosticClassification.FLAKY: (
        "Repeat under controlled conditions and retain every attempt as evidence before a repair "
        "is proposed."
    ),
    DiagnosticClassification.UNKNOWN: (
        "Keep the failure unclassified until an isolated reproduction yields sufficient evidence."
    ),
}

_SENSITIVE_ENV_NAME = re.compile(
    r"(?:token|secret|password|passwd|api[_-]?key|private|credential|auth|cookie|session)",
    re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b((?:[A-Za-z][A-Za-z0-9_-]*)?(?:token|secret|password|passwd|api[_-]?key|"
    r"credential|auth)[A-Za-z0-9_-]*)\s*([=:])\s*([^\s,;]+)"
)
_BEARER_TOKEN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_GITHUB_TOKEN = re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{8,}\b")
_SAFE_CORRELATION_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


class EngineeringDiagnosticCoordinator:
    """Project a failed validation capture through an injected cause classifier.

    The classifier is intentionally injected rather than constructed here.  A
    caller must choose its model/provider policy before it supplies the existing
    ``RootCauseClassifier``; this coordinator never enables a provider itself.
    """

    def __init__(
        self,
        *,
        store: EngineeringFindingStore,
        classifier: RootCauseClassifierLike | None,
    ) -> None:
        self._store = store
        self._classifier = classifier

    def diagnose(self, request: EngineeringDiagnosticRequest) -> EngineeringDiagnosticReport:
        """Persist one evidence-bearing finding for a captured failing run."""

        self._validate_request(request)
        classification, reason, evidence_paths, used_model = self._classify(request)
        finding = self._store.record(
            self._finding_from_diagnosis(
                request=request,
                classification=classification,
                reason=reason,
                evidence_paths=evidence_paths,
                used_model=used_model,
            )
        )
        return EngineeringDiagnosticReport(
            request=request,
            classification=classification,
            reason=reason,
            evidence_paths=evidence_paths,
            used_model=used_model,
            sanitized_environment=_sanitize_environment(request.environment),
            finding=finding,
        )

    @staticmethod
    def _validate_request(request: EngineeringDiagnosticRequest) -> None:
        if not request.failed:
            raise ValueError("a diagnostic finding requires failed validation")
        if not request.command:
            raise ValueError("a diagnostic finding requires the captured command")
        if not _SAFE_CORRELATION_ID.fullmatch(request.correlation_id):
            raise ValueError("correlation_id must be a safe opaque identifier")

    def _classify(
        self,
        request: EngineeringDiagnosticRequest,
    ) -> tuple[DiagnosticClassification, str, tuple[str, ...], bool]:
        if self._classifier is None:
            return (
                DiagnosticClassification.UNKNOWN,
                "no diagnostic classifier is configured",
                (),
                False,
            )
        try:
            verdict = self._classifier.classify(
                pytest_summary=request.pytest_summary,
                mypy_summary=request.mypy_summary,
                base_ref=request.base_revision,
            )
        except Exception as exc:  # noqa: BLE001 - diagnostics preserve failed analysis as UNKNOWN
            return (
                DiagnosticClassification.UNKNOWN,
                f"diagnostic classifier failed with {type(exc).__name__}",
                (),
                False,
            )

        raw_classification = getattr(verdict, "classification", "")
        normalized = str(raw_classification).strip().casefold().replace("-", "_")
        classification = _CLASSIFICATIONS.get(normalized)
        if classification is None:
            return (
                DiagnosticClassification.UNKNOWN,
                "diagnostic classifier returned an unsupported classification",
                (),
                bool(getattr(verdict, "used_llm", False)),
            )
        return (
            classification,
            f"diagnostic classifier classified the failure as {classification.value}",
            _safe_relative_paths(getattr(verdict, "evidence_paths", ())),
            bool(getattr(verdict, "used_llm", False)),
        )

    @staticmethod
    def _finding_from_diagnosis(
        *,
        request: EngineeringDiagnosticRequest,
        classification: DiagnosticClassification,
        reason: str,
        evidence_paths: tuple[str, ...],
        used_model: bool,
    ) -> EngineeringFinding:
        fingerprint_source = "\x00".join(
            (
                request.repository,
                request.base_revision,
                request.candidate_revision,
                request.correlation_id,
                classification.value,
            )
        )
        fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()[:16]
        detail = f"Validation failure classification: {classification.value}."
        if reason:
            detail = f"{detail} Diagnostic evidence: {reason}"
        return EngineeringFinding(
            id=f"finding_diagnostic_{fingerprint}",
            run_id=request.run_id,
            task_id=request.task_id,
            repository=request.repository,
            base_revision=request.base_revision,
            candidate_revision=request.candidate_revision,
            source="diagnostic_coordinator",
            category="validation_diagnostic",
            severity=request.severity,
            status=FindingStatus.OPEN,
            summary=f"Validation failure classified as {classification.value}",
            detail=detail,
            locations=tuple(FindingLocation(path=path) for path in evidence_paths),
            evidence=(
                FindingEvidence(
                    kind="diagnostic_classification",
                    reference=classification.value,
                    detail=f"used_model={str(used_model).lower()}",
                ),
                FindingEvidence(
                    kind="validation_failure",
                    reference=request.correlation_id,
                    detail=(
                        f"pytest_exit={request.pytest_exit}; mypy_exit={request.mypy_exit}; "
                        "captured without raw command output"
                    ),
                ),
            ),
            reproduction=None,
            suggested_action=_SUGGESTED_ACTIONS[classification],
            patch_ref=None,
            dedupe_key=(
                f"{request.repository}:{request.candidate_revision}:diagnostic:"
                f"{request.correlation_id}:{classification.value}"
            ),
            created_at=request.at,
            updated_at=request.at,
            risk=request.risk,
        )


def _sanitize_environment(
    environment: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    """Return stable non-secret diagnostic metadata without mutating caller input."""

    sanitized: dict[str, str] = {}
    for key, value in environment:
        clean_key = key.strip()
        if not clean_key:
            continue
        if _SENSITIVE_ENV_NAME.search(clean_key):
            sanitized[clean_key] = "<redacted>"
        else:
            sanitized[clean_key] = _redact_text(value)[:256]
    return tuple(sorted(sanitized.items()))


def _safe_relative_paths(raw_paths: object) -> tuple[str, ...]:
    """Retain only normal relative paths as locations; never resolve or open them."""

    if not isinstance(raw_paths, (list, tuple)):
        return ()
    paths: set[str] = set()
    for raw_path in raw_paths:
        if not isinstance(raw_path, str):
            continue
        path = raw_path.strip().replace("\\", "/")
        if not path:
            continue
        parsed = PurePosixPath(path)
        if parsed.is_absolute() or ".." in parsed.parts:
            continue
        paths.add(path)
    return tuple(sorted(paths))


def _redact_text(value: str) -> str:
    """Redact common credential forms before an untrusted reason becomes evidence."""

    redacted = _SENSITIVE_ASSIGNMENT.sub(r"\1\2<redacted>", value)
    redacted = _BEARER_TOKEN.sub("Bearer <redacted>", redacted)
    redacted = _GITHUB_TOKEN.sub("<redacted>", redacted)
    return redacted.strip()[:512]
