"""WP-EH-ANTI-SELF: cross-field independent-witness validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from atlas.acceptance import (
    CanonicalIndependentWitnessRequirement,
    CanonicalVerifierMismatchError,
    ContractIdentityMismatchError,
    IndependenceClass,
    IndependentWitnessClaim,
    IndependentWitnessClassError,
    IndependentWitnessValidator,
    MaterialActorMismatchError,
    SelfVerifierError,
    UnknownVerifierIdentityError,
    VerifierIdentityMetadata,
    VerifierIdentityRegistry,
)


_CONTRACTS = ("CR-P09-006", "CR-P09-011", "CR-P12-004")


def _registry(
    c14_domain: str = "TZ-07",
    c18_domain: str = "TZ-01",
) -> VerifierIdentityRegistry:
    return VerifierIdentityRegistry(
        [
            VerifierIdentityMetadata(
                verifier_identity="ARC-C14",
                independence_class=IndependenceClass.INDEPENDENT_WITNESS,
                trust_domain=c14_domain,
            ),
            VerifierIdentityMetadata(
                verifier_identity="ARC-C18",
                independence_class=IndependenceClass.INDEPENDENT_WITNESS,
                trust_domain=c18_domain,
            ),
        ]
    )


def _requirement(
    contract_id: str = "CR-P09-006",
    actors: tuple[str, ...] = ("ARC-C14",),
    verifier: str = "ARC-C18",
) -> CanonicalIndependentWitnessRequirement:
    return CanonicalIndependentWitnessRequirement(
        contract_id=contract_id,
        materially_constrained_actor_identities=actors,
        canonical_verifier_identity=verifier,
    )


def _claim(
    contract_id: str = "CR-P09-006",
    actors: tuple[str, ...] = ("ARC-C14",),
    verifier: str = "ARC-C18",
    independence_class: IndependenceClass = IndependenceClass.INDEPENDENT_WITNESS,
) -> IndependentWitnessClaim:
    return IndependentWitnessClaim(
        contract_id=contract_id,
        materially_constrained_actor_identities=actors,
        verifier_identity=verifier,
        independence_class=independence_class,
    )


@pytest.mark.parametrize("contract_id", _CONTRACTS)
def test_c14_under_test_with_c18_canonical_witness_is_valid(
    contract_id: str,
) -> None:
    binding = IndependentWitnessValidator(_registry()).validate(
        _requirement(contract_id),
        _claim(contract_id),
    )

    assert binding.requirement.contract_id == contract_id
    assert binding.claim.verifier_identity == "ARC-C18"
    assert "result" not in type(binding).model_fields


@pytest.mark.parametrize("contract_id", _CONTRACTS)
def test_c14_under_test_with_c14_as_witness_is_rejected_even_with_valid_metadata(
    contract_id: str,
) -> None:
    with pytest.raises(SelfVerifierError, match="ARC-C14"):
        IndependentWitnessValidator(_registry()).validate(
            _requirement(contract_id),
            _claim(contract_id, verifier="ARC-C14"),
        )


def test_different_object_instances_with_same_identity_are_self_verification() -> None:
    requirement = _requirement()
    self_claim = IndependentWitnessClaim.model_validate(
        _claim(verifier="ARC-C14").model_dump()
    )

    assert requirement is not self_claim
    with pytest.raises(SelfVerifierError):
        IndependentWitnessValidator(_registry()).validate(requirement, self_claim)


def test_independent_witness_label_alone_cannot_substitute_canonical_verifier() -> None:
    registry = VerifierIdentityRegistry(
        [
            _registry().require("ARC-C14"),
            _registry().require("ARC-C18"),
            VerifierIdentityMetadata(
                verifier_identity="ARC-C19",
                independence_class=IndependenceClass.INDEPENDENT_WITNESS,
                trust_domain="TZ-02",
            ),
        ]
    )

    with pytest.raises(CanonicalVerifierMismatchError, match="ARC-C18"):
        IndependentWitnessValidator(registry).validate(
            _requirement(),
            _claim(verifier="ARC-C19"),
        )


def test_different_verifier_identity_alone_cannot_substitute_canonical_verifier() -> None:
    registry = VerifierIdentityRegistry(
        [
            _registry().require("ARC-C14"),
            _registry().require("ARC-C18"),
            VerifierIdentityMetadata(
                verifier_identity="verifier:alternate-instance",
                independence_class=IndependenceClass.INDEPENDENT_WITNESS,
                trust_domain="TZ-03",
            ),
        ]
    )

    with pytest.raises(CanonicalVerifierMismatchError):
        IndependentWitnessValidator(registry).validate(
            _requirement(),
            _claim(verifier="verifier:alternate-instance"),
        )


def test_trust_domain_change_cannot_bypass_self_verifier_detection() -> None:
    with pytest.raises(SelfVerifierError):
        IndependentWitnessValidator(_registry(c14_domain="TZ-01")).validate(
            _requirement(),
            _claim(verifier="ARC-C14"),
        )


def test_forged_independence_class_is_rejected() -> None:
    with pytest.raises(IndependentWitnessClassError):
        IndependentWitnessValidator(_registry()).validate(
            _requirement(),
            _claim(independence_class=IndependenceClass.SELF_REPORTED),
        )


def test_forged_registered_independence_class_metadata_is_rejected() -> None:
    registry = VerifierIdentityRegistry(
        [
            _registry().require("ARC-C14"),
            VerifierIdentityMetadata(
                verifier_identity="ARC-C18",
                independence_class=IndependenceClass.SELF_REPORTED,
                trust_domain="TZ-01",
            ),
        ]
    )

    with pytest.raises(IndependentWitnessClassError):
        IndependentWitnessValidator(registry).validate(_requirement(), _claim())


def test_claim_cannot_cross_bind_a_different_contract() -> None:
    with pytest.raises(ContractIdentityMismatchError):
        IndependentWitnessValidator(_registry()).validate(
            _requirement("CR-P09-006"),
            _claim("CR-P09-011"),
        )


def test_claim_actor_set_must_match_the_actual_materially_constrained_actors() -> None:
    with pytest.raises(MaterialActorMismatchError, match="ARC-C14"):
        IndependentWitnessValidator(_registry()).validate(
            _requirement(),
            _claim(actors=("ARC-C19",)),
        )


def test_duplicated_material_actor_identity_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unique"):
        IndependentWitnessClaim.model_validate(
            {
                "contract_id": "CR-P09-006",
                "materially_constrained_actor_identities": ["ARC-C14", "ARC-C14"],
                "verifier_identity": "ARC-C18",
                "independence_class": "INDEPENDENT_WITNESS",
            }
        )


def test_unregistered_canonical_verifier_identity_is_a_validation_failure() -> None:
    with pytest.raises(UnknownVerifierIdentityError, match="ARC-C19"):
        IndependentWitnessValidator(_registry()).validate(
            _requirement(verifier="ARC-C19"),
            _claim(verifier="ARC-C19"),
        )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "contract_id": "CR-P09-006",
            "verifier_identity": "ARC-C18",
            "independence_class": "INDEPENDENT_WITNESS",
        },
        {
            "contract_id": "CR-P09-006",
            "materially_constrained_actor_identities": [],
            "verifier_identity": "ARC-C18",
            "independence_class": "INDEPENDENT_WITNESS",
        },
        {
            "contract_id": "CR-P09-006",
            "materially_constrained_actor_identities": ["ARC-C14"],
            "verifier_identity": "ARC-C18",
            "independence_class": "INDEPENDENT_WITNESS",
            "result": "PASS",
        },
    ],
)
def test_missing_or_incomplete_actor_metadata_never_promotes_independent_pass(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        IndependentWitnessClaim.model_validate(payload)


def test_validator_revalidates_model_construct_bypass_attempts() -> None:
    malformed_claim = IndependentWitnessClaim.model_construct(
        contract_id="CR-P09-006",
        materially_constrained_actor_identities=(),
        verifier_identity="ARC-C18",
        independence_class="INDEPENDENT_WITNESS",
    )
    forged_claim = IndependentWitnessClaim.model_construct(
        contract_id="CR-P09-006",
        materially_constrained_actor_identities=("ARC-C14",),
        verifier_identity="ARC-C14",
        independence_class="INDEPENDENT_WITNESS",
    )
    validator = IndependentWitnessValidator(_registry())

    with pytest.raises(ValidationError):
        validator.validate(_requirement(), malformed_claim)
    with pytest.raises(SelfVerifierError):
        validator.validate(_requirement(), forged_claim)


def test_validator_and_binding_have_no_result_or_authority_promotion_surface() -> None:
    assert set(IndependentWitnessClaim.model_fields) == {
        "contract_id",
        "materially_constrained_actor_identities",
        "verifier_identity",
        "independence_class",
    }
    assert not hasattr(IndependentWitnessValidator(_registry()), "authorize")
