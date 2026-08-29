"""WP-EH-AGGREGATION: hard result propagation with complete trace."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from atlas.acceptance import (
    ACCEPTANCE_AGGREGATION_RULE_ID,
    AcceptanceAggregation,
    AcceptanceEvidenceReceipt,
    AcceptanceResult,
    AcceptanceResultAggregator,
    ContractAggregationTrace,
)


def _receipt(
    contract_id: str,
    result: str = "PASS",
    *,
    derived_metrics: dict[str, object] | None = None,
) -> AcceptanceEvidenceReceipt:
    return AcceptanceEvidenceReceipt.model_validate(
        {
            "test_contract_id": contract_id,
            "result": result,
            "target_version_build_identity": "atlas-core@661af4b",
            "environment_identity": {"platform": "linux", "python": "3.12.3"},
            "input_corpus_version": "corpus:sha256:aggregation-v1",
            "verifier_identity": "pytest:wp-eh-aggregation",
            "independence_class": "HARNESS_OBSERVED",
            "raw_evidence_locator": {
                "uri": f"evidence://wp-eh-aggregation/{contract_id}",
                "sha256": "d" * 64,
            },
            "derived_metrics": derived_metrics or {},
            "signature_hash_receipt": None,
            "timestamp_order": {
                "timestamp": "2026-08-29T00:00:00+00:00",
                "run_id": "run-aggregation-001",
                "sequence": 1,
            },
            "source_canon_ids": ["CC005-AGGREGATION-V1"],
            "semantic_reproduction_instructions": (
                "Aggregate the exact required contract vector."
            ),
            "known_limitations": ["No higher acceptance level is inferred."],
            "falsifier_exercised": (
                ["hard result normalization rejected"] if result == "PASS" else []
            ),
        }
    )


def test_complete_pass_vector_is_required_for_aggregate_pass() -> None:
    aggregate = AcceptanceResultAggregator().aggregate(
        required_contract_ids=("AC-001", "AC-002"),
        receipts=(_receipt("AC-001"), _receipt("AC-002")),
    )

    assert aggregate.rule_id == ACCEPTANCE_AGGREGATION_RULE_ID
    assert aggregate.required_contract_ids == ("AC-001", "AC-002")
    assert aggregate.result is AcceptanceResult.PASS
    assert tuple(item.test_contract_id for item in aggregate.contract_trace) == (
        "AC-001",
        "AC-002",
    )
    assert tuple(item.result for item in aggregate.contract_trace) == (
        AcceptanceResult.PASS,
        AcceptanceResult.PASS,
    )
    assert all(item.receipt is not None for item in aggregate.contract_trace)


@pytest.mark.parametrize(
    ("contract_result", "aggregate_result"),
    [
        ("FAIL", AcceptanceResult.FAIL),
        ("BLOCKED", AcceptanceResult.BLOCKED),
        ("INCONCLUSIVE", AcceptanceResult.INCONCLUSIVE),
        ("NOT_RUN", AcceptanceResult.NOT_RUN),
    ],
)
def test_each_non_pass_state_prevents_pass_without_normalization(
    contract_result: str,
    aggregate_result: AcceptanceResult,
) -> None:
    aggregate = AcceptanceResultAggregator().aggregate(
        required_contract_ids=("AC-PASS", "AC-ADVERSE"),
        receipts=(
            _receipt("AC-PASS"),
            _receipt("AC-ADVERSE", contract_result),
        ),
    )

    assert aggregate.result is aggregate_result
    assert aggregate.contract_trace[1].result is aggregate_result
    assert aggregate.contract_trace[1].receipt is not None


@pytest.mark.parametrize(
    ("results", "expected"),
    [
        (("FAIL", "BLOCKED", "INCONCLUSIVE", "NOT_RUN"), AcceptanceResult.FAIL),
        (("BLOCKED", "INCONCLUSIVE", "NOT_RUN"), AcceptanceResult.BLOCKED),
        (("INCONCLUSIVE", "NOT_RUN"), AcceptanceResult.INCONCLUSIVE),
    ],
)
def test_reporting_precedence_is_fail_blocked_inconclusive_not_run(
    results: tuple[str, ...],
    expected: AcceptanceResult,
) -> None:
    contract_ids = tuple(f"AC-{index}" for index in range(len(results)))

    aggregate = AcceptanceResultAggregator().aggregate(
        required_contract_ids=contract_ids,
        receipts=tuple(
            _receipt(contract_id, result)
            for contract_id, result in zip(contract_ids, results, strict=True)
        ),
    )

    assert aggregate.result is expected


def test_missing_required_contract_is_retained_as_not_run_not_omitted() -> None:
    aggregate = AcceptanceResultAggregator().aggregate(
        required_contract_ids=("AC-001", "AC-002"),
        receipts=(_receipt("AC-001"),),
    )

    assert aggregate.result is AcceptanceResult.NOT_RUN
    assert aggregate.contract_trace == (
        ContractAggregationTrace(
            test_contract_id="AC-001",
            result=AcceptanceResult.PASS,
            receipt=_receipt("AC-001"),
        ),
        ContractAggregationTrace(
            test_contract_id="AC-002",
            result=AcceptanceResult.NOT_RUN,
            receipt=None,
        ),
    )


def test_percentage_metrics_cannot_average_away_a_required_failure() -> None:
    aggregate = AcceptanceResultAggregator().aggregate(
        required_contract_ids=("AC-001", "AC-002"),
        receipts=(
            _receipt("AC-001", derived_metrics={"coverage_percent": 100}),
            _receipt(
                "AC-002",
                "FAIL",
                derived_metrics={"coverage_percent": 99.999},
            ),
        ),
    )

    assert aggregate.result is AcceptanceResult.FAIL
    assert [
        item.receipt.derived_metrics
        for item in aggregate.contract_trace
        if item.receipt is not None
    ] == [{"coverage_percent": 100}, {"coverage_percent": 99.999}]
    assert "score" not in AcceptanceAggregation.model_fields
    assert "percentage" not in AcceptanceAggregation.model_fields


@pytest.mark.parametrize(
    ("required_contract_ids", "receipts", "message"),
    [
        ((), (), "at least one"),
        (("AC-001", "AC-001"), (_receipt("AC-001"),), "unique"),
        (
            ("AC-001",),
            (_receipt("AC-001"), _receipt("AC-001")),
            "duplicate",
        ),
        (("AC-001",), (_receipt("AC-002"),), "not required"),
    ],
)
def test_ambiguous_or_out_of_scope_contract_vectors_fail_closed(
    required_contract_ids: tuple[str, ...],
    receipts: tuple[AcceptanceEvidenceReceipt, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        AcceptanceResultAggregator().aggregate(
            required_contract_ids=required_contract_ids,
            receipts=receipts,
        )


def test_aggregate_and_trace_revalidate_constructed_or_tampered_inputs() -> None:
    malformed_receipt = AcceptanceEvidenceReceipt.model_construct(
        **{
            **_receipt("AC-001").model_dump(),
            "result": "UNKNOWN",
        }
    )
    with pytest.raises(ValidationError):
        AcceptanceResultAggregator().aggregate(
            required_contract_ids=("AC-001",),
            receipts=(malformed_receipt,),
        )

    failed = AcceptanceResultAggregator().aggregate(
        required_contract_ids=("AC-001",),
        receipts=(_receipt("AC-001", "FAIL"),),
    )
    forged_pass = failed.model_dump(mode="json")
    forged_pass["result"] = "PASS"
    with pytest.raises(ValidationError, match="derived from the full contract trace"):
        AcceptanceAggregation.model_validate(forged_pass)


@pytest.mark.parametrize("omitted_result", ["FAIL", None])
def test_tampering_cannot_omit_an_adverse_or_missing_required_trace(
    omitted_result: str | None,
) -> None:
    receipts = (
        (_receipt("AC-PASS"), _receipt("AC-OMITTED", omitted_result))
        if omitted_result is not None
        else (_receipt("AC-PASS"),)
    )
    aggregate = AcceptanceResultAggregator().aggregate(
        required_contract_ids=("AC-PASS", "AC-OMITTED"),
        receipts=receipts,
    )
    tampered = aggregate.model_dump(mode="json")
    tampered["contract_trace"] = tampered["contract_trace"][:1]
    tampered["result"] = "PASS"

    with pytest.raises(ValidationError, match="cover required contract identities"):
        AcceptanceAggregation.model_validate(tampered)


def test_trace_cannot_detach_result_or_contract_identity_from_receipt() -> None:
    receipt = _receipt("AC-001", "FAIL")

    with pytest.raises(ValidationError, match="result"):
        ContractAggregationTrace(
            test_contract_id="AC-001",
            result=AcceptanceResult.PASS,
            receipt=receipt,
        )
    with pytest.raises(ValidationError, match="identity"):
        ContractAggregationTrace(
            test_contract_id="AC-002",
            result=AcceptanceResult.FAIL,
            receipt=receipt,
        )


def test_aggregate_has_no_authority_promotion_or_maturity_surface() -> None:
    assert set(AcceptanceAggregation.model_fields) == {
        "rule_id",
        "required_contract_ids",
        "result",
        "contract_trace",
    }
    assert "authority" not in AcceptanceAggregation.model_fields
    assert "acceptance_level" not in AcceptanceAggregation.model_fields
    assert "promoted_result" not in AcceptanceAggregation.model_fields

    aggregate = AcceptanceResultAggregator().aggregate(
        required_contract_ids=("AC-001",),
        receipts=(_receipt("AC-001"),),
    )
    with pytest.raises(ValidationError):
        aggregate.result = AcceptanceResult.FAIL
