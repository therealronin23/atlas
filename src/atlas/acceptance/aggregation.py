"""WP-EH-AGGREGATION: hard acceptance-result aggregation.

The aggregate is derived from a complete required-contract vector.  It keeps
each receipt (or an explicit missing-as-NOT_RUN trace) and exposes no score,
maturity promotion, authority decision, persistence, or migration operation.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, Self

from pydantic import field_validator, model_validator

from atlas.acceptance.core import (
    AcceptanceEvidenceReceipt,
    AcceptanceResult,
    _ContractId,
    _FrozenStrictModel,
)


ACCEPTANCE_AGGREGATION_RULE_ID: Literal["CC005-AGGREGATION-V1"] = (
    "CC005-AGGREGATION-V1"
)

_REPORTING_PRECEDENCE = (
    AcceptanceResult.FAIL,
    AcceptanceResult.BLOCKED,
    AcceptanceResult.INCONCLUSIVE,
    AcceptanceResult.NOT_RUN,
    AcceptanceResult.PASS,
)


def _require_exact_result(value: object) -> object:
    if isinstance(value, AcceptanceResult):
        return value
    if not isinstance(value, str):
        raise ValueError("result must be an exact string")
    return value


class _RequiredContractSet(_FrozenStrictModel):
    contract_ids: tuple[_ContractId, ...]

    @model_validator(mode="after")
    def _require_nonempty_unique_contract_ids(self) -> Self:
        if not self.contract_ids:
            raise ValueError("required contract set must contain at least one identity")
        if len(set(self.contract_ids)) != len(self.contract_ids):
            raise ValueError("required contract identities must be unique")
        return self


class ContractAggregationTrace(_FrozenStrictModel):
    """One required contract and the exact evidence used for its result."""

    test_contract_id: _ContractId
    result: AcceptanceResult
    receipt: AcceptanceEvidenceReceipt | None

    @field_validator("result", mode="before")
    @classmethod
    def _require_exact_result_input(cls, value: object) -> object:
        return _require_exact_result(value)

    @model_validator(mode="after")
    def _bind_result_to_receipt(self) -> Self:
        if self.receipt is None:
            if self.result is not AcceptanceResult.NOT_RUN:
                raise ValueError("a missing required receipt must remain NOT_RUN")
            return self

        receipt = AcceptanceEvidenceReceipt.model_validate(self.receipt)
        if receipt.test_contract_id != self.test_contract_id:
            raise ValueError("trace contract identity must match its receipt")
        if receipt.result is not self.result:
            raise ValueError("trace result must match its receipt result")
        return self


def _derive_result(trace: tuple[ContractAggregationTrace, ...]) -> AcceptanceResult:
    observed = {item.result for item in trace}
    for candidate in _REPORTING_PRECEDENCE:
        if candidate in observed:
            return candidate
    raise ValueError("aggregate trace must contain at least one required contract")


class AcceptanceAggregation(_FrozenStrictModel):
    """Immutable gate result plus the full required per-contract trace."""

    rule_id: Literal["CC005-AGGREGATION-V1"]
    required_contract_ids: tuple[_ContractId, ...]
    result: AcceptanceResult
    contract_trace: tuple[ContractAggregationTrace, ...]

    @field_validator("result", mode="before")
    @classmethod
    def _require_exact_result_input(cls, value: object) -> object:
        return _require_exact_result(value)

    @model_validator(mode="after")
    def _require_result_derived_from_complete_trace(self) -> Self:
        required = _RequiredContractSet(contract_ids=self.required_contract_ids)
        trace = tuple(
            ContractAggregationTrace.model_validate(item)
            for item in self.contract_trace
        )
        if not trace:
            raise ValueError("aggregate trace must contain at least one contract")
        identities = tuple(item.test_contract_id for item in trace)
        if len(set(identities)) != len(identities):
            raise ValueError("aggregate trace contract identities must be unique")
        if identities != required.contract_ids:
            raise ValueError(
                "aggregate trace must cover required contract identities in "
                "declared order"
            )
        if self.result is not _derive_result(trace):
            raise ValueError("aggregate result must be derived from the full contract trace")
        return self


class AcceptanceResultAggregator:
    """Aggregate an exact required set without omission, scoring, or promotion."""

    __slots__ = ()

    def aggregate(
        self,
        *,
        required_contract_ids: Iterable[str],
        receipts: Iterable[AcceptanceEvidenceReceipt],
    ) -> AcceptanceAggregation:
        if isinstance(required_contract_ids, (str, bytes)):
            raise ValueError("required contract identities must be an iterable")
        required = _RequiredContractSet(
            contract_ids=tuple(required_contract_ids),
        )
        required_id_set = set(required.contract_ids)

        observed: dict[str, AcceptanceEvidenceReceipt] = {}
        for candidate in receipts:
            receipt = AcceptanceEvidenceReceipt.model_validate(candidate)
            contract_id = receipt.test_contract_id
            if contract_id in observed:
                raise ValueError(f"duplicate contract result: {contract_id}")
            if contract_id not in required_id_set:
                raise ValueError(f"contract result is not required: {contract_id}")
            observed[contract_id] = receipt

        trace = tuple(
            ContractAggregationTrace(
                test_contract_id=contract_id,
                result=(
                    observed[contract_id].result
                    if contract_id in observed
                    else AcceptanceResult.NOT_RUN
                ),
                receipt=observed.get(contract_id),
            )
            for contract_id in required.contract_ids
        )
        return AcceptanceAggregation(
            rule_id=ACCEPTANCE_AGGREGATION_RULE_ID,
            required_contract_ids=required.contract_ids,
            result=_derive_result(trace),
            contract_trace=trace,
        )
