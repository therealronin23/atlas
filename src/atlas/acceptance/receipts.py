"""WP-EH-RECEIPTS: deterministic capture of provenance-bound observations.

Capture creates an immutable content-hash receipt record.  It neither persists
evidence nor adjudicates results, verifier independence, external effects, or
production authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Self

from pydantic import field_validator, model_validator

from atlas.acceptance.core import (
    AcceptanceEvidenceReceipt,
    _FrozenStrictModel,
    _Sha256,
)


RECEIPT_RETENTION_METADATA = (
    "Retain corpus identity/version and raw evidence as long as dependent "
    "acceptance/rollback/audit claims remain valid; no unratified numeric "
    "duration invented."
)


def _canonical_receipt_bytes(receipt: AcceptanceEvidenceReceipt) -> bytes:
    """Produce the one stable byte representation used for the content hash."""

    return json.dumps(
        receipt.model_dump(mode="json"),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _receipt_sha256(receipt: AcceptanceEvidenceReceipt) -> str:
    return hashlib.sha256(_canonical_receipt_bytes(receipt)).hexdigest()


class CapturedAcceptanceReceipt(_FrozenStrictModel):
    """Immutable capture metadata, not evidence, an authorization, or a decision.

    ``receipt_sha256`` is a content hash of the canonical receipt bytes.  It is
    deliberately not represented as a cryptographic signature.
    """

    receipt: AcceptanceEvidenceReceipt
    receipt_sha256: _Sha256
    retention_metadata: str

    @field_validator("retention_metadata")
    @classmethod
    def _require_frozen_retention_metadata(cls, value: str) -> str:
        if value != RECEIPT_RETENTION_METADATA:
            raise ValueError("retention_metadata must use the frozen instruction")
        return value

    @model_validator(mode="after")
    def _require_receipt_content_binding(self) -> Self:
        validated_receipt = AcceptanceEvidenceReceipt.model_validate(self.receipt)
        expected_sha256 = _receipt_sha256(validated_receipt)
        if self.receipt_sha256 != expected_sha256:
            raise ValueError("receipt_sha256 must bind the canonical receipt bytes")
        return self


class ReceiptCaptureAdapter:
    """Revalidate and capture a receipt without persistence or promotion."""

    __slots__ = ()

    def capture(
        self,
        payload: Mapping[str, object] | AcceptanceEvidenceReceipt,
    ) -> CapturedAcceptanceReceipt:
        if isinstance(payload, AcceptanceEvidenceReceipt):
            receipt = AcceptanceEvidenceReceipt.model_validate(payload)
        elif isinstance(payload, Mapping):
            receipt = AcceptanceEvidenceReceipt.model_validate(dict(payload))
        else:
            raise TypeError("receipt payload must be a mapping or receipt envelope")
        return CapturedAcceptanceReceipt(
            receipt=receipt,
            receipt_sha256=_receipt_sha256(receipt),
            retention_metadata=RECEIPT_RETENTION_METADATA,
        )
