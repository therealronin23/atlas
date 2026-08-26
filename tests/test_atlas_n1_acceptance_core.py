"""WP-EH-CORE: frozen acceptance vocabulary, registry and evidence envelope."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from atlas.acceptance import (
    AcceptanceContract,
    AcceptanceContractRegistry,
    AcceptanceEvidenceReceipt,
    AcceptanceLevel,
    AcceptanceLevelMismatchError,
    AcceptanceResult,
    BoundAcceptanceEvidence,
    ContractProvenance,
    DuplicateAcceptanceContractError,
    EvidenceLocator,
    IndependenceClass,
    ReceiptEnvelopeAdapter,
    TimestampOrder,
    UnknownAcceptanceContractError,
)


_SHA_A = "a" * 64
_SHA_B = "b" * 64
_CONTRACT_ID = "AC-G-CR-P00-001"


def _provenance() -> ContractProvenance:
    return ContractProvenance(
        artifact_name="CC005R1_BENCHMARK_ACCEPTANCE_ARCHITECTURE.zip",
        artifact_sha256=_SHA_A,
        member_path="03_GUARANTEE_ACCEPTANCE_CONTRACTS_94.jsonl",
        member_sha256=_SHA_B,
        record_sha256="c" * 64,
    )


def _contract() -> AcceptanceContract:
    return AcceptanceContract(
        contract_id=_CONTRACT_ID,
        contract_kind="GUARANTEE",
        acceptance_levels=(
            AcceptanceLevel.A0_SPEC_INTEGRITY,
            AcceptanceLevel.A1_COMPONENT_CONTRACT,
        ),
        source_canon_ids=("CR-P00-001",),
        provenance=_provenance(),
    )


def _receipt_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "test_contract_id": _CONTRACT_ID,
        "result": "PASS",
        "target_version_build_identity": "atlas-core@2161f2b",
        "environment_identity": {"python": "3.12.3", "platform": "linux"},
        "input_corpus_version": "corpus:sha256:fixture-v1",
        "verifier_identity": "pytest:wp-eh-core",
        "independence_class": "HARNESS_OBSERVED",
        "raw_evidence_locator": {
            "uri": "evidence://wp-eh-core/run-001",
            "sha256": "d" * 64,
        },
        "derived_metrics": {"assertions": 8},
        "signature_hash_receipt": None,
        "timestamp_order": {
            "timestamp": "2026-08-26T00:00:00+00:00",
            "run_id": "run-001",
            "sequence": 1,
        },
        "source_canon_ids": ["CR-P00-001"],
        "semantic_reproduction_instructions": "Run the bounded contract test.",
        "known_limitations": [],
        "falsifier_exercised": ["counterexample rejected"],
    }
    payload.update(overrides)
    return payload


def test_frozen_acceptance_vocabularies_are_exact() -> None:
    assert [level.value for level in AcceptanceLevel] == [
        "A0_SPEC_INTEGRITY",
        "A1_COMPONENT_CONTRACT",
        "A2_INTERFACE_INTEGRATION",
        "A3_REPLAY_SHADOW",
        "A4_MIGRATION_CUTOVER",
        "A5_LIVE_VERIFICATION",
        "A6_PRODUCT_ACCEPTANCE",
    ]
    assert [result.value for result in AcceptanceResult] == [
        "PASS",
        "FAIL",
        "INCONCLUSIVE",
        "BLOCKED",
        "NOT_RUN",
    ]
    assert [item.value for item in IndependenceClass] == [
        "SELF_REPORTED",
        "HARNESS_OBSERVED",
        "INDEPENDENT_WITNESS",
        "EXTERNAL_SOURCE",
        "USER_ACCEPTANCE",
    ]

    with pytest.raises(ValueError):
        AcceptanceResult("pass")
    with pytest.raises(ValueError):
        AcceptanceResult("UNKNOWN")
    with pytest.raises(ValueError):
        AcceptanceLevel("A7_GLOBAL_PASS")


def test_registry_is_unique_read_only_and_provenance_bound() -> None:
    contract = _contract()
    registry = AcceptanceContractRegistry([contract])

    assert len(registry) == 1
    assert registry.contract_ids == (_CONTRACT_ID,)
    assert registry.require(_CONTRACT_ID) == contract
    assert registry.require(_CONTRACT_ID).provenance.artifact_sha256 == _SHA_A

    with pytest.raises(DuplicateAcceptanceContractError, match=_CONTRACT_ID):
        AcceptanceContractRegistry([contract, contract])
    with pytest.raises(UnknownAcceptanceContractError, match="AC-MISSING"):
        registry.require("AC-MISSING")
    with pytest.raises(TypeError):
        registry._contracts = {}


def test_registry_revalidates_preconstructed_contract_instances() -> None:
    unvalidated = AcceptanceContract.model_construct(
        contract_id=_CONTRACT_ID,
        contract_kind="GUARANTEE",
        acceptance_levels=("A7_GLOBAL_PASS",),
        source_canon_ids=("CR-P00-001",),
        provenance=_provenance(),
    )

    with pytest.raises(ValidationError):
        AcceptanceContractRegistry([unvalidated])

    invalid_level_type = _contract().model_dump()
    invalid_level_type["acceptance_levels"] = (b"A0_SPEC_INTEGRITY",)
    with pytest.raises(ValidationError):
        AcceptanceContract.model_validate(invalid_level_type)


@pytest.mark.parametrize(
    "artifact_name",
    ["..\\evil.zip", "C:evil.zip", "evil\x00.zip"],
)
def test_contract_provenance_rejects_host_dependent_artifact_names(
    artifact_name: str,
) -> None:
    payload = _provenance().model_dump()
    payload["artifact_name"] = artifact_name
    with pytest.raises(ValidationError):
        ContractProvenance.model_validate(payload)


@pytest.mark.parametrize(
    "member_path",
    ["C:/Windows/system32", "evil\x00.jsonl", "a/./b", "a//b"],
)
def test_contract_provenance_rejects_ambiguous_member_paths(
    member_path: str,
) -> None:
    payload = _provenance().model_dump()
    payload["member_path"] = member_path
    with pytest.raises(ValidationError):
        ContractProvenance.model_validate(payload)


def test_receipt_schema_keeps_every_frozen_required_field_required() -> None:
    required = set(AcceptanceEvidenceReceipt.model_json_schema()["required"])
    assert {
        "test_contract_id",
        "result",
        "target_version_build_identity",
        "environment_identity",
        "input_corpus_version",
        "verifier_identity",
        "independence_class",
        "raw_evidence_locator",
        "derived_metrics",
        "signature_hash_receipt",
        "timestamp_order",
        "source_canon_ids",
        "semantic_reproduction_instructions",
        "known_limitations",
    } <= required

    missing_signature = _receipt_payload()
    del missing_signature["signature_hash_receipt"]
    with pytest.raises(ValidationError):
        AcceptanceEvidenceReceipt.model_validate(missing_signature)


def test_receipt_rejects_non_frozen_result_extra_fields_and_mutable_locator() -> None:
    with pytest.raises(ValidationError):
        AcceptanceEvidenceReceipt.model_validate(
            _receipt_payload(result="UNKNOWN")
        )
    with pytest.raises(ValidationError):
        AcceptanceEvidenceReceipt.model_validate(
            _receipt_payload(unratified_promotion=True)
        )
    with pytest.raises(ValidationError):
        AcceptanceEvidenceReceipt.model_validate(
            _receipt_payload(raw_evidence_locator={"uri": "dashboard://latest"})
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"result": b"PASS"},
        {"target_version_build_identity": b"atlas-core@2161f2b"},
        {"verifier_identity": b"pytest:wp-eh-core"},
        {"independence_class": b"HARNESS_OBSERVED"},
        {
            "raw_evidence_locator": {
                "uri": "evidence://wp-eh-core/run-001",
                "sha256": b"d" * 64,
            }
        },
        {"source_canon_ids": [b"CR-P00-001"]},
        {"derived_metrics": {b"score": 1}},
        {"derived_metrics": {"nested": {b"score": 1}}},
    ],
)
def test_receipt_rejects_non_json_string_coercions(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        AcceptanceEvidenceReceipt.model_validate(_receipt_payload(**overrides))


def test_pass_requires_named_falsifier_but_adverse_states_are_preserved() -> None:
    with pytest.raises(ValidationError, match="falsifier"):
        AcceptanceEvidenceReceipt.model_validate(
            _receipt_payload(falsifier_exercised=[])
        )

    for result in ("FAIL", "INCONCLUSIVE", "BLOCKED", "NOT_RUN"):
        receipt = AcceptanceEvidenceReceipt.model_validate(
            _receipt_payload(result=result, falsifier_exercised=[])
        )
        assert receipt.result.value == result


@pytest.mark.parametrize(
    "overrides",
    [
        {"verifier_identity": " \t "},
        {"falsifier_exercised": ["\n"]},
    ],
)
def test_required_receipt_names_reject_whitespace_only(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        AcceptanceEvidenceReceipt.model_validate(_receipt_payload(**overrides))


@pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), -float("inf")])
def test_receipt_json_numbers_must_be_finite(non_finite: float) -> None:
    with pytest.raises(ValidationError):
        AcceptanceEvidenceReceipt.model_validate(
            _receipt_payload(derived_metrics={"score": non_finite})
        )


def test_timestamp_requires_timezone_and_stable_run_order() -> None:
    with pytest.raises(ValidationError):
        TimestampOrder(
            timestamp=datetime(2026, 8, 26),
            run_id="run-001",
            sequence=1,
        )
    with pytest.raises(ValidationError):
        TimestampOrder(
            timestamp=datetime(2026, 8, 26, tzinfo=timezone.utc),
            run_id="run-001",
            sequence=-1,
        )

    for coerced_sequence in (True, False, "1", 1.0, -0.0):
        with pytest.raises(ValidationError):
            TimestampOrder(
                timestamp=datetime(2026, 8, 26, tzinfo=timezone.utc),
                run_id="run-001",
                sequence=coerced_sequence,
            )

    with pytest.raises(ValidationError):
        TimestampOrder(
            timestamp=1787702400,
            run_id="run-001",
            sequence=1,
        )


def test_adapter_binds_receipt_to_registered_contract_and_declared_level() -> None:
    contract = _contract()
    adapter = ReceiptEnvelopeAdapter(AcceptanceContractRegistry([contract]))

    bound = adapter.bind(
        _receipt_payload(
            environment_identity={"runtime": {"python": "3.12.3"}},
            derived_metrics={"samples": [{"score": 1.0}]},
        ),
        acceptance_level=AcceptanceLevel.A1_COMPONENT_CONTRACT,
    )

    assert isinstance(bound, BoundAcceptanceEvidence)
    assert bound.contract == contract
    assert bound.receipt.test_contract_id == contract.contract_id
    assert bound.acceptance_level is AcceptanceLevel.A1_COMPONENT_CONTRACT

    from_exact_string = adapter.bind(
        _receipt_payload(),
        acceptance_level="A0_SPEC_INTEGRITY",
    )
    assert from_exact_string.acceptance_level is AcceptanceLevel.A0_SPEC_INTEGRITY


def test_adapter_rejects_unknown_contract_and_undeclared_level() -> None:
    adapter = ReceiptEnvelopeAdapter(AcceptanceContractRegistry([_contract()]))

    with pytest.raises(UnknownAcceptanceContractError, match="AC-MISSING"):
        adapter.bind(
            _receipt_payload(test_contract_id="AC-MISSING"),
            acceptance_level=AcceptanceLevel.A0_SPEC_INTEGRITY,
        )
    with pytest.raises(AcceptanceLevelMismatchError, match="A2_INTERFACE_INTEGRATION"):
        adapter.bind(
            _receipt_payload(),
            acceptance_level=AcceptanceLevel.A2_INTERFACE_INTEGRATION,
        )

    with pytest.raises(ValidationError, match="source_canon_ids"):
        adapter.bind(
            _receipt_payload(source_canon_ids=["CR-WRONG"]),
            acceptance_level=AcceptanceLevel.A0_SPEC_INTEGRITY,
        )

    for invalid_level in (b"A0_SPEC_INTEGRITY", "A7_GLOBAL_PASS", 1):
        with pytest.raises(AcceptanceLevelMismatchError):
            adapter.bind(
                _receipt_payload(),
                acceptance_level=invalid_level,
            )


def test_adapter_revalidates_preconstructed_receipt_instances() -> None:
    adapter = ReceiptEnvelopeAdapter(AcceptanceContractRegistry([_contract()]))
    unvalidated = AcceptanceEvidenceReceipt.model_construct(
        **_receipt_payload(result="UNKNOWN")
    )

    with pytest.raises(ValidationError):
        adapter.bind(
            unvalidated,
            acceptance_level=AcceptanceLevel.A0_SPEC_INTEGRITY,
        )


def test_models_are_frozen_after_validation() -> None:
    receipt = AcceptanceEvidenceReceipt.model_validate(_receipt_payload())
    locator = EvidenceLocator(uri="evidence://immutable", sha256="e" * 64)

    with pytest.raises(ValidationError):
        receipt.result = AcceptanceResult.FAIL
    with pytest.raises(ValidationError):
        locator.sha256 = "f" * 64


def test_receipt_json_objects_are_deeply_immutable_and_still_serialize() -> None:
    receipt = AcceptanceEvidenceReceipt.model_validate(
        _receipt_payload(
            environment_identity={"runtime": {"python": "3.12.3"}},
            derived_metrics={"samples": [{"score": 1.0}]},
        )
    )

    with pytest.raises(TypeError):
        receipt.environment_identity["runtime"] = {"python": "tampered"}
    with pytest.raises(TypeError):
        receipt.derived_metrics["samples"][0]["score"] = 0.0
    with pytest.raises(TypeError):
        receipt.derived_metrics._data = {}

    assert receipt.model_dump(mode="json")["derived_metrics"] == {
        "samples": [{"score": 1.0}]
    }
