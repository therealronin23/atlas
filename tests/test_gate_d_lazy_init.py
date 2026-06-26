"""G0.0 regression — Gate-D lazy init y fail-closed.

Criterio de done: self-audit (y cualquier comando de introspección) arranca
con Gate-D roto a propósito. El fallo es ruidoso en el punto de uso,
no un crash opaco en el constructor.
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


def make_orchestrator(**env):
    """Construye un Orchestrator con env parcheado."""
    with patch.dict(os.environ, env, clear=False):
        from atlas.core.orchestrator import Orchestrator
        return Orchestrator()


def test_orchestrator_constructs_without_gate_d_env():
    """Sin ATLAS_PIPELINE_GATE_D, el constructor no toca Kuzu."""
    orch = make_orchestrator(ATLAS_PIPELINE_GATE_D="0")
    assert not orch._gate_d_enabled
    assert not orch._gate_d_requested


def test_orchestrator_constructs_even_when_gate_d_requested():
    """Con ATLAS_PIPELINE_GATE_D=1, el constructor termina sin inicializar Gate-D."""
    orch = make_orchestrator(ATLAS_PIPELINE_GATE_D="1")
    assert not orch._gate_d_enabled   # todavía no inicializado
    assert orch._gate_d_requested     # pero marcado para inicializar en primer uso


def test_orchestrator_constructs_with_gate_d_requested_and_kuzu_absent(tmp_path):
    """G0.0 done-criterion: el constructor no falla aunque Gate-D esté pedido.
    La inicialización real ocurre en primer uso, no aquí."""
    with patch.dict(os.environ, {"ATLAS_PIPELINE_GATE_D": "1"}, clear=False):
        from atlas.core.orchestrator import Orchestrator
        orch = Orchestrator()
        # Constructor terminó — Gate-D pendiente, no inicializado
        assert not orch._gate_d_enabled
        assert orch._gate_d_requested


def test_ensure_gate_d_raises_kuzu_init_error_on_broken_db(tmp_path):
    """_ensure_gate_d() falla ruidoso con KuzuInitError cuando Kuzu está roto."""
    from atlas.core.orchestrator import Orchestrator, KuzuInitError

    orch = make_orchestrator(ATLAS_PIPELINE_GATE_D="1", ATLAS_MEMORY_VECTOR="1")
    orch._gate_d_requested = True

    # Inyectar un workspace con DB corrupta
    kuzu_dir = tmp_path / "memory" / "kuzu"
    kuzu_dir.mkdir(parents=True)
    (kuzu_dir / "atlas.kuzu").write_text("corrupto")
    orch._workspace = tmp_path

    with pytest.raises(KuzuInitError, match="rm -rf"):
        orch._ensure_gate_d()


def test_ensure_gate_d_noop_when_not_requested():
    """_ensure_gate_d() no hace nada si ATLAS_PIPELINE_GATE_D no está."""
    orch = make_orchestrator(ATLAS_PIPELINE_GATE_D="0")
    # No debe lanzar aunque Kuzu no exista
    orch._ensure_gate_d()
    assert not orch._gate_d_enabled


def test_ensure_gate_d_idempotent():
    """_ensure_gate_d() es idempotente si ya está habilitado."""
    orch = make_orchestrator(ATLAS_PIPELINE_GATE_D="0")
    orch._gate_d_enabled = True   # simular ya inicializado
    orch._gate_d_requested = True
    # No debe rellamar enable_gate_d_pipeline
    with patch.object(orch, "enable_gate_d_pipeline") as mock_init:
        orch._ensure_gate_d()
        mock_init.assert_not_called()
