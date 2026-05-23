"""
Tests del pipeline Gate D integrado en Orchestrator (cableo end-to-end).
Verifica:
  - opt-in (off por defecto, on via enable_gate_d_pipeline o env)
  - Ghost lookup -> hit corto-circuita ejecucion
  - Hybrid classify: rule-based si confidence alta, SLM si baja
  - Cada paso aparece en TimeTravel
  - Tras execucion, el resultado se cachea en GhostReplay
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.contracts import RoutingLevel, TaskStatus
from atlas.core.orchestrator import Orchestrator


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.delenv("ATLAS_PIPELINE_GATE_D", raising=False)
    return Orchestrator(workspace=tmp_path / "atlas")


# ===========================================================================
# Opt-in / default
# ===========================================================================


class TestOptIn:

    def test_default_pipeline_d_off(self, orch: Orchestrator) -> None:
        assert orch.gate_d_pipeline_enabled is False
        # Las propiedades de piezas opt-in son None por defecto
        assert orch.distiller is None
        assert orch.ghost_replay is None
        assert orch.slm_classifier is None
        assert orch.timetravel is None

    def test_pii_surrogate_always_available(self, orch: Orchestrator) -> None:
        # PIISurrogate es ligero y siempre construible — disponible incluso off
        assert orch.pii_surrogate is not None

    def test_enable_pipeline_idempotent(self, orch: Orchestrator) -> None:
        orch.enable_gate_d_pipeline()
        first_tt = orch.timetravel
        orch.enable_gate_d_pipeline()
        assert orch.timetravel is first_tt

    def test_enable_pipeline_populates_pieces(self, orch: Orchestrator) -> None:
        orch.enable_gate_d_pipeline()
        assert orch.gate_d_pipeline_enabled is True
        assert orch.distiller is not None
        assert orch.ghost_replay is not None
        assert orch.slm_classifier is not None
        assert orch.timetravel is not None

    def test_env_var_activates_on_init(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
        monkeypatch.setenv("ATLAS_PIPELINE_GATE_D", "1")
        o = Orchestrator(workspace=tmp_path / "atlas")
        assert o.gate_d_pipeline_enabled is True


# ===========================================================================
# Pipeline activo: ghost hit corta el flujo
# ===========================================================================


class TestGhostHitShortCircuit:

    def test_ghost_hit_skips_classification(self, orch: Orchestrator) -> None:
        orch.enable_gate_d_pipeline()
        # Pre-cargar entrada en cache. Task.sensitivity por defecto = "low".
        assert orch.ghost_replay is not None
        orch.ghost_replay.record(
            "lista los archivos del workspace",
            "low",
            "pipeline-d-v1",
            {
                "route":     "deterministic_tool",
                "tool_name": "fs.list_dir",
                "payload":   {"items": ["cached.txt"]},
            },
        )
        task = orch.handle_intent("lista los archivos del workspace")
        assert task.status == TaskStatus.DONE
        assert task.tool_name in ("fs.list_dir", "ghost.cache")
        # El payload original debe estar accesible (el resultado entero o solo
        # el .payload, segun como lo hayamos guardado).
        if task.result:
            # algun valor cacheado debe verse
            assert (
                "cached.txt" in str(task.result)
                or task.result.get("cached") is True
            )


# ===========================================================================
# Pipeline activo: ghost miss -> ejecuta y cachea
# ===========================================================================


class TestGhostMissThenRecord:

    def test_miss_executes_and_caches(self, orch: Orchestrator) -> None:
        orch.enable_gate_d_pipeline()
        assert orch.ghost_replay is not None

        task = orch.handle_intent("lista los archivos")
        assert task.status == TaskStatus.DONE

        # Segunda invocacion: ahora deberia ser ghost hit
        hit = orch.ghost_replay.lookup(
            "lista los archivos", "low", "pipeline-d-v1"
        )
        assert hit is not None


# ===========================================================================
# Pipeline activo: TimeTravel registra los pasos
# ===========================================================================


class TestTimeTravelSnapshots:

    def test_timetravel_records_each_step(self, orch: Orchestrator) -> None:
        orch.enable_gate_d_pipeline()
        task = orch.handle_intent("estado de atlas")
        assert orch.timetravel is not None
        history = orch.timetravel.list_history(task.id)
        labels = [h.label for h in history]
        # Debe haber al menos: received + classified + done
        assert "received" in labels
        assert "classified" in labels
        assert "done" in labels

    def test_timetravel_chain_verifies(self, orch: Orchestrator) -> None:
        orch.enable_gate_d_pipeline()
        task = orch.handle_intent("git status")
        assert orch.timetravel is not None
        ok, _ = orch.timetravel.verify_chain(task.id)
        assert ok


# ===========================================================================
# Pipeline activo: routing por governance
# ===========================================================================


class TestGovernanceStillBlocks:

    def test_block_intent_blocked(self, orch: Orchestrator) -> None:
        orch.enable_gate_d_pipeline()
        task = orch.handle_intent("ejecuta sudo rm -rf /")
        assert task.status == TaskStatus.BLOCKED


# ===========================================================================
# Backward compat: pipeline OFF -> comportamiento clasico
# ===========================================================================


class TestBackwardCompatibility:

    def test_off_no_ghost_record(self, orch: Orchestrator) -> None:
        # Pipeline desactivado -> ghost_replay sigue None
        task = orch.handle_intent("lista los archivos")
        assert task.status == TaskStatus.DONE
        assert orch.ghost_replay is None

    def test_off_no_timetravel(self, orch: Orchestrator) -> None:
        orch.handle_intent("git status")
        assert orch.timetravel is None


# ===========================================================================
# Hybrid classify path
# ===========================================================================


class TestHybridClassify:

    def test_high_confidence_rule_wins(self, orch: Orchestrator) -> None:
        # rule-based matchea claramente "git status" con confidence 1.0:
        # no debe consultar SLM
        orch.enable_gate_d_pipeline()
        task = orch.handle_intent("git status")
        assert task.route == RoutingLevel.DETERMINISTIC_TOOL

    def test_pipeline_d_enabled_log_in_merkle(self, orch: Orchestrator) -> None:
        orch.enable_gate_d_pipeline()
        recent = orch._merkle.tail(20)
        actions = [r.action for r in recent]
        assert "pipeline.gate_d_enabled" in actions
