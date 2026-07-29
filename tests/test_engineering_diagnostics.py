"""Tests for the bounded engineering diagnostic coordination slice.

The coordinator projects validation evidence into the shared finding contract.
It must preserve uncertainty, avoid persisting raw command output or secrets,
and leave reproduction, repair, approval, and effects to their governed owners.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from atlas.core.validation_runner import ValidationReport
from atlas.engineering.diagnostics import (
    DiagnosticClassification,
    EngineeringDiagnosticCoordinator,
    EngineeringDiagnosticRequest,
)
from atlas.engineering.findings import EngineeringFindingStore, FindingSeverity
from atlas.events.schemas import Risk


@dataclass
class _RootCauseVerdict:
    classification: str
    reason: str = ""
    evidence_paths: list[str] = field(default_factory=list)
    used_llm: bool = False


class _Classifier:
    def __init__(self, verdict: _RootCauseVerdict) -> None:
        self.verdict = verdict
        self.calls: list[dict[str, str]] = []

    def classify(
        self,
        *,
        pytest_summary: str,
        mypy_summary: str,
        base_ref: str,
    ) -> _RootCauseVerdict:
        self.calls.append(
            {
                "pytest_summary": pytest_summary,
                "mypy_summary": mypy_summary,
                "base_ref": base_ref,
            }
        )
        return self.verdict


class _BrokenClassifier:
    def classify(self, *, pytest_summary: str, mypy_summary: str, base_ref: str) -> _RootCauseVerdict:
        raise RuntimeError("token=do-not-persist")


def _request() -> EngineeringDiagnosticRequest:
    return EngineeringDiagnosticRequest(
        run_id="run_diagnostic_001",
        task_id="task_001",
        mission_id=None,
        repository="atlas-core",
        base_revision="a" * 40,
        candidate_revision="b" * 40,
        correlation_id="validation_001",
        command=("python", "-m", "pytest", "tests/test_example.py"),
        pytest_exit=1,
        mypy_exit=0,
        pytest_summary="FAILED tests/test_example.py::test_case - assertion failed",
        mypy_summary="",
        environment=(("ATLAS_MODE", "test"), ("API_TOKEN", "do-not-persist")),
        at="2026-07-29T13:00:00+00:00",
        severity=FindingSeverity.MAJOR,
        risk=Risk.MEDIUM,
    )


def test_diff_root_cause_becomes_introduced_regression_without_persisting_secret(tmp_path: Path) -> None:
    classifier = _Classifier(
        _RootCauseVerdict(
            classification="causado_por_diff",
            reason="token=do-not-persist candidate changed an assertion",
            evidence_paths=["src/atlas/example.py"],
            used_llm=False,
        )
    )
    store = EngineeringFindingStore(tmp_path / "findings.jsonl")

    report = EngineeringDiagnosticCoordinator(store=store, classifier=classifier).diagnose(_request())

    assert report.classification is DiagnosticClassification.INTRODUCED_REGRESSION
    assert report.used_model is False
    assert report.finding.severity is FindingSeverity.MAJOR
    assert report.finding.locations[0].path == "src/atlas/example.py"
    assert report.finding.evidence[0].kind == "diagnostic_classification"
    assert report.finding.evidence[0].reference == "INTRODUCED_REGRESSION"
    assert report.finding.evidence[0].detail == "used_model=false"
    assert report.sanitized_environment == (
        ("API_TOKEN", "<redacted>"),
        ("ATLAS_MODE", "test"),
    )
    serialized = report.finding.model_dump_json()
    assert "do-not-persist" not in serialized
    assert "do-not-persist" not in report.reason
    assert "candidate changed" not in serialized
    assert "candidate changed" not in report.reason
    assert classifier.calls[0]["base_ref"] == "a" * 40
    assert store.count() == 1


def test_environmental_diagnosis_is_preserved_as_evidence_not_a_repair(tmp_path: Path) -> None:
    classifier = _Classifier(
        _RootCauseVerdict(
            classification="ambiental",
            reason="the isolated worktree differs from the active environment",
            evidence_paths=["docs/design/current.md"],
            used_llm=False,
        )
    )
    store = EngineeringFindingStore(tmp_path / "findings.jsonl")

    report = EngineeringDiagnosticCoordinator(store=store, classifier=classifier).diagnose(_request())

    assert report.classification is DiagnosticClassification.ENVIRONMENTAL
    assert report.finding.patch_ref is None
    assert report.finding.status.value == "OPEN"
    assert "environment" in (report.finding.suggested_action or "").lower()
    assert store.count() == 1


def test_classifier_failure_remains_unknown_without_exposing_its_message(tmp_path: Path) -> None:
    store = EngineeringFindingStore(tmp_path / "findings.jsonl")

    report = EngineeringDiagnosticCoordinator(store=store, classifier=_BrokenClassifier()).diagnose(_request())

    assert report.classification is DiagnosticClassification.UNKNOWN
    assert report.used_model is False
    assert report.reason == "diagnostic classifier failed with RuntimeError"
    assert "do-not-persist" not in report.finding.model_dump_json()
    assert store.count() == 1


def test_known_optional_dependency_classification_is_retained(tmp_path: Path) -> None:
    classifier = _Classifier(
        _RootCauseVerdict(
            classification="optional_dependency_missing",
            reason="browser adapter is unavailable",
        )
    )
    store = EngineeringFindingStore(tmp_path / "findings.jsonl")

    report = EngineeringDiagnosticCoordinator(store=store, classifier=classifier).diagnose(_request())

    assert report.classification is DiagnosticClassification.OPTIONAL_DEPENDENCY_MISSING
    assert "dependency" in (report.finding.suggested_action or "").lower()


def test_untrusted_evidence_paths_cannot_escape_the_finding_context(tmp_path: Path) -> None:
    classifier = _Classifier(
        _RootCauseVerdict(
            classification="unknown",
            evidence_paths=["../.env", "/private/key", "src/atlas/safe.py"],
        )
    )
    store = EngineeringFindingStore(tmp_path / "findings.jsonl")

    report = EngineeringDiagnosticCoordinator(store=store, classifier=classifier).diagnose(_request())

    assert report.evidence_paths == ("src/atlas/safe.py",)
    assert tuple(location.path for location in report.finding.locations) == (
        "src/atlas/safe.py",
    )


def test_absent_classifier_is_visible_as_unknown_not_an_implicit_pass(tmp_path: Path) -> None:
    store = EngineeringFindingStore(tmp_path / "findings.jsonl")

    report = EngineeringDiagnosticCoordinator(store=store, classifier=None).diagnose(_request())

    assert report.classification is DiagnosticClassification.UNKNOWN
    assert report.reason == "no diagnostic classifier is configured"
    assert report.used_model is False
    assert store.count() == 1


def test_successful_validation_cannot_emit_a_diagnostic_finding(tmp_path: Path) -> None:
    classifier = _Classifier(_RootCauseVerdict(classification="causado_por_diff"))
    store = EngineeringFindingStore(tmp_path / "findings.jsonl")
    request = replace(_request(), pytest_exit=0, mypy_exit=0)

    with pytest.raises(ValueError, match="failed validation"):
        EngineeringDiagnosticCoordinator(store=store, classifier=classifier).diagnose(request)

    assert classifier.calls == []
    assert store.count() == 0


def test_request_factory_captures_existing_validation_report_without_running_it() -> None:
    validation = ValidationReport(
        passed=False,
        pytest_exit=1,
        mypy_exit=0,
        pytest_summary="FAILED tests/test_example.py::test_case",
        mypy_summary="",
    )

    request = EngineeringDiagnosticRequest.from_validation_report(
        validation=validation,
        run_id="run_diagnostic_002",
        task_id=None,
        mission_id=None,
        repository="atlas-core",
        base_revision="a" * 40,
        candidate_revision="b" * 40,
        correlation_id="validation_002",
        command=("python", "-m", "pytest"),
        environment=(),
        at="2026-07-29T13:00:00+00:00",
        severity=FindingSeverity.MAJOR,
        risk=Risk.MEDIUM,
    )

    assert request.pytest_exit == 1
    assert request.mypy_exit == 0
    assert request.pytest_summary == validation.pytest_summary
