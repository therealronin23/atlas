"""
Tests para IncrementalCoder — descomposición de features multi-pieza en
incrementos de una pieza verificados uno a uno.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from atlas.core.atlas_coder import AtlasCoder, CoderResult
from atlas.core.incremental_coder import Increment, IncrementalCoder


def _fake_coder(outcomes: list[bool]) -> MagicMock:
    """AtlasCoder falso cuyo .code() devuelve success según *outcomes* en orden."""
    coder = MagicMock(spec=AtlasCoder)
    results = [
        CoderResult(success=ok, iterations=1, files_changed=[], test_output="")
        for ok in outcomes
    ]
    coder.code.side_effect = results
    return coder


def _inc(n: int) -> Increment:
    return Increment(task=f"pieza {n}", context_files=["foo.py"], test_cmd=["true"])


def test_all_increments_pass():
    coder = _fake_coder([True, True, True])
    runner = IncrementalCoder(coder)
    result = runner.run([_inc(1), _inc(2), _inc(3)])

    assert result.success is True
    assert result.completed == 3
    assert result.total == 3
    assert result.failed_increment is None
    assert coder.code.call_count == 3


def test_sequence_cut_at_first_failure():
    """El incremento 2 falla → el 3 NO se intenta; se reporta qué se completó."""
    coder = _fake_coder([True, False, True])
    runner = IncrementalCoder(coder)
    result = runner.run([_inc(1), _inc(2), _inc(3)])

    assert result.success is False
    assert result.completed == 1
    assert result.total == 3
    assert result.failed_increment == 1
    assert coder.code.call_count == 2  # el tercero nunca se lanzó


def test_sandbox_enabled_by_default():
    coder = _fake_coder([True])
    runner = IncrementalCoder(coder)
    runner.run([_inc(1)])

    _, kwargs = coder.code.call_args
    assert kwargs["sandbox"] is True


def test_coder_kwargs_forwarded():
    """edit_format y demás kwargs llegan a cada AtlasCoder.code()."""
    coder = _fake_coder([True])
    runner = IncrementalCoder(coder)
    runner.run([_inc(1)], edit_format="apply_patch", use_apply_model=True)

    _, kwargs = coder.code.call_args
    assert kwargs["edit_format"] == "apply_patch"
    assert kwargs["use_apply_model"] is True


def test_empty_increment_list_is_success():
    coder = _fake_coder([])
    runner = IncrementalCoder(coder)
    result = runner.run([])

    assert result.success is True
    assert result.completed == 0
    assert result.total == 0


def test_suspicious_no_op_success_cuts_sequence():
    """success=True + files_changed=[] se trata como fallo — no avanza sobre
    una pieza que en realidad no se implementó (lección del lote A-D)."""
    coder = MagicMock(spec=AtlasCoder)
    coder.code.side_effect = [
        CoderResult(success=True, iterations=1, files_changed=[], test_output="", suspicious_no_op=True),
        CoderResult(success=True, iterations=1, files_changed=[], test_output=""),  # nunca se lanza
    ]
    runner = IncrementalCoder(coder)
    result = runner.run([_inc(1), _inc(2)])

    assert result.success is False
    assert result.completed == 0
    assert result.failed_increment == 0
    assert coder.code.call_count == 1  # el 2º incremento nunca se intentó
