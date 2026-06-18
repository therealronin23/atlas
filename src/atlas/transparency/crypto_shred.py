"""OSM-007 — Crypto-shredding for GDPR Art. 17 vs. Merkle immutability.

The Merkle log is append-only and must not be rewritten. Under GDPR Art. 17
a subject can demand that their content be irrecoverable after deletion. These
two requirements are reconciled without touching the tree:

  Dual-hash leaf design
  ---------------------
  Each InspectionRecord carries TWO hashes:

    payload_hash  = SHA-256(payload)
      The value the client already signed in CosignedRequest.
      Lives in the leaf permanently; enables APIResponse check 4 (binding).
      For typical AI prompts — long natural-language text — SHA-256 is
      preimage-infeasible, so this is pseudo-anonymous. See honest limits.

    salted_hash   = SHA-256(salt_i || payload)
      An independent per-request hash derived from a randomly-generated
      32-byte salt stored OUTSIDE the Merkle tree in a deletable store.

  GDPR right of erasure (Art. 17): destroy salt_i.  The salted_hash in the
  Merkle tree becomes a dead-end — content cannot be reconstructed even by
  the operator.  The tree's integrity, consistency proofs, and detect_omission()
  are all unaffected because none of them depend on the salt.

Honest limits (paper §6 / OSM-007):
  - payload_hash (unsalted) persists permanently in the tree.  It is pseudo-
    anonymous for typical AI prompts but may be confirmable by brute-force for
    low-entropy inputs (short, predictable queries).
  - Metadata (seq, decision, cause, timestamp_ns) may themselves be personal
    data by usage pattern; crypto-shredding does not cover them.
  - Salt store integrity: a salt leaked before shredding nullifies erasure.
  - This does not resolve the metadata-vs-GDPR tension inherent in a
    mandatory 6-month log required by EU AI Act Art. 12.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SaltedEntry:
    """One per-request salt, NOT stored in the Merkle tree."""

    seq: int
    salt: bytes  # 32 random bytes

    def compute_salted_hash(self, payload: bytes) -> str:
        """Return SHA-256(salt || payload) as hex — the value for InspectionRecord."""
        return hashlib.sha256(self.salt + payload).hexdigest()


class SaltStore:
    """External, deletable store for per-request salts.

    In production this would be a separate access-controlled database table —
    physically separated from the Merkle log so that deleting a row never
    touches the tree.
    """

    def __init__(self) -> None:
        self._salts: dict[int, bytes] = {}

    def register(self, seq: int) -> SaltedEntry:
        """Generate and persist a fresh random salt for *seq*.

        Idempotent: calling again for the same seq returns the same entry.
        """
        if seq not in self._salts:
            self._salts[seq] = os.urandom(32)
        return SaltedEntry(seq=seq, salt=self._salts[seq])

    def shred(self, seq: int) -> None:
        """Destroy the salt for *seq* (GDPR Art. 17 right of erasure).

        After this call the salted_hash committed in the Merkle tree cannot be
        linked to any content, even by the operator.  Idempotent.
        """
        self._salts.pop(seq, None)

    def is_shredded(self, seq: int) -> bool:
        """True if the salt for *seq* has been destroyed (or was never registered)."""
        return seq not in self._salts

    def get_salt(self, seq: int) -> bytes | None:
        """Return the raw salt for *seq*, or None if already shredded."""
        return self._salts.get(seq)
