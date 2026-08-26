"""Atlas N+1 WP-EH-CORE acceptance contract and evidence primitives.

This module is deliberately an enablement seam.  It validates frozen contract
identities, A0-A6 levels, result vocabulary and provenance-bound evidence
envelopes.  It does not execute tests, persist receipts, aggregate results,
decide verifier independence, or grant production authority.
"""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import Annotated, Any, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    JsonValue,
    field_validator,
    model_validator,
)
from pydantic_core import CoreSchema, core_schema


class AcceptanceLevel(str, Enum):
    """The frozen A0-A6 maturity levels; no level implies another here."""

    A0_SPEC_INTEGRITY = "A0_SPEC_INTEGRITY"
    A1_COMPONENT_CONTRACT = "A1_COMPONENT_CONTRACT"
    A2_INTERFACE_INTEGRATION = "A2_INTERFACE_INTEGRATION"
    A3_REPLAY_SHADOW = "A3_REPLAY_SHADOW"
    A4_MIGRATION_CUTOVER = "A4_MIGRATION_CUTOVER"
    A5_LIVE_VERIFICATION = "A5_LIVE_VERIFICATION"
    A6_PRODUCT_ACCEPTANCE = "A6_PRODUCT_ACCEPTANCE"


class AcceptanceResult(str, Enum):
    """The complete frozen result vocabulary; UNKNOWN is not a synonym."""

    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    BLOCKED = "BLOCKED"
    NOT_RUN = "NOT_RUN"


class IndependenceClass(str, Enum):
    """Receipt metadata vocabulary from the frozen evidence bundle schema."""

    SELF_REPORTED = "SELF_REPORTED"
    HARNESS_OBSERVED = "HARNESS_OBSERVED"
    INDEPENDENT_WITNESS = "INDEPENDENT_WITNESS"
    EXTERNAL_SOURCE = "EXTERNAL_SOURCE"
    USER_ACCEPTANCE = "USER_ACCEPTANCE"


class DuplicateAcceptanceContractError(ValueError):
    """Raised when one registry would make an identity ambiguous."""


class UnknownAcceptanceContractError(KeyError):
    """Raised when evidence names an identity absent from the registry."""


class AcceptanceLevelMismatchError(ValueError):
    """Raised when evidence claims a level not declared by its contract."""


class _FrozenStrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )


def _require_named_text(value: str) -> str:
    if not value.strip():
        raise ValueError("text must contain at least one non-whitespace character")
    return value


def _contains_control_character(value: str) -> bool:
    return any(unicodedata.category(character) == "Cc" for character in value)


_NonEmptyText = Annotated[
    str,
    Field(min_length=1, max_length=4096, strict=True),
    AfterValidator(_require_named_text),
]
_OpaqueId = Annotated[
    str,
    Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$", strict=True),
]
_ContractId = Annotated[
    str,
    Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$", strict=True),
]
_Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", strict=True)]
_ContractKind = Annotated[
    str,
    Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$", strict=True),
]


def _freeze_json_value(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON numbers must be finite")
    if isinstance(value, dict):
        return _FrozenJsonObject(value)
    if isinstance(value, list):
        return tuple(_freeze_json_value(item) for item in value)
    return value


def _thaw_json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json_value(item) for item in value]
    return value


def _prepare_json_value_for_validation(value: object) -> object:
    if isinstance(value, Mapping):
        prepared: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must already be strings")
            prepared[key] = _prepare_json_value_for_validation(item)
        return prepared
    if isinstance(value, (list, tuple)):
        return [_prepare_json_value_for_validation(item) for item in value]
    return value


class _FrozenJsonObject(Mapping[str, object]):
    """Recursively immutable JSON object with ordinary JSON serialization."""

    __slots__ = ("_data",)
    _data: Mapping[str, object]

    def __init__(self, value: Mapping[str, object]) -> None:
        object.__setattr__(
            self,
            "_data",
            MappingProxyType(
                {key: _freeze_json_value(item) for key, item in value.items()}
            ),
        )

    def __setattr__(self, name: str, value: object) -> None:
        raise TypeError("frozen JSON objects are immutable")

    def __getitem__(self, key: str) -> object:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        json_object_schema = handler.generate_schema(dict[str, JsonValue])
        revalidatable_json_object_schema = (
            core_schema.no_info_before_validator_function(
                _prepare_json_value_for_validation,
                json_object_schema,
            )
        )
        return core_schema.no_info_after_validator_function(
            cls,
            revalidatable_json_object_schema,
            serialization=core_schema.plain_serializer_function_ser_schema(
                _thaw_json_value,
                return_schema=json_object_schema,
            ),
        )


_IdentityValue = _NonEmptyText | _FrozenJsonObject


class ContractProvenance(_FrozenStrictModel):
    """Cryptographic location of one contract record in a frozen authority."""

    artifact_name: _NonEmptyText
    artifact_sha256: _Sha256
    member_path: _NonEmptyText
    member_sha256: _Sha256
    record_sha256: _Sha256

    @field_validator("artifact_name")
    @classmethod
    def _require_zip_basename(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            "\\" in value
            or _contains_control_character(value)
            or bool(PureWindowsPath(value).drive)
            or path.name != value
            or path.suffix.lower() != ".zip"
        ):
            raise ValueError("artifact_name must be a ZIP basename")
        return value

    @field_validator("member_path")
    @classmethod
    def _require_safe_member_path(cls, value: str) -> str:
        if "\\" in value or _contains_control_character(value):
            raise ValueError("member_path must use POSIX separators")
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or bool(PureWindowsPath(value).drive)
            or not path.parts
            or path.as_posix() != value
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("member_path must be a safe relative path")
        return path.as_posix()


class AcceptanceContract(_FrozenStrictModel):
    """Registry metadata only; canonical PASS/FAIL predicates stay external."""

    contract_id: _ContractId
    contract_kind: _ContractKind
    acceptance_levels: tuple[AcceptanceLevel, ...] = ()
    source_canon_ids: tuple[_OpaqueId, ...] = ()
    provenance: ContractProvenance

    @field_validator("acceptance_levels", mode="before")
    @classmethod
    def _require_exact_level_inputs(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            raise ValueError("acceptance_levels must be an array or tuple")
        if any(
            not isinstance(item, (str, AcceptanceLevel))
            for item in value
        ):
            raise ValueError("acceptance levels must be exact strings")
        return value

    @model_validator(mode="after")
    def _require_unambiguous_metadata(self) -> Self:
        if len(set(self.acceptance_levels)) != len(self.acceptance_levels):
            raise ValueError("acceptance_levels must be unique")
        if len(set(self.source_canon_ids)) != len(self.source_canon_ids):
            raise ValueError("source_canon_ids must be unique")
        return self


class AcceptanceContractRegistry:
    """Immutable identity lookup; construction fails closed on duplicates."""

    __slots__ = ("_contracts", "_contract_ids")
    _contracts: Mapping[str, AcceptanceContract]
    _contract_ids: tuple[str, ...]

    def __init__(self, contracts: Iterable[AcceptanceContract]) -> None:
        indexed: dict[str, AcceptanceContract] = {}
        for candidate in contracts:
            contract = AcceptanceContract.model_validate(candidate)
            if contract.contract_id in indexed:
                raise DuplicateAcceptanceContractError(
                    f"duplicate acceptance contract: {contract.contract_id}"
                )
            indexed[contract.contract_id] = contract
        object.__setattr__(self, "_contracts", MappingProxyType(indexed))
        object.__setattr__(self, "_contract_ids", tuple(sorted(indexed)))

    def __setattr__(self, name: str, value: object) -> None:
        raise TypeError("acceptance contract registries are immutable")

    def __len__(self) -> int:
        return len(self._contracts)

    @property
    def contract_ids(self) -> tuple[str, ...]:
        return self._contract_ids

    def require(self, contract_id: str) -> AcceptanceContract:
        try:
            return self._contracts[contract_id]
        except KeyError as exc:
            raise UnknownAcceptanceContractError(
                f"unknown acceptance contract: {contract_id}"
            ) from exc


class EvidenceLocator(_FrozenStrictModel):
    """A locator remains attributable because the referenced bytes are hashed."""

    uri: _NonEmptyText
    sha256: _Sha256


class TimestampOrder(_FrozenStrictModel):
    """Timestamp plus stable run ordering, as required by the frozen schema."""

    timestamp: datetime
    run_id: _OpaqueId
    sequence: Annotated[int, Field(ge=0, strict=True)]

    @field_validator("timestamp", mode="before")
    @classmethod
    def _require_datetime_or_iso_string(cls, value: object) -> object:
        if not isinstance(value, (datetime, str)):
            raise ValueError("timestamp must be a datetime or ISO timestamp string")
        return value

    @field_validator("timestamp")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value


class AcceptanceEvidenceReceipt(_FrozenStrictModel):
    """Strict envelope for one later-authorized acceptance observation.

    The model deliberately carries no aggregation or promotion operation.  A
    PASS is representable only when its falsifier is named; adverse and open
    states remain first-class values and are never normalized here.
    """

    test_contract_id: _ContractId
    result: AcceptanceResult
    target_version_build_identity: _NonEmptyText
    environment_identity: _IdentityValue
    input_corpus_version: _IdentityValue
    verifier_identity: _NonEmptyText
    independence_class: IndependenceClass
    raw_evidence_locator: EvidenceLocator
    derived_metrics: _FrozenJsonObject
    signature_hash_receipt: _NonEmptyText | None
    timestamp_order: TimestampOrder
    source_canon_ids: tuple[_OpaqueId, ...]
    semantic_reproduction_instructions: _NonEmptyText
    known_limitations: _NonEmptyText | tuple[_NonEmptyText, ...]
    falsifier_exercised: tuple[_NonEmptyText, ...] = ()

    @field_validator("result", "independence_class", mode="before")
    @classmethod
    def _require_string_enum_input(cls, value: object) -> object:
        if isinstance(value, (AcceptanceResult, IndependenceClass)):
            return value
        if not isinstance(value, str):
            raise ValueError("enum values must be exact strings")
        return value

    @field_validator("environment_identity", "input_corpus_version")
    @classmethod
    def _require_nonempty_identity(cls, value: _IdentityValue) -> _IdentityValue:
        if isinstance(value, _FrozenJsonObject) and not value:
            raise ValueError("identity objects must not be empty")
        return value

    @field_validator("source_canon_ids")
    @classmethod
    def _require_unique_canon_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("source_canon_ids must name at least one source")
        if len(set(value)) != len(value):
            raise ValueError("source_canon_ids must be unique")
        return value

    @model_validator(mode="after")
    def _require_pass_falsifier(self) -> Self:
        if self.result is AcceptanceResult.PASS and not self.falsifier_exercised:
            raise ValueError("PASS must name the falsifier exercised")
        return self


class BoundAcceptanceEvidence(_FrozenStrictModel):
    """An envelope bound to its frozen registry metadata and one exact level."""

    acceptance_level: AcceptanceLevel
    contract: AcceptanceContract
    receipt: AcceptanceEvidenceReceipt

    @field_validator("acceptance_level", mode="before")
    @classmethod
    def _require_exact_level_input(cls, value: object) -> object:
        if not isinstance(value, (str, AcceptanceLevel)):
            raise ValueError("acceptance level must be an exact string")
        return value

    @model_validator(mode="after")
    def _require_matching_contract(self) -> Self:
        if self.receipt.test_contract_id != self.contract.contract_id:
            raise ValueError("receipt contract identity does not match registry metadata")
        if self.acceptance_level not in self.contract.acceptance_levels:
            raise AcceptanceLevelMismatchError(
                f"{self.acceptance_level.value} is not declared for "
                f"{self.contract.contract_id}"
            )
        missing_sources = set(self.contract.source_canon_ids).difference(
            self.receipt.source_canon_ids
        )
        if missing_sources:
            raise ValueError(
                "receipt source_canon_ids do not cover registered contract "
                f"provenance: {sorted(missing_sources)}"
            )
        return self


class ReceiptEnvelopeAdapter:
    """Validate and bind an envelope without persisting or adjudicating it."""

    def __init__(self, registry: AcceptanceContractRegistry) -> None:
        self._registry = registry

    def bind(
        self,
        payload: Mapping[str, object] | AcceptanceEvidenceReceipt,
        *,
        acceptance_level: AcceptanceLevel | str,
    ) -> BoundAcceptanceEvidence:
        if isinstance(acceptance_level, AcceptanceLevel):
            validated_level = acceptance_level
        elif isinstance(acceptance_level, str):
            try:
                validated_level = AcceptanceLevel(acceptance_level)
            except ValueError as exc:
                raise AcceptanceLevelMismatchError(
                    f"unknown acceptance level: {acceptance_level}"
                ) from exc
        else:
            raise AcceptanceLevelMismatchError(
                "acceptance_level must be an AcceptanceLevel or exact string"
            )
        receipt = AcceptanceEvidenceReceipt.model_validate(
            payload if isinstance(payload, AcceptanceEvidenceReceipt) else dict(payload)
        )
        contract = self._registry.require(receipt.test_contract_id)
        if validated_level not in contract.acceptance_levels:
            raise AcceptanceLevelMismatchError(
                f"{validated_level.value} is not declared for {contract.contract_id}"
            )
        return BoundAcceptanceEvidence(
            acceptance_level=validated_level,
            contract=contract,
            receipt=receipt,
        )
