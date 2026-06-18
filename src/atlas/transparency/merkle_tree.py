"""
Atlas Transparency — RFC 9162 (Certificate Transparency v2) Merkle tree.

Implements the three families of primitives specified in RFC 9162 §2.1:
  - Tree hashing  (§2.1.1 / §2.1.2)
  - Inclusion proofs  (§2.1.3)
  - Consistency proofs  (§2.1.4)

Domain-separation prefixes prevent second-preimage attacks:
  leaf node: sha256(0x00 || data)
  inner node: sha256(0x01 || left || right)
"""

from __future__ import annotations

import hashlib
from typing import Sequence

# ---------------------------------------------------------------------------
# Domain-separated hash primitives  (RFC 9162 §2.1.1)
# ---------------------------------------------------------------------------

_EMPTY_HASH: bytes = hashlib.sha256(b"").digest()


def leaf_hash(data: bytes) -> bytes:
    """sha256(0x00 || data) — RFC 9162 §2.1.1 MTH leaf."""
    return hashlib.sha256(b"\x00" + data).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    """sha256(0x01 || left || right) — RFC 9162 §2.1.1 MTH inner node."""
    return hashlib.sha256(b"\x01" + left + right).digest()


# ---------------------------------------------------------------------------
# Tree root  (RFC 9162 §2.1.2  — MTH)
# ---------------------------------------------------------------------------

def merkle_root(entries: Sequence[bytes]) -> bytes:
    """Return the Merkle Tree Hash of *entries* (RFC 9162 §2.1.2).

    MTH({}) = sha256(b'')  (empty-tree sentinel)
    MTH({d[0]}) = leaf_hash(d[0])
    MTH(D[n]) = node_hash( MTH(D[0:k]), MTH(D[k:n]) )
      where k = largest power-of-two < n.
    """
    n = len(entries)
    if n == 0:
        return _EMPTY_HASH
    return _mth(entries, 0, n)


def _mth(entries: Sequence[bytes], lo: int, hi: int) -> bytes:
    """Recursive MTH over entries[lo:hi]."""
    size = hi - lo
    if size == 1:
        return leaf_hash(entries[lo])
    k = _largest_power_of_two_less_than(size)
    left = _mth(entries, lo, lo + k)
    right = _mth(entries, lo + k, hi)
    return node_hash(left, right)


def _largest_power_of_two_less_than(n: int) -> int:
    """Return the largest power of two strictly less than n (n >= 2).

    Uses integer bit_length() to avoid floating-point precision issues with
    large n (> 2**53 would lose precision with math.log2).
    """
    return 1 << ((n - 1).bit_length() - 1)


# ---------------------------------------------------------------------------
# Inclusion proofs  (RFC 9162 §2.1.3)
# ---------------------------------------------------------------------------

def inclusion_proof(entries: Sequence[bytes], index: int) -> list[bytes]:
    """Return the inclusion proof for entries[index] in the tree.

    The proof is a list of sibling hashes from leaf to root that, together
    with leaf_hash(entries[index]), reproduce the Merkle root.

    Raises IndexError if index is out of range.
    """
    n = len(entries)
    if index < 0 or index >= n:
        raise IndexError(f"index {index} out of range [0, {n})")
    path: list[bytes] = []
    _inclusion_path(entries, 0, n, index, path)
    return path


def _inclusion_path(
    entries: Sequence[bytes], lo: int, hi: int, target: int, path: list[bytes]
) -> None:
    """Recursive helper: append sibling hashes for entries[target] to *path*.

    Siblings are collected leaf-to-root (RFC 9162 §2.1.3.1 PATH ordering):
    recurse first, then append the sibling at this level so the deepest
    sibling appears first in *path*.
    """
    size = hi - lo
    if size == 1:
        # Leaf node — no sibling to append.
        return
    k = _largest_power_of_two_less_than(size)
    mid = lo + k
    if target < mid:
        # target is in the left sub-tree; sibling is the right sub-tree hash.
        _inclusion_path(entries, lo, mid, target, path)
        path.append(_mth(entries, mid, hi))
    else:
        # target is in the right sub-tree; sibling is the left sub-tree hash.
        _inclusion_path(entries, mid, hi, target, path)
        path.append(_mth(entries, lo, mid))


def verify_inclusion(
    leaf: bytes,
    index: int,
    tree_size: int,
    proof: list[bytes],
    root: bytes,
) -> bool:
    """Verify an inclusion proof (RFC 9162 §2.1.3.2).

    Parameters
    ----------
    leaf:       The raw entry bytes (NOT the leaf hash).
    index:      0-based position of the entry in the log.
    tree_size:  Total number of entries at the time the STH was produced.
    proof:      Sibling hashes from inclusion_proof().
    root:       The Merkle root (STH tree hash).

    Returns True iff the proof is valid.
    """
    if tree_size <= 0 or index < 0 or index >= tree_size:
        return False
    try:
        computed = _compute_root_from_inclusion(leaf_hash(leaf), index, tree_size, proof)
    except Exception:
        return False
    return computed == root


def _compute_root_from_inclusion(
    hash_value: bytes, index: int, tree_size: int, proof: list[bytes]
) -> bytes:
    """Walk a proof bottom-up to compute the implied root.

    Algorithm: RFC 9162 §2.1.3.2 (VERIFY_INCLUSION).
    We track fn (0-based leaf index) and sn (last leaf index = tree_size-1).
    At each step:
      - If fn is odd OR fn == sn (rightmost in sub-tree): sibling is to our left.
      - Otherwise: sibling is to our right.
    After combining, divide both fn and sn by 2 to move up, but first strip
    any trailing 1-bits from fn so we align with the RFC's right-edge logic.
    """
    fn = index
    sn = tree_size - 1
    r = hash_value
    for sibling in proof:
        if sn == 0:
            raise ValueError("proof too long")
        if _is_right_child(fn, sn):
            r = node_hash(sibling, r)
            # Move up, stripping completed subtrees on the right edge.
            while fn != 0 and fn % 2 == 0:
                fn //= 2
                sn //= 2
        else:
            r = node_hash(r, sibling)
        fn //= 2
        sn //= 2
    if sn != 0:
        raise ValueError("proof too short")
    return r


def _is_right_child(fn: int, sn: int) -> bool:
    """True when fn is a right-child index or the rightmost node in its subtree."""
    return fn % 2 == 1 or fn == sn


# ---------------------------------------------------------------------------
# Consistency proofs  (RFC 9162 §2.1.4)
# ---------------------------------------------------------------------------

def consistency_proof(
    old_size: int, new_size: int, entries: Sequence[bytes]
) -> list[bytes]:
    """Return a consistency proof that entries[:old_size] ⊆ entries[:new_size].

    The proof lets a verifier holding only old_root and new_root confirm that
    the log was append-only (no rewriting).

    Raises ValueError if sizes are inconsistent with *entries*.
    """
    if old_size < 0 or new_size < 0:
        raise ValueError("sizes must be non-negative")
    if old_size > new_size:
        raise ValueError("old_size must be <= new_size")
    if new_size > len(entries):
        raise ValueError(f"new_size {new_size} exceeds entries length {len(entries)}")
    if old_size == 0 or old_size == new_size:
        return []
    path: list[bytes] = []
    _consistency_path(entries, old_size, new_size, path, first_call=True)
    return path


def _consistency_path(
    entries: Sequence[bytes],
    m: int,
    n: int,
    path: list[bytes],
    first_call: bool,
) -> None:
    """RFC 9162 §2.1.4.1  PROOF(m, D[n]) — recursive consistency path.

    The algorithm from the RFC:
      PROOF(m, D[n]):
        if m == n: return []  (complete sub-tree)
        let k be the largest power of two < n
        if m <= k:
          return PROOF(m, D[0:k]) + [MTH(D[k:n])]
        else:
          return PROOF(m-k, D[k:n]) + [MTH(D[0:k])]

    The `first_call` flag handles the special case where the first node is an
    old-log complete sub-tree root: it is included in the proof only on the
    first call when m is NOT a power of two (RFC 9162 §2.1.4 last paragraph).
    """
    if m == n:
        if not first_call:
            path.append(_mth(entries, 0, n))
        return

    k = _largest_power_of_two_less_than(n)

    if m <= k:
        _consistency_path(entries, m, k, path, first_call=first_call)
        path.append(_mth(entries, k, n))
    else:
        _consistency_path(
            _OffsetView(entries, k), m - k, n - k, path, first_call=False
        )
        path.append(_mth(entries, 0, k))


class _OffsetView(Sequence[bytes]):
    """A zero-copy slice view used by the recursive consistency algorithm."""

    def __init__(self, data: Sequence[bytes], offset: int) -> None:
        self._data = data
        self._offset = offset

    def __len__(self) -> int:
        return len(self._data) - self._offset

    def __getitem__(self, index: object) -> bytes:  # type: ignore[override]
        if isinstance(index, int):
            if index < 0:
                index += len(self)
            if index < 0 or index >= len(self):
                raise IndexError(index)
            return self._data[self._offset + index]
        raise TypeError(f"unsupported index type {type(index)}")


def verify_consistency(
    old_root: bytes,
    old_size: int,
    new_root: bytes,
    new_size: int,
    proof: list[bytes],
) -> bool:
    """Verify a consistency proof (RFC 9162 §2.1.4.2).

    Returns True iff new_root is a valid append-only extension of old_root.
    Returns False for rewrites, truncation, or tampered roots.
    """
    if old_size < 0 or new_size < 0:
        return False
    if old_size > new_size:
        return False
    if old_size == new_size:
        return old_root == new_root and proof == []
    if old_size == 0:
        # Empty log is consistent with anything; proof must be empty.
        return proof == []
    try:
        return _verify_consistency_proof(old_root, old_size, new_root, new_size, proof)
    except Exception:
        return False


def _verify_consistency_proof(
    old_root: bytes,
    old_size: int,
    new_root: bytes,
    new_size: int,
    proof: list[bytes],
) -> bool:
    """Walk the consistency proof to verify both old_root and new_root."""
    # Determine if old_size is a complete sub-tree (power of two).
    # If so, the first proof element doubles as the old-tree root node.
    old_is_power_of_two = old_size > 0 and (old_size & (old_size - 1)) == 0

    if old_is_power_of_two:
        # old root is already a complete subtree; prepend it so the loop works
        # uniformly.
        proof = [old_root] + proof

    if len(proof) < 1:
        return False

    fn = old_size - 1
    sn = new_size - 1

    # Find the first node that corresponds to a complete (old) subtree.
    while fn % 2 == 1:
        fn //= 2
        sn //= 2

    old_hash = proof[0]
    new_hash = proof[0]

    for step in proof[1:]:
        if sn == 0:
            return False
        if fn % 2 == 1 or fn == sn:
            old_hash = node_hash(step, old_hash)
            new_hash = node_hash(step, new_hash)
            while fn % 2 == 0 and fn > 0:
                fn //= 2
                sn //= 2
        else:
            new_hash = node_hash(new_hash, step)
        fn //= 2
        sn //= 2

    return old_hash == old_root and new_hash == new_root
