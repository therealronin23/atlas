"""Test de escala del TransparencyLog (OSM-006).

Demuestra que el log RFC 9162 escala a N entradas con inclusion proof y
consistency proof correctas.  No toca código de producción.
"""
from __future__ import annotations

import time

from atlas.security.authorization import HMACSigner
from atlas.transparency.log import TransparencyLog
from atlas.transparency.merkle_tree import verify_inclusion, verify_consistency


def test_transparency_log_scale() -> None:
    """OSM-006: 10k entradas en CI; el diseño escala a 100k+."""
    N = 10_000  # OSM-006: 10k en CI; el diseño escala a 100k+

    signer = HMACSigner(b"test-secret-key")
    log = TransparencyLog(signer=signer)

    t_start = time.perf_counter()

    for i in range(N):
        log.append(f"entry-{i}".encode())

    elapsed = time.perf_counter() - t_start
    print(f"\nOSM-006: appended {N} entries in {elapsed*1000:.1f}ms")

    # tree_size debe coincidir exactamente
    assert log.tree_size == N

    # Inclusion proof para una hoja del medio
    mid = N // 2
    sth = log.signed_tree_head()
    proof = log.prove_inclusion(mid)
    entry_bytes = f"entry-{mid}".encode()
    assert verify_inclusion(entry_bytes, mid, N, proof, sth.root_hash), (
        f"inclusion proof falló para índice {mid}"
    )

    # Consistency proof: desde old_size hasta N (el árbol completo).
    # prove_consistency(old_size) prueba que el árbol actual (tamaño N) es
    # una extensión append-only del árbol de tamaño old_size.
    old_size = N // 4

    # Construimos un log auxiliar hasta old_size para obtener su root.
    log_old = TransparencyLog(signer=signer)
    for i in range(old_size):
        log_old.append(f"entry-{i}".encode())
    old_root = log_old.signed_tree_head().root_hash

    # new_root es el root del log principal (N entradas) ya computado
    new_root = sth.root_hash

    consistency_proof = log.prove_consistency(old_size)
    assert verify_consistency(
        old_root, old_size, new_root, N, consistency_proof
    ), f"consistency proof falló entre tamaños {old_size}→{N}"

    t_total = time.perf_counter() - t_start
    print(f"OSM-006: total (append + proofs) {t_total*1000:.1f}ms")
