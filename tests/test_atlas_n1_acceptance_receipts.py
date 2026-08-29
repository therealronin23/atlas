"""WP-EH-RECEIPTS: immutable capture without acceptance authority."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from atlas.acceptance import (
    AcceptanceEvidenceReceipt,
    AcceptanceResult,
    CapturedAcceptanceReceipt,
    IndependenceClass,
    RECEIPT_RETENTION_METADATA,
    ReceiptCaptureAdapter,
)


def _receipt_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "test_contract_id": "AC-G-CR-P00-001",
        "result": "PASS",
        "target_version_build_identity": "atlas-core@15e9cfc",
        "environment_identity": {"platform": "linux", "python": "3.12.3"},
        "input_corpus_version": "corpus:sha256:receipts-v1",
        "verifier_identity": "pytest:wp-eh-receipts",
        "independence_class": "HARNESS_OBSERVED",
        "raw_evidence_locator": {
            "uri": "evidence://wp-eh-receipts/run-001",
            "sha256": "d" * 64,
        },
        "derived_metrics": {"assertions": 8, "samples": ["negative"]},
        "signature_hash_receipt": None,
        "timestamp_order": {
            "timestamp": "2026-08-29T00:00:00+00:00",
            "run_id": "run-001",
            "sequence": 1,
        },
        "source_canon_ids": ["CR-P00-001"],
        "semantic_reproduction_instructions": "Run the bounded receipt capture test.",
        "known_limitations": ["No external effect is asserted."],
        "falsifier_exercised": ["malformed receipt rejected"],
    }
    payload.update(overrides)
    return payload


def test_capture_is_deterministic_and_preserves_provenance_bound_receipt() -> None:
    adapter = ReceiptCaptureAdapter()
    first = adapter.capture(_receipt_payload())
    second = adapter.capture(
        _receipt_payload(
            environment_identity={"python": "3.12.3", "platform": "linux"},
            derived_metrics={"samples": ["negative"], "assertions": 8},
        )
    )

    assert isinstance(first, CapturedAcceptanceReceipt)
    assert first == second
    assert first.receipt_sha256 == "336baa4cf9d7d708ab847cf0c2e60f525a4f5846d014c53d14ab7c0813cec646"
    assert first.retention_metadata == RECEIPT_RETENTION_METADATA
    assert first.receipt.target_version_build_identity == "atlas-core@15e9cfc"
    assert first.receipt.environment_identity == {"platform": "linux", "python": "3.12.3"}
    assert first.receipt.input_corpus_version == "corpus:sha256:receipts-v1"
    assert first.receipt.verifier_identity == "pytest:wp-eh-receipts"
    assert first.receipt.raw_evidence_locator.uri == "evidence://wp-eh-receipts/run-001"
    assert first.receipt.source_canon_ids == ("CR-P00-001",)
    assert first.receipt.semantic_reproduction_instructions == (
        "Run the bounded receipt capture test."
    )
    assert first.receipt.known_limitations == ("No external effect is asserted.",)


@pytest.mark.parametrize("result", ["FAIL", "INCONCLUSIVE", "BLOCKED", "NOT_RUN"])
def test_capture_preserves_adverse_and_open_results_without_promotion(result: str) -> None:
    captured = ReceiptCaptureAdapter().capture(
        _receipt_payload(result=result, falsifier_exercised=[])
    )

    assert captured.receipt.result.value == result
    assert set(CapturedAcceptanceReceipt.model_fields) == {
        "receipt",
        "receipt_sha256",
        "retention_metadata",
    }


def test_capture_preserves_identity_metadata_without_inferring_independence() -> None:
    captured = ReceiptCaptureAdapter().capture(
        _receipt_payload(independence_class="SELF_REPORTED")
    )

    assert captured.receipt.independence_class is IndependenceClass.SELF_REPORTED
    assert "independent_verification" not in CapturedAcceptanceReceipt.model_fields
    assert "authorization" not in CapturedAcceptanceReceipt.model_fields


@pytest.mark.parametrize(
    "overrides",
    [
        {"result": "UNKNOWN"},
        {"raw_evidence_locator": {"uri": "dashboard://latest"}},
        {"unratified_promotion": True},
    ],
)
def test_capture_fails_closed_for_malformed_or_non_frozen_envelopes(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ReceiptCaptureAdapter().capture(_receipt_payload(**overrides))


def test_capture_revalidates_model_construct_and_binds_content_hash() -> None:
    unvalidated = AcceptanceEvidenceReceipt.model_construct(
        **_receipt_payload(result="UNKNOWN")
    )
    with pytest.raises(ValidationError):
        ReceiptCaptureAdapter().capture(unvalidated)

    captured = ReceiptCaptureAdapter().capture(_receipt_payload())
    tampered = captured.model_dump(mode="json")
    tampered["receipt_sha256"] = "e" * 64
    with pytest.raises(ValidationError, match="receipt_sha256"):
        CapturedAcceptanceReceipt.model_validate(tampered)


def test_capture_retention_has_no_unratified_numeric_duration_and_is_frozen() -> None:
    captured = ReceiptCaptureAdapter().capture(_receipt_payload())

    assert "numeric duration" in captured.retention_metadata
    with pytest.raises(ValidationError):
        captured.retention_metadata = "retain for 30 days"
    with pytest.raises(ValidationError):
        CapturedAcceptanceReceipt.model_validate(
            {**captured.model_dump(mode="json"), "unauthorized_field": True}
        )


def test_capture_does_not_represent_or_assert_an_external_effect() -> None:
    captured = ReceiptCaptureAdapter().capture(_receipt_payload())

    assert captured.receipt.result is AcceptanceResult.PASS
    assert "external_effect" not in CapturedAcceptanceReceipt.model_fields
    assert "effect_certainty" not in CapturedAcceptanceReceipt.model_fields
    assert "signature" not in CapturedAcceptanceReceipt.model_fields


def test_receipt_timestamp_stays_explicit_and_ordered() -> None:
    captured = ReceiptCaptureAdapter().capture(
        _receipt_payload(
            timestamp_order={
                "timestamp": datetime(2026, 8, 29, tzinfo=timezone.utc),
                "run_id": "run-001",
                "sequence": 1,
            }
        )
    )

    assert captured.receipt.timestamp_order.run_id == "run-001"
    assert captured.receipt.timestamp_order.sequence == 1
