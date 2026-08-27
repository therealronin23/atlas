"""Explicit verifier metadata for the isolated Atlas N+1 acceptance harness.

This module records identity, declared independence class, and trust-domain
metadata for tests.  It deliberately does not decide independence, reject
self-verification, grant authority, or promote any acceptance result.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from atlas.acceptance.core import IndependenceClass


class DuplicateVerifierIdentityError(ValueError):
    """Raised when one identity would have ambiguous verifier metadata."""


class UnknownVerifierIdentityError(KeyError):
    """Raised when requested verifier metadata is not registered."""


class _FrozenStrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )


_VerifierIdentity = Annotated[
    str,
    Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$", strict=True),
]
_TrustDomain = Annotated[str, Field(pattern=r"^TZ-[0-9]{2}$", strict=True)]


class VerifierIdentityMetadata(_FrozenStrictModel):
    """Declared metadata only; its class never implies independence."""

    verifier_identity: _VerifierIdentity
    independence_class: IndependenceClass
    trust_domain: _TrustDomain

    @field_validator("independence_class", mode="before")
    @classmethod
    def _require_exact_independence_class(cls, value: object) -> object:
        if isinstance(value, IndependenceClass):
            return value
        if not isinstance(value, str):
            raise ValueError("independence_class must be an exact string")
        return value


class TrustDomainComparison(_FrozenStrictModel):
    """A descriptive pair of registry records, without a semantic verdict."""

    left: VerifierIdentityMetadata
    right: VerifierIdentityMetadata


class VerifierIdentityRegistry:
    """Immutable lookup and descriptive comparison for verifier test metadata."""

    __slots__ = ("_identities", "_verifier_identities")
    _identities: Mapping[str, VerifierIdentityMetadata]
    _verifier_identities: tuple[str, ...]

    def __init__(self, identities: Iterable[VerifierIdentityMetadata]) -> None:
        indexed: dict[str, VerifierIdentityMetadata] = {}
        for candidate in identities:
            identity = VerifierIdentityMetadata.model_validate(candidate)
            if identity.verifier_identity in indexed:
                raise DuplicateVerifierIdentityError(
                    "duplicate verifier identity: "
                    f"{identity.verifier_identity}"
                )
            indexed[identity.verifier_identity] = identity
        object.__setattr__(self, "_identities", MappingProxyType(indexed))
        object.__setattr__(
            self,
            "_verifier_identities",
            tuple(sorted(indexed)),
        )

    def __setattr__(self, name: str, value: object) -> None:
        raise TypeError("verifier identity registries are immutable")

    @property
    def verifier_identities(self) -> tuple[str, ...]:
        return self._verifier_identities

    def require(self, verifier_identity: str) -> VerifierIdentityMetadata:
        try:
            return self._identities[verifier_identity]
        except KeyError as exc:
            raise UnknownVerifierIdentityError(
                f"unknown verifier identity: {verifier_identity}"
            ) from exc

    def compare(
        self,
        left_verifier_identity: str,
        right_verifier_identity: str,
    ) -> TrustDomainComparison:
        return TrustDomainComparison(
            left=self.require(left_verifier_identity),
            right=self.require(right_verifier_identity),
        )
