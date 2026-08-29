"""WP-EH-FAILURE: bounded failure simulation with raw-order capture."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from atlas.acceptance import (
    FAILURE_CORPUS_RETENTION_METADATA,
    CanonicalFalsifierScenario,
    ConcurrencyFailureScenario,
    CrashFailureScenario,
    DeletionFailureScenario,
    DuplicateFailureScenario,
    ErasureFailureScenario,
    ExpiryFailureScenario,
    FailureInjectionFixture,
    FailureInjectionHarness,
    FailureInjectionMode,
    FailureInjectionObservation,
    FailureInjectionTrace,
    LostAcknowledgementFailureScenario,
    PartialFailureScenario,
    RetryFailureScenario,
    RevocationFailureScenario,
    TimeoutFailureScenario,
)


def _scenario_payload(mode: FailureInjectionMode) -> dict[str, object]:
    scenarios: dict[FailureInjectionMode, dict[str, object]] = {
        FailureInjectionMode.CRASH: {
            "mode": "CRASH",
            "process_identity": "process-001",
            "crash_point": "after-durable-write-before-ack",
            "simulated_running_before": True,
            "simulated_running_after": False,
        },
        FailureInjectionMode.TIMEOUT: {
            "mode": "TIMEOUT",
            "operation_identity": "operation-timeout-001",
            "deadline_ms": 100,
            "simulated_elapsed_ms": 101,
        },
        FailureInjectionMode.RETRY: {
            "mode": "RETRY",
            "operation_identity": "operation-retry-001",
            "attempt_number": 2,
            "maximum_attempts": 3,
        },
        FailureInjectionMode.DUPLICATE: {
            "mode": "DUPLICATE",
            "delivery_identity": "delivery-001",
            "occurrence_number": 2,
        },
        FailureInjectionMode.LOST_ACKNOWLEDGEMENT: {
            "mode": "LOST_ACKNOWLEDGEMENT",
            "delivery_identity": "delivery-lost-ack-001",
            "simulated_delivery_observed": True,
            "simulated_acknowledgement_observed": False,
        },
        FailureInjectionMode.REVOCATION: {
            "mode": "REVOCATION",
            "subject_identity": "revocable-subject-001",
            "simulated_valid_before": True,
            "simulated_valid_after": False,
        },
        FailureInjectionMode.EXPIRY: {
            "mode": "EXPIRY",
            "subject_identity": "expiring-subject-001",
            "valid_until": "2026-08-29T00:00:00+00:00",
            "simulated_observed_at": "2026-08-29T00:00:01+00:00",
        },
        FailureInjectionMode.CONCURRENCY: {
            "mode": "CONCURRENCY",
            "resource_identity": "resource-001",
            "shared_precondition_version": "version-001",
            "competing_actor_identities": ("actor-001", "actor-002"),
        },
        FailureInjectionMode.DELETION: {
            "mode": "DELETION",
            "target_identity": "target-delete-001",
            "simulated_present_before": True,
            "simulated_present_after": False,
        },
        FailureInjectionMode.ERASURE: {
            "mode": "ERASURE",
            "protected_target_identity": "protected-target-001",
            "key_handle_identity": "key-handle-001",
            "simulated_key_available_before": True,
            "simulated_key_available_after": False,
        },
        FailureInjectionMode.PARTIAL_FAILURE: {
            "mode": "PARTIAL_FAILURE",
            "operation_identity": "operation-partial-001",
            "total_units": 3,
            "failed_units": 1,
        },
        FailureInjectionMode.CANONICAL_FALSIFIER: {
            "mode": "CANONICAL_FALSIFIER",
            "source_falsifier_identity": "falsifier-CR-P00-001",
            "simulated_counterexample_observed": True,
        },
    }
    return dict(scenarios[mode])


def _fixture(
    fixture_id: str,
    mode: FailureInjectionMode = FailureInjectionMode.CRASH,
    *,
    sequence: int = 1,
    scenario: dict[str, object] | None = None,
) -> FailureInjectionFixture:
    return FailureInjectionFixture.model_validate(
        {
            "fixture_id": fixture_id,
            "test_contract_id": "AC-G-CR-P00-001",
            "semantic_falsifier": (
                "Exercise the bounded source-defined counterexample."
            ),
            "corpus_class_id": "CORPUS-FAILINJ",
            "corpus_version": "CORPUS-FAILINJ:sha256:fixture-v1",
            "source_canon_ids": ("CR-P00-001", "CC006-AR-04"),
            "creator_identity": "pytest-wp-eh-failure",
            "import_source": "local-synthetic-fixture",
            "generation_method": "SYNTHETIC_BOUNDED_FIXTURE",
            "contamination_history": (),
            "retention_metadata": FAILURE_CORPUS_RETENTION_METADATA,
            "raw_order": {
                "timestamp": "2026-08-29T00:00:00+00:00",
                "run_id": "run-failure-001",
                "sequence": sequence,
            },
            "scenario": scenario or _scenario_payload(mode),
        }
    )


def test_failure_mode_vocabulary_covers_frozen_boundary_failures() -> None:
    assert [mode.value for mode in FailureInjectionMode] == [
        "CRASH",
        "TIMEOUT",
        "RETRY",
        "DUPLICATE",
        "LOST_ACKNOWLEDGEMENT",
        "REVOCATION",
        "EXPIRY",
        "CONCURRENCY",
        "DELETION",
        "ERASURE",
        "PARTIAL_FAILURE",
        "CANONICAL_FALSIFIER",
    ]


def test_every_mode_dispatches_a_distinct_typed_satisfied_transition() -> None:
    fixtures = tuple(
        _fixture(f"failure-{index}", mode, sequence=index)
        for index, mode in enumerate(FailureInjectionMode)
    )

    trace = FailureInjectionHarness().simulate(fixtures)

    expected_types = (
        CrashFailureScenario,
        TimeoutFailureScenario,
        RetryFailureScenario,
        DuplicateFailureScenario,
        LostAcknowledgementFailureScenario,
        RevocationFailureScenario,
        ExpiryFailureScenario,
        ConcurrencyFailureScenario,
        DeletionFailureScenario,
        ErasureFailureScenario,
        PartialFailureScenario,
        CanonicalFalsifierScenario,
    )
    assert isinstance(trace, FailureInjectionTrace)
    assert tuple(type(item.simulated_transition) for item in trace.observations) == (
        expected_types
    )
    assert tuple(item.fixture.mode for item in trace.observations) == tuple(
        FailureInjectionMode
    )
    assert all(
        item.simulated_transition == item.fixture.scenario
        for item in trace.observations
    )
    assert all(item.predicate_satisfied is True for item in trace.observations)
    assert all(item.live_effect_emitted is False for item in trace.observations)
    assert all(len(item.fixture_sha256) == 64 for item in trace.observations)


@pytest.mark.parametrize(
    ("mode", "invalid_update"),
    [
        (FailureInjectionMode.CRASH, {"simulated_running_after": True}),
        (FailureInjectionMode.TIMEOUT, {"simulated_elapsed_ms": 100}),
        (FailureInjectionMode.RETRY, {"attempt_number": 1}),
        (FailureInjectionMode.DUPLICATE, {"occurrence_number": 1}),
        (
            FailureInjectionMode.LOST_ACKNOWLEDGEMENT,
            {"simulated_acknowledgement_observed": True},
        ),
        (FailureInjectionMode.REVOCATION, {"simulated_valid_after": True}),
        (
            FailureInjectionMode.EXPIRY,
            {"simulated_observed_at": "2026-08-29T00:00:00+00:00"},
        ),
        (
            FailureInjectionMode.CONCURRENCY,
            {"competing_actor_identities": ("actor-001", "actor-001")},
        ),
        (FailureInjectionMode.DELETION, {"simulated_present_after": True}),
        (FailureInjectionMode.ERASURE, {"simulated_key_available_after": True}),
        (FailureInjectionMode.PARTIAL_FAILURE, {"failed_units": 3}),
        (
            FailureInjectionMode.CANONICAL_FALSIFIER,
            {"simulated_counterexample_observed": False},
        ),
    ],
)
def test_each_mode_rejects_a_non_failure_boundary(
    mode: FailureInjectionMode,
    invalid_update: dict[str, object],
) -> None:
    scenario = _scenario_payload(mode)
    scenario.update(invalid_update)

    with pytest.raises(ValidationError):
        _fixture("failure-invalid-boundary", mode, scenario=scenario)


def test_timeout_retry_and_partial_failure_enforce_numeric_boundaries() -> None:
    retry = _scenario_payload(FailureInjectionMode.RETRY)
    retry.update({"attempt_number": 4, "maximum_attempts": 3})
    partial = _scenario_payload(FailureInjectionMode.PARTIAL_FAILURE)
    partial["failed_units"] = 0

    with pytest.raises(ValidationError, match="maximum_attempts"):
        _fixture("failure-retry-limit", scenario=retry)
    with pytest.raises(ValidationError, match="failed_units"):
        _fixture("failure-partial-zero", scenario=partial)


def test_expiry_requires_timezone_and_observation_after_boundary() -> None:
    naive = _scenario_payload(FailureInjectionMode.EXPIRY)
    naive["valid_until"] = "2026-08-29T00:00:00"
    earlier = _scenario_payload(FailureInjectionMode.EXPIRY)
    earlier["simulated_observed_at"] = "2026-08-28T23:59:59+00:00"

    with pytest.raises(ValidationError, match="timezone"):
        _fixture("failure-expiry-naive", scenario=naive)
    with pytest.raises(ValidationError, match="after valid_until"):
        _fixture("failure-expiry-early", scenario=earlier)


def test_capture_preserves_input_and_raw_order_without_sorting() -> None:
    first = _fixture("failure-first", FailureInjectionMode.RETRY, sequence=9)
    second = _fixture("failure-second", FailureInjectionMode.TIMEOUT, sequence=2)

    trace = FailureInjectionHarness().simulate((first, second))

    assert tuple(item.fixture.fixture_id for item in trace.observations) == (
        "failure-first",
        "failure-second",
    )
    assert tuple(item.fixture.raw_order.sequence for item in trace.observations) == (
        9,
        2,
    )
    assert tuple(item.capture_index for item in trace.observations) == (0, 1)


def test_retry_and_duplicate_retain_the_same_delivery_identity() -> None:
    retry = _scenario_payload(FailureInjectionMode.RETRY)
    retry["operation_identity"] = "delivery-001"
    duplicate = _scenario_payload(FailureInjectionMode.DUPLICATE)
    duplicate["delivery_identity"] = "delivery-001"

    trace = FailureInjectionHarness().simulate(
        (
            _fixture("failure-retry", sequence=1, scenario=retry),
            _fixture("failure-duplicate", sequence=2, scenario=duplicate),
        )
    )

    retry_scenario = trace.observations[0].fixture.scenario
    duplicate_scenario = trace.observations[1].fixture.scenario
    assert isinstance(retry_scenario, RetryFailureScenario)
    assert isinstance(duplicate_scenario, DuplicateFailureScenario)
    assert retry_scenario.operation_identity == "delivery-001"
    assert duplicate_scenario.delivery_identity == "delivery-001"
    assert trace.observations[0].fixture.mode is FailureInjectionMode.RETRY
    assert trace.observations[1].fixture.mode is FailureInjectionMode.DUPLICATE


def test_fixture_keeps_frozen_corpus_provenance_and_retention() -> None:
    fixture = _fixture(
        "failure-falsifier",
        FailureInjectionMode.CANONICAL_FALSIFIER,
    )

    observation = FailureInjectionHarness().simulate((fixture,)).observations[0]

    assert observation.fixture.test_contract_id == "AC-G-CR-P00-001"
    assert observation.fixture.corpus_class_id == "CORPUS-FAILINJ"
    assert observation.fixture.corpus_version == (
        "CORPUS-FAILINJ:sha256:fixture-v1"
    )
    assert observation.fixture.source_canon_ids == (
        "CR-P00-001",
        "CC006-AR-04",
    )
    assert observation.fixture.creator_identity == "pytest-wp-eh-failure"
    assert observation.fixture.import_source == "local-synthetic-fixture"
    assert observation.fixture.generation_method == "SYNTHETIC_BOUNDED_FIXTURE"
    assert observation.fixture.contamination_history == ()
    assert observation.fixture.retention_metadata == (
        FAILURE_CORPUS_RETENTION_METADATA
    )
    assert observation.fixture.semantic_falsifier == (
        "Exercise the bounded source-defined counterexample."
    )


def test_deletion_and_erasure_scenarios_do_not_touch_a_named_target(
    tmp_path: Path,
) -> None:
    governed_target = tmp_path / "governed-state.txt"
    governed_target.write_text("must remain", encoding="utf-8")

    observations = FailureInjectionHarness().simulate(
        (
            _fixture("failure-delete", FailureInjectionMode.DELETION),
            _fixture("failure-erasure", FailureInjectionMode.ERASURE, sequence=2),
        )
    ).observations

    assert all(item.live_effect_emitted is False for item in observations)
    assert governed_target.read_text(encoding="utf-8") == "must remain"


def test_fixture_and_nested_scenario_are_immutable() -> None:
    fixture = _fixture("failure-immutable")

    with pytest.raises(ValidationError):
        fixture.scenario = TimeoutFailureScenario(
            mode=FailureInjectionMode.TIMEOUT,
            operation_identity="operation-002",
            deadline_ms=10,
            simulated_elapsed_ms=11,
        )
    with pytest.raises(ValidationError):
        fixture.scenario.crash_point = "different-point"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "overrides",
    [
        {"scenario": {"mode": "LIVE_DESTRUCTION"}},
        {"scenario": {"mode": b"CRASH"}},
        {"source_canon_ids": ()},
        {"source_canon_ids": ("CR-P00-001", "CR-P00-001")},
        {"semantic_falsifier": "  "},
        {"creator_identity": "  "},
        {"import_source": "  "},
        {"corpus_class_id": "CORPUS-NEG"},
        {"retention_metadata": "retain for 30 days"},
        {"contamination_history": ("known", "known")},
    ],
)
def test_malformed_or_wrong_corpus_fixtures_fail_closed(
    overrides: dict[str, object],
) -> None:
    payload = _fixture("failure-invalid").model_dump(mode="json")
    payload.update(overrides)

    with pytest.raises(ValidationError):
        FailureInjectionFixture.model_validate(payload)


def test_scenario_extra_fields_cannot_smuggle_executable_content() -> None:
    payload = _fixture("failure-callback").model_dump(mode="json")
    payload["scenario"]["callback"] = lambda: None

    with pytest.raises(ValidationError):
        FailureInjectionFixture.model_validate(payload)


def test_harness_revalidates_constructed_fixture_and_content_bindings() -> None:
    malformed = FailureInjectionFixture.model_construct(
        **{
            **_fixture("failure-constructed").model_dump(),
            "scenario": {"mode": "CRASH"},
        }
    )
    with pytest.raises(ValidationError):
        FailureInjectionHarness().simulate((malformed,))

    observation = FailureInjectionHarness().simulate(
        (_fixture("failure-hash"),)
    ).observations[0]
    tampered_fixture = observation.model_dump(mode="json")
    tampered_fixture["fixture"]["scenario"]["crash_point"] = "other-point"
    with pytest.raises(ValidationError, match="fixture_sha256"):
        FailureInjectionObservation.model_validate(tampered_fixture)

    tampered_transition = observation.model_dump(mode="json")
    tampered_transition["simulated_transition"]["crash_point"] = "other-point"
    with pytest.raises(ValidationError, match="simulated_transition"):
        FailureInjectionObservation.model_validate(tampered_transition)

    forged_predicate = observation.model_dump(mode="json")
    forged_predicate["predicate_satisfied"] = False
    with pytest.raises(ValidationError):
        FailureInjectionObservation.model_validate(forged_predicate)

    forged_effect = observation.model_dump(mode="json")
    forged_effect["live_effect_emitted"] = True
    with pytest.raises(ValidationError):
        FailureInjectionObservation.model_validate(forged_effect)


def test_ambiguous_trace_identity_or_order_fails_closed() -> None:
    duplicate_id = (
        _fixture("failure-duplicate-id", sequence=1),
        _fixture("failure-duplicate-id", sequence=2),
    )
    duplicate_order = (
        _fixture("failure-order-1", sequence=1),
        _fixture("failure-order-2", sequence=1),
    )

    with pytest.raises(ValidationError, match="fixture identities must be unique"):
        FailureInjectionHarness().simulate(duplicate_id)
    with pytest.raises(ValidationError, match="raw order identities must be unique"):
        FailureInjectionHarness().simulate(duplicate_order)
    with pytest.raises(ValidationError, match="at least one"):
        FailureInjectionHarness().simulate(())


def test_capture_index_and_trace_cannot_be_forged_reordered_or_omitted() -> None:
    trace = FailureInjectionHarness().simulate(
        (
            _fixture("failure-1", sequence=1),
            _fixture("failure-2", sequence=2),
        )
    )
    reordered = trace.model_dump(mode="json")
    reordered["observations"][0]["capture_index"] = 1
    reordered["observations"][1]["capture_index"] = 0

    with pytest.raises(ValidationError, match="capture indexes"):
        FailureInjectionTrace.model_validate(reordered)

    omitted = trace.model_dump(mode="json")
    omitted["observations"] = omitted["observations"][:1]
    with pytest.raises(ValidationError, match="cover declared fixture identities"):
        FailureInjectionTrace.model_validate(omitted)


def test_failure_harness_exposes_no_result_authority_or_live_callback() -> None:
    assert set(FailureInjectionObservation.model_fields) == {
        "fixture",
        "fixture_sha256",
        "simulated_transition",
        "predicate_satisfied",
        "capture_index",
        "live_effect_emitted",
    }
    assert set(FailureInjectionTrace.model_fields) == {
        "fixture_ids",
        "observations",
    }
    for forbidden in (
        "result",
        "authority",
        "grant",
        "execute",
        "callback",
        "migration",
        "deletion_performed",
    ):
        assert forbidden not in FailureInjectionObservation.model_fields
        assert forbidden not in FailureInjectionTrace.model_fields
