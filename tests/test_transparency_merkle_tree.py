"""Tests for RFC 9162 Merkle tree primitives (T1/T2/T3 of ADR-053)."""

from __future__ import annotations

import hashlib

import pytest

from atlas.transparency.merkle_tree import (
    _largest_power_of_two_less_than,
    consistency_proof,
    inclusion_proof,
    leaf_hash,
    merkle_root,
    node_hash,
    verify_consistency,
    verify_inclusion,
)


# ---------------------------------------------------------------------------
# T1 — Tree hashing
# ---------------------------------------------------------------------------


class TestLeafAndNodeHash:
    def test_leaf_hash_prefix(self) -> None:
        data = b"hello"
        expected = hashlib.sha256(b"\x00" + data).digest()
        assert leaf_hash(data) == expected

    def test_node_hash_prefix(self) -> None:
        l = leaf_hash(b"a")
        r = leaf_hash(b"b")
        expected = hashlib.sha256(b"\x01" + l + r).digest()
        assert node_hash(l, r) == expected

    def test_node_hash_not_commutative(self) -> None:
        l = leaf_hash(b"a")
        r = leaf_hash(b"b")
        assert node_hash(l, r) != node_hash(r, l)


class TestMerkleRoot:
    def test_empty_list(self) -> None:
        assert merkle_root([]) == hashlib.sha256(b"").digest()

    def test_single_entry(self) -> None:
        data = b"one"
        assert merkle_root([data]) == leaf_hash(data)

    def test_two_entries(self) -> None:
        a, b = b"a", b"b"
        expected = node_hash(leaf_hash(a), leaf_hash(b))
        assert merkle_root([a, b]) == expected

    def test_three_entries(self) -> None:
        # RFC 9162 §2.1.2: k=2 (largest power-of-two < 3)
        # MTH({a,b,c}) = node_hash(MTH({a,b}), MTH({c}))
        a, b, c = b"a", b"b", b"c"
        left = node_hash(leaf_hash(a), leaf_hash(b))
        right = leaf_hash(c)
        assert merkle_root([a, b, c]) == node_hash(left, right)

    def test_four_entries_balanced(self) -> None:
        entries = [b"a", b"b", b"c", b"d"]
        left = node_hash(leaf_hash(b"a"), leaf_hash(b"b"))
        right = node_hash(leaf_hash(b"c"), leaf_hash(b"d"))
        assert merkle_root(entries) == node_hash(left, right)

    def test_deterministic(self) -> None:
        entries = [b"x", b"y", b"z"]
        assert merkle_root(entries) == merkle_root(entries)

    def test_order_matters(self) -> None:
        assert merkle_root([b"a", b"b"]) != merkle_root([b"b", b"a"])


# ---------------------------------------------------------------------------
# T2 — Inclusion proofs
# ---------------------------------------------------------------------------


class TestInclusionProof:
    def _entries(self, n: int) -> list[bytes]:
        return [f"entry-{i}".encode() for i in range(n)]

    def test_single_entry_proof_empty(self) -> None:
        entries = [b"only"]
        proof = inclusion_proof(entries, 0)
        assert proof == []

    def test_proof_two_entries_index0(self) -> None:
        entries = [b"a", b"b"]
        proof = inclusion_proof(entries, 0)
        assert len(proof) == 1
        assert proof[0] == leaf_hash(b"b")

    def test_proof_two_entries_index1(self) -> None:
        entries = [b"a", b"b"]
        proof = inclusion_proof(entries, 1)
        assert len(proof) == 1
        assert proof[0] == leaf_hash(b"a")

    def test_inclusion_proof_index_out_of_range(self) -> None:
        with pytest.raises(IndexError):
            inclusion_proof([b"a"], 1)

    def test_verify_inclusion_valid(self) -> None:
        entries = self._entries(8)
        root = merkle_root(entries)
        for i in range(8):
            proof = inclusion_proof(entries, i)
            assert verify_inclusion(entries[i], i, 8, proof, root), f"failed at {i}"

    def test_verify_inclusion_seven_entries(self) -> None:
        entries = self._entries(7)
        root = merkle_root(entries)
        for i in range(7):
            proof = inclusion_proof(entries, i)
            assert verify_inclusion(entries[i], i, 7, proof, root), f"failed at {i}"

    def test_verify_inclusion_wrong_leaf(self) -> None:
        entries = self._entries(4)
        root = merkle_root(entries)
        proof = inclusion_proof(entries, 0)
        assert not verify_inclusion(b"not-in-tree", 0, 4, proof, root)

    def test_verify_inclusion_wrong_index(self) -> None:
        entries = self._entries(4)
        root = merkle_root(entries)
        proof = inclusion_proof(entries, 0)
        # Proof built for index 0 should fail when claiming index 1.
        assert not verify_inclusion(entries[0], 1, 4, proof, root)

    def test_verify_inclusion_tampered_root(self) -> None:
        entries = self._entries(4)
        root = merkle_root(entries)
        proof = inclusion_proof(entries, 0)
        bad_root = bytes(b ^ 0xFF for b in root)
        assert not verify_inclusion(entries[0], 0, 4, proof, bad_root)

    def test_verify_inclusion_tampered_proof(self) -> None:
        entries = self._entries(4)
        root = merkle_root(entries)
        proof = inclusion_proof(entries, 0)
        bad_proof = [bytes(b ^ 0xFF for b in proof[0])] + proof[1:]
        assert not verify_inclusion(entries[0], 0, 4, bad_proof, root)

    def test_verify_inclusion_absent_entry(self) -> None:
        entries = self._entries(4)
        root = merkle_root(entries)
        proof = inclusion_proof(entries, 0)
        # Using an entry not in the tree at any index.
        assert not verify_inclusion(b"absent", 0, 4, proof, root)

    def test_verify_inclusion_index_out_of_tree_size(self) -> None:
        entries = self._entries(4)
        root = merkle_root(entries)
        proof = inclusion_proof(entries, 0)
        assert not verify_inclusion(entries[0], 4, 4, proof, root)

    def test_verify_inclusion_single_entry(self) -> None:
        entries = [b"solo"]
        root = merkle_root(entries)
        proof = inclusion_proof(entries, 0)
        assert verify_inclusion(b"solo", 0, 1, proof, root)

    def test_verify_inclusion_large_tree(self) -> None:
        entries = self._entries(100)
        root = merkle_root(entries)
        for i in [0, 1, 50, 99]:
            proof = inclusion_proof(entries, i)
            assert verify_inclusion(entries[i], i, 100, proof, root)


# ---------------------------------------------------------------------------
# T3 — Consistency proofs
# ---------------------------------------------------------------------------


class TestConsistencyProof:
    def _entries(self, n: int) -> list[bytes]:
        return [f"log-{i}".encode() for i in range(n)]

    def test_empty_to_nonempty_proof_empty(self) -> None:
        entries = self._entries(5)
        assert consistency_proof(0, 5, entries) == []

    def test_same_size_proof_empty(self) -> None:
        entries = self._entries(4)
        assert consistency_proof(4, 4, entries) == []

    def test_verify_consistency_same_size(self) -> None:
        entries = self._entries(4)
        root = merkle_root(entries)
        assert verify_consistency(root, 4, root, 4, [])

    def test_verify_consistency_same_size_wrong_root(self) -> None:
        entries = self._entries(4)
        root = merkle_root(entries)
        bad = bytes(b ^ 0x01 for b in root)
        assert not verify_consistency(root, 4, bad, 4, [])

    def test_verify_consistency_append_only(self) -> None:
        entries = self._entries(8)
        for old_size in range(1, 8):
            old_root = merkle_root(entries[:old_size])
            new_root = merkle_root(entries)
            proof = consistency_proof(old_size, 8, entries)
            assert verify_consistency(old_root, old_size, new_root, 8, proof), (
                f"failed for old_size={old_size}"
            )

    def test_verify_consistency_arbitrary_sizes(self) -> None:
        entries = self._entries(20)
        for old_size in [1, 3, 5, 7, 10, 15, 19]:
            for new_size in [old_size, old_size + 1, 20]:
                if new_size < old_size:
                    continue
                old_root = merkle_root(entries[:old_size])
                new_root = merkle_root(entries[:new_size])
                proof = consistency_proof(old_size, new_size, entries)
                assert verify_consistency(
                    old_root, old_size, new_root, new_size, proof
                ), f"failed for ({old_size}, {new_size})"

    def test_verify_consistency_rewritten_history(self) -> None:
        """If the log was mutated, old_root does not match the tampered new log."""
        original = self._entries(4)
        tampered = [b"TAMPERED", original[1], original[2], original[3]]
        old_root = merkle_root(original[:4])   # root before tampering
        new_root = merkle_root(tampered)        # root of tampered log
        proof = consistency_proof(4, 4, tampered)
        # Sizes are equal, so proof is [] and old != new.
        assert not verify_consistency(old_root, 4, new_root, 4, proof)

    def test_verify_consistency_rewritten_with_extension(self) -> None:
        """Rewrite then extend: consistency proof built on tampered data must fail."""
        original = self._entries(4)
        tampered = [b"BAD", original[1], original[2], original[3], b"extra"]
        old_root = merkle_root(original[:4])
        new_root = merkle_root(tampered)
        proof = consistency_proof(4, 5, tampered)
        # old_root was computed on the original, but proof is for tampered log.
        assert not verify_consistency(old_root, 4, new_root, 5, proof)

    def test_verify_consistency_truncation(self) -> None:
        """A truncated log (new_size < old_size) must fail."""
        entries = self._entries(8)
        old_root = merkle_root(entries)
        new_root = merkle_root(entries[:4])
        # verify_consistency checks old_size > new_size → False.
        assert not verify_consistency(old_root, 8, new_root, 4, [])

    def test_verify_consistency_tampered_old_root(self) -> None:
        entries = self._entries(8)
        old_root = merkle_root(entries[:4])
        new_root = merkle_root(entries)
        proof = consistency_proof(4, 8, entries)
        bad_old = bytes(b ^ 0xFF for b in old_root)
        assert not verify_consistency(bad_old, 4, new_root, 8, proof)

    def test_verify_consistency_tampered_new_root(self) -> None:
        entries = self._entries(8)
        old_root = merkle_root(entries[:4])
        new_root = merkle_root(entries)
        proof = consistency_proof(4, 8, entries)
        bad_new = bytes(b ^ 0xFF for b in new_root)
        assert not verify_consistency(old_root, 4, bad_new, 8, proof)

    def test_verify_consistency_tampered_proof(self) -> None:
        entries = self._entries(8)
        old_root = merkle_root(entries[:4])
        new_root = merkle_root(entries)
        proof = consistency_proof(4, 8, entries)
        bad_proof = [bytes(b ^ 0xFF for b in proof[0])] + proof[1:]
        assert not verify_consistency(old_root, 4, new_root, 8, bad_proof)

    def test_verify_consistency_from_empty(self) -> None:
        entries = self._entries(5)
        new_root = merkle_root(entries)
        empty_hash = merkle_root([])
        # From empty, any append is consistent; empty proof.
        assert verify_consistency(empty_hash, 0, new_root, 5, [])

    def test_verify_consistency_power_of_two_boundaries(self) -> None:
        """Test at powers of two where the tree is perfectly balanced."""
        entries = self._entries(16)
        for old_size in [1, 2, 4, 8]:
            old_root = merkle_root(entries[:old_size])
            new_root = merkle_root(entries)
            proof = consistency_proof(old_size, 16, entries)
            assert verify_consistency(old_root, old_size, new_root, 16, proof), (
                f"failed for old_size={old_size}"
            )


# ---------------------------------------------------------------------------
# SEC-3 — _largest_power_of_two_less_than: integer math, no float precision issues
# ---------------------------------------------------------------------------


class TestLargestPowerOfTwoLessThan:
    """SEC-3: bit_length()-based impl must be exact for all sizes including n > 2^53."""

    @pytest.mark.parametrize("n,expected", [
        (2, 1),
        (3, 2),
        (4, 2),
        (5, 4),
        (1024, 512),
        (1025, 1024),
    ])
    def test_exact_boundaries(self, n: int, expected: int) -> None:
        assert _largest_power_of_two_less_than(n) == expected

    def test_large_n_beyond_float53(self) -> None:
        """n > 2**53 where math.log2 loses precision; bit_length() stays exact."""
        n = (1 << 54) + 1  # 2^54 + 1 — beyond float53 precision
        result = _largest_power_of_two_less_than(n)
        # largest power of two < (2^54 + 1) is 2^54
        assert result == 1 << 54
        assert result < n
        # Must be a power of two
        assert result > 0 and (result & (result - 1)) == 0

    def test_large_tree_uses_correct_split(self) -> None:
        """Verify merkle_root works on a large tree (>2^53 entries impractical;
        check that the function is wired in correctly via a 1025-entry tree)."""
        entries = [f"e{i}".encode() for i in range(1025)]
        root = merkle_root(entries)
        # Round-trip: all inclusion proofs valid
        for i in [0, 512, 1023, 1024]:
            proof = inclusion_proof(entries, i)
            assert verify_inclusion(entries[i], i, 1025, proof, root), f"failed at {i}"
