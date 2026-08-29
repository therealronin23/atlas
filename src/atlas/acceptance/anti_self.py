"""Cross-field rejection of self-verification in the N+1 acceptance harness.

This bounded validator checks only the frozen independent-witness invariant:
the canonical verifier identity must be disjoint from every materially
constrained actor.  It neither evaluates evidence nor emits, promotes, or
authorizes an acceptance result.  Trust-domain metadata remains descriptive;
it is not used as an automatic proxy for independence.
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from atlas.acceptance.core import IndependenceClass
from atlas.acceptance.identity import VerifierIdentityRegistry


class IndependentWitnessValidationError(ValueError):
    """Base error for a rejected independent-witness binding."""


class ContractIdentityMismatchError(IndependentWitnessValidationError):
    """Raised when a claim is not for the canonical requirement contract."""


class MaterialActorMismatchError(IndependentWitnessValidationError):
    """Raised when a claim omits or substitutes a constrained actor."""


class CanonicalVerifierMismatchError(IndependentWitnessValidationError):
    """Raised when a label names a verifier other than the canonical witness."""


class SelfVerifierError(IndependentWitnessValidationError):
    """Raised when a materially constrained actor verifies itself."""


class IndependentWitnessClassError(IndependentWitnessValidationError):
    """Raised when either declaration is not exactly INDEPENDENT_WITNESS."""


class _FrozenStrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )


_OpaqueId = Annotated[
    str,
    Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$", strict=True),
]
_ContractId = Annotated[
    str,
    Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$", strict=True),
]


class CanonicalIndependentWitnessRequirement(_FrozenStrictModel):
    """Frozen actor and verifier identities required by one contract binding."""

    contract_id: _ContractId
    materially_constrained_actor_identities: tuple[_OpaqueId, ...]
    canonical_verifier_identity: _OpaqueId

    @field_validator("materially_constrained_actor_identities", mode="before")
    @classmethod
    def _require_explicit_actor_collection(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            raise ValueError(
                "materially_constrained_actor_identities must be an array or tuple"
            )
        return value

    @model_validator(mode="after")
    def _require_disjoint_canonical_witness(self) -> Self:
        actors = set(self.materially_constrained_actor_identities)
        if not actors:
            raise ValueError(
                "materially_constrained_actor_identities must not be empty"
            )
        if len(actors) != len(self.materially_constrained_actor_identities):
            raise ValueError("materially constrained actor identities must be unique")
        if self.canonical_verifier_identity in actors:
            raise SelfVerifierError(
                "canonical verifier identity is a materially constrained actor: "
                f"{self.canonical_verifier_identity}"
            )
        return self


class IndependentWitnessClaim(_FrozenStrictModel):
    """Claimed witness identities only; this model has no result/promotion field."""

    contract_id: _ContractId
    materially_constrained_actor_identities: tuple[_OpaqueId, ...]
    verifier_identity: _OpaqueId
    independence_class: IndependenceClass

    @field_validator("materially_constrained_actor_identities", mode="before")
    @classmethod
    def _require_explicit_actor_collection(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            raise ValueError(
                "materially_constrained_actor_identities must be an array or tuple"
            )
        return value

    @field_validator("independence_class", mode="before")
    @classmethod
    def _require_exact_independence_class(cls, value: object) -> object:
        if isinstance(value, IndependenceClass):
            return value
        if not isinstance(value, str):
            raise ValueError("independence_class must be an exact string")
        return value

    @model_validator(mode="after")
    def _require_complete_actor_metadata(self) -> Self:
        actors = set(self.materially_constrained_actor_identities)
        if not actors:
            raise ValueError(
                "materially_constrained_actor_identities must not be empty"
            )
        if len(actors) != len(self.materially_constrained_actor_identities):
            raise ValueError("materially constrained actor identities must be unique")
        return self


class IndependentWitnessBinding(_FrozenStrictModel):
    """A validated invariant binding, intentionally not an acceptance decision."""

    requirement: CanonicalIndependentWitnessRequirement
    claim: IndependentWitnessClaim


class IndependentWitnessValidator:
    """Validate only canonical identity and anti-self witness disjointness."""

    __slots__ = ("_registry",)
    _registry: VerifierIdentityRegistry

    def __init__(self, registry: VerifierIdentityRegistry) -> None:
        object.__setattr__(self, "_registry", registry)

    def __setattr__(self, name: str, value: object) -> None:
        raise TypeError("independent witness validators are immutable")

    def validate(
        self,
        requirement: CanonicalIndependentWitnessRequirement,
        claim: IndependentWitnessClaim,
    ) -> IndependentWitnessBinding:
        """Reject self/ambiguous claims without inferring independence from metadata."""

        validated_requirement = CanonicalIndependentWitnessRequirement.model_validate(
            requirement
        )
        validated_claim = IndependentWitnessClaim.model_validate(claim)

        if validated_claim.independence_class is not IndependenceClass.INDEPENDENT_WITNESS:
            raise IndependentWitnessClassError(
                "claim independence_class must be INDEPENDENT_WITNESS"
            )
        if validated_claim.contract_id != validated_requirement.contract_id:
            raise ContractIdentityMismatchError(
                "claim contract identity does not match canonical requirement: "
                f"{validated_claim.contract_id} != {validated_requirement.contract_id}"
            )
        if (
            set(validated_claim.materially_constrained_actor_identities)
            != set(validated_requirement.materially_constrained_actor_identities)
        ):
            raise MaterialActorMismatchError(
                "claim materially constrained actors do not match canonical "
                f"requirement for {validated_requirement.contract_id}: "
                f"{sorted(validated_claim.materially_constrained_actor_identities)} "
                f"!= {sorted(validated_requirement.materially_constrained_actor_identities)}"
            )
        if (
            validated_claim.verifier_identity
            in validated_claim.materially_constrained_actor_identities
        ):
            raise SelfVerifierError(
                "verifier identity is a materially constrained actor: "
                f"{validated_claim.verifier_identity}"
            )
        if (
            validated_claim.verifier_identity
            != validated_requirement.canonical_verifier_identity
        ):
            raise CanonicalVerifierMismatchError(
                "claim verifier identity does not match canonical verifier: "
                f"{validated_claim.verifier_identity} != "
                f"{validated_requirement.canonical_verifier_identity}"
            )

        metadata = self._registry.require(validated_claim.verifier_identity)
        if metadata.independence_class is not IndependenceClass.INDEPENDENT_WITNESS:
            raise IndependentWitnessClassError(
                "registered verifier metadata must be INDEPENDENT_WITNESS"
            )

        return IndependentWitnessBinding(
            requirement=validated_requirement,
            claim=validated_claim,
        )
