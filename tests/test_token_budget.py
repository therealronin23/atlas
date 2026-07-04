"""
Tests de verificación — técnica #5 (Priompt, Cursor): presupuesto de tokens
con prioridad por bloque. Recorte binario: si excede el presupuesto, se
descartan los bloques de MENOR prioridad primero hasta caber.
"""

from __future__ import annotations

from atlas.core.token_budget import Block, fit_to_budget


def test_all_blocks_fit_returns_everything():
    blocks = [Block(text="a" * 10, priority=1), Block(text="b" * 10, priority=2)]
    result = fit_to_budget(blocks, budget_chars=100)
    assert "a" * 10 in result
    assert "b" * 10 in result


def test_drops_lowest_priority_first_when_over_budget():
    low = Block(text="LOW" * 20, priority=1)
    high = Block(text="HIGH" * 20, priority=10)
    result = fit_to_budget([low, high], budget_chars=len(high.text) + 5)
    assert "HIGH" in result
    assert "LOW" not in result


def test_empty_blocks_returns_empty_string():
    assert fit_to_budget([], budget_chars=100) == ""


def test_single_block_larger_than_budget_still_included_if_only_one():
    """Un único bloque que excede el presupuesto se incluye igual (mejor
    exceder un poco que no dar nada)."""
    block = Block(text="x" * 200, priority=1)
    result = fit_to_budget([block], budget_chars=50)
    assert "x" * 200 in result
