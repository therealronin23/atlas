"""
Atlas Transparency — RFC 9162 Witness / Split-View Detector.

Implements T6 of ADR-053: Witness observes Signed Tree Heads (STH) from a
transparency log operator, verifies their signatures, and detects split-view
attacks (same tree_size, different root_hash shown to different parties).
"""

from __future__ import annotations

from atlas.security.authorization import SigVerifier
from atlas.transparency.log import SignedTreeHead


class SplitViewError(Exception):
    """Raised when a split-view conflict is detected between two STHs."""


class InvalidSignatureError(Exception):
    """Raised when an STH signature fails verification."""


class Witness:
    """RFC 9162 witness that accumulates STHs and detects split-view attacks.

    Parameters
    ----------
    sig_verifier:
        A :class:`~atlas.security.authorization.SigVerifier` used to verify
        each STH's signature before it is accepted.
    """

    def __init__(self, sig_verifier: SigVerifier) -> None:
        self._verifier = sig_verifier
        # Keyed by tree_size; stores the first accepted STH for that size.
        self._seen: dict[int, SignedTreeHead] = {}

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def observe(self, sth: SignedTreeHead) -> None:
        """Record *sth* after verifying its signature.

        Raises
        ------
        InvalidSignatureError
            If the STH signature does not pass verification.
        SplitViewError
            If a previously-observed STH for the same ``tree_size`` has a
            different ``root_hash`` (split-view detected).
        """
        if not sth.verify(self._verifier):
            raise InvalidSignatureError(
                f"STH signature invalid for tree_size={sth.tree_size}"
            )

        existing = self._seen.get(sth.tree_size)
        if existing is not None:
            if existing.root_hash != sth.root_hash:
                raise SplitViewError(
                    f"Split-view detected for tree_size={sth.tree_size}: "
                    f"root_hash {existing.root_hash.hex()!r} != {sth.root_hash.hex()!r}"
                )
            # Consistent duplicate — silently accept (idempotent).
            return

        self._seen[sth.tree_size] = sth

    def detect_split_view(self, sth_a: SignedTreeHead, sth_b: SignedTreeHead) -> bool:
        """Return True iff *sth_a* and *sth_b* reveal a split-view attack.

        A split-view exists when both STHs cover the same ``tree_size`` but
        disagree on ``root_hash``.  If they cover different tree sizes, this
        method returns False (no conflict detectable from size alone).

        Note: this method does NOT require valid signatures; it is a pure
        structural comparison.  Use :meth:`observe` to enforce signature
        validity before recording STHs.
        """
        if sth_a.tree_size != sth_b.tree_size:
            return False
        return sth_a.root_hash != sth_b.root_hash
