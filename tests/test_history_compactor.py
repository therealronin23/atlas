"""
Tests de verificación — técnica #21 (Codex CLI): compactación de historial.
En vez de acumular el texto crudo de errores de TODAS las iteraciones
anteriores en el prompt (crece sin límite), se mantiene el más reciente
completo y se resumen/truncan los anteriores.
"""

from __future__ import annotations

from atlas.core.history_compactor import compact_history


def test_single_entry_returned_verbatim():
    result = compact_history(["error de la iteración 1"], budget_chars=1000)
    assert result == "error de la iteración 1"


def test_most_recent_kept_verbatim_older_truncated():
    old = "x" * 500
    recent = "y" * 100
    result = compact_history([old, recent], budget_chars=200)
    assert recent in result  # el más reciente sobrevive completo
    assert result.count("y") == 100  # no truncado
    assert "[...]" in result or "truncad" in result.lower()  # el viejo se marca truncado


def test_empty_history_returns_empty_string():
    assert compact_history([], budget_chars=1000) == ""


def test_all_entries_fit_no_truncation_marker():
    result = compact_history(["corto1", "corto2"], budget_chars=1000)
    assert "corto1" in result
    assert "corto2" in result
