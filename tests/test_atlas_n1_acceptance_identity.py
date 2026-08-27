"""WP-EH-IDENTITY: explicit verifier metadata for bounded acceptance tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from atlas.acceptance import (
    DuplicateVerifierIdentityError,
    IndependenceClass,
    UnknownVerifierIdentityError,
    VerifierIdentityMetadata,
    VerifierIdentityRegistry,
)


def _identity(
    verifier_identity: str = "ARC-C14",
    independence_class: IndependenceClass = IndependenceClass.INDEPENDENT_WITNESS,
    trust_domain: str = "TZ-07",
) -> VerifierIdentityMetadata:
    return VerifierIdentityMetadata(
        verifier_identity=verifier_identity,
        independence_class=independence_class,
        trust_domain=trust_domain,
    )


def test_registry_preserves_explicit_verifier_identity_class_and_trust_domain() -> None:
    c14 = _identity()
    c18 = _identity("ARC-C18", trust_domain="TZ-01")
    registry = VerifierIdentityRegistry([c14, c18])

    assert registry.verifier_identities == ("ARC-C14", "ARC-C18")
    assert registry.require("ARC-C14") == c14
    assert registry.require("ARC-C18").independence_class is (
        IndependenceClass.INDEPENDENT_WITNESS
    )
    assert registry.require("ARC-C18").trust_domain == "TZ-01"

    comparison = registry.compare("ARC-C14", "ARC-C18")
    assert comparison.left == c14
    assert comparison.right == c18


@pytest.mark.parametrize(
    "payload",
    [
        {"independence_class": "INDEPENDENT_WITNESS", "trust_domain": "TZ-07"},
        {"verifier_identity": "ARC-C14", "trust_domain": "TZ-07"},
        {
            "verifier_identity": "ARC-C14",
            "independence_class": "INDEPENDENT_WITNESS",
        },
    ],
)
def test_incomplete_metadata_is_not_promoted(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        VerifierIdentityMetadata.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "verifier_identity": "  ",
            "independence_class": "INDEPENDENT_WITNESS",
            "trust_domain": "TZ-07",
        },
        {
            "verifier_identity": b"ARC-C14",
            "independence_class": "INDEPENDENT_WITNESS",
            "trust_domain": "TZ-07",
        },
        {
            "verifier_identity": "ARC-C14",
            "independence_class": "AUTOMATIC",
            "trust_domain": "TZ-07",
        },
        {
            "verifier_identity": "ARC-C14",
            "independence_class": "INDEPENDENT_WITNESS",
            "trust_domain": "TZ-7",
        },
        {
            "verifier_identity": "ARC-C14",
            "independence_class": "INDEPENDENT_WITNESS",
            "trust_domain": b"TZ-07",
        },
    ],
)
def test_invalid_identity_class_or_trust_domain_is_rejected(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        VerifierIdentityMetadata.model_validate(payload)


def test_registry_revalidates_rejects_duplicates_and_is_immutable() -> None:
    unvalidated = VerifierIdentityMetadata.model_construct(
        verifier_identity="ARC-C14",
        independence_class="AUTOMATIC",
        trust_domain="TZ-07",
    )
    with pytest.raises(ValidationError):
        VerifierIdentityRegistry([unvalidated])

    identity = _identity()
    with pytest.raises(DuplicateVerifierIdentityError, match="ARC-C14"):
        VerifierIdentityRegistry([identity, identity])

    registry = VerifierIdentityRegistry([identity])
    with pytest.raises(UnknownVerifierIdentityError, match="MISSING"):
        registry.require("MISSING")
    with pytest.raises(TypeError):
        registry._identities = {}  # type: ignore[misc]


def test_comparison_is_descriptive_and_never_inferrs_independence() -> None:
    self_reported = _identity(
        "verifier:test-a",
        IndependenceClass.SELF_REPORTED,
        "TZ-07",
    )
    same_domain = _identity(
        "verifier:test-b",
        IndependenceClass.SELF_REPORTED,
        "TZ-07",
    )
    other_domain = _identity(
        "verifier:test-c",
        IndependenceClass.SELF_REPORTED,
        "TZ-01",
    )
    registry = VerifierIdentityRegistry([self_reported, same_domain, other_domain])

    comparison = registry.compare("verifier:test-a", "verifier:test-b")
    cross_domain_comparison = registry.compare("verifier:test-a", "verifier:test-c")

    assert comparison.left.independence_class is IndependenceClass.SELF_REPORTED
    assert comparison.right.independence_class is IndependenceClass.SELF_REPORTED
    assert comparison.left.trust_domain == comparison.right.trust_domain == "TZ-07"
    assert (
        cross_domain_comparison.right.independence_class
        is IndependenceClass.SELF_REPORTED
    )
    assert cross_domain_comparison.left.trust_domain != cross_domain_comparison.right.trust_domain
    assert "independent" not in type(comparison).model_fields


def test_identity_models_expose_metadata_only_not_authority() -> None:
    assert set(VerifierIdentityMetadata.model_fields) == {
        "verifier_identity",
        "independence_class",
        "trust_domain",
    }
