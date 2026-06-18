"""
Atlas Transparency — RFC 9162-style append-only Transparency Log.

Implements T4 of ADR-053: TransparencyLog + SignedTreeHead with inclusion
and consistency proof delegation to merkle_tree.py.

Signed payload format (canonical, documented here):
  JSON with sort_keys=True, separators=(",", ":"):
  {"root_hash": "<hex>", "timestamp": <int_ms>, "tree_size": <int>}

  root_hash: merkle_root of all appended entries, hex-encoded.
  timestamp: milliseconds since Unix epoch (int).
  tree_size: number of entries at the time of signing (int).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from atlas.security.authorization import SigVerifier, Signer
from atlas.transparency.merkle_tree import (
    consistency_proof,
    inclusion_proof,
    merkle_root,
    verify_consistency,
    verify_inclusion,
)

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# SignedTreeHead
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SignedTreeHead:
    """An RFC 9162 Signed Tree Head (STH).

    Attributes
    ----------
    tree_size:  Number of entries covered by this STH.
    root_hash:  Merkle root over those entries (32 bytes).
    timestamp:  Milliseconds since Unix epoch (int).
    signature:  Opaque signature string produced by the log's Signer.
    algo:       Signing algorithm name (from Signer.algo).
    """

    tree_size: int
    root_hash: bytes
    timestamp: int
    signature: str
    algo: str

    # ------------------------------------------------------------------
    # Canonical payload
    # ------------------------------------------------------------------

    def _payload(self) -> bytes:
        """Return the canonical bytes that were/will be signed.

        Format: JSON, sort_keys=True, no spaces:
          {"root_hash": "<lowercase hex>", "timestamp": <int>, "tree_size": <int>}
        """
        doc = {
            "root_hash": self.root_hash.hex(),
            "timestamp": self.timestamp,
            "tree_size": self.tree_size,
        }
        return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(self, sig_verifier: SigVerifier) -> bool:
        """Return True iff the STH signature is valid for *sig_verifier*."""
        try:
            return sig_verifier.verify(self._payload(), self.signature)
        except Exception:
            return False


# ---------------------------------------------------------------------------
# TransparencyLog
# ---------------------------------------------------------------------------


class TransparencyLog:
    """Append-only log with RFC 9162 inclusion and consistency proofs.

    Parameters
    ----------
    signer:
        A :class:`~atlas.security.authorization.Signer` used to sign each STH.
        Injected; no global state.
    """

    def __init__(self, signer: Signer) -> None:
        self._signer = signer
        self._entries: list[bytes] = []

    # ------------------------------------------------------------------
    # Append
    # ------------------------------------------------------------------

    @property
    def tree_size(self) -> int:
        """Current number of entries (monotonically increasing)."""
        return len(self._entries)

    def append(self, entry_bytes: bytes) -> int:
        """Append *entry_bytes* to the log.

        Returns the 0-based index of the new entry.
        tree_size is monotonically increasing after this call.
        """
        index = len(self._entries)
        self._entries.append(entry_bytes)
        return index

    # ------------------------------------------------------------------
    # STH
    # ------------------------------------------------------------------

    def signed_tree_head(self, *, timestamp: int | None = None) -> SignedTreeHead:
        """Produce a SignedTreeHead for the current log state.

        Parameters
        ----------
        timestamp:
            Milliseconds since Unix epoch. Defaults to ``time.time_ns() // 1_000_000``.
        """
        ts = timestamp if timestamp is not None else time.time_ns() // 1_000_000
        root = merkle_root(self._entries)
        size = self.tree_size
        # Build a temporary STH to compute the canonical payload.
        draft = SignedTreeHead(
            tree_size=size,
            root_hash=root,
            timestamp=ts,
            signature="",
            algo=self._signer.algo,
        )
        sig = self._signer.sign(draft._payload())
        return SignedTreeHead(
            tree_size=size,
            root_hash=root,
            timestamp=ts,
            signature=sig,
            algo=self._signer.algo,
        )

    # ------------------------------------------------------------------
    # Proofs
    # ------------------------------------------------------------------

    def prove_inclusion(self, index: int) -> list[bytes]:
        """Return the inclusion proof for the entry at *index*.

        Delegates to :func:`~atlas.transparency.merkle_tree.inclusion_proof`.
        Raises IndexError if *index* is out of range.
        """
        return inclusion_proof(self._entries, index)

    def prove_consistency(self, old_size: int) -> list[bytes]:
        """Return the consistency proof from *old_size* to the current tree_size.

        Delegates to :func:`~atlas.transparency.merkle_tree.consistency_proof`.
        """
        return consistency_proof(old_size, self.tree_size, self._entries)
