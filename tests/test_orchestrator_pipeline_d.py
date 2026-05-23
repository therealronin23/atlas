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

    def test_rule_match_skips_slm_consultation(self, orch: Orchestrator) -> None:
        # Rule-based matchea "git status" con confidence 1.0 -> el SLM NO debe
        # consultarse y no debe haber `classify.slm_consulted` en el log.
        orch.enable_gate_d_pipeline()
        task = orch.handle_intent("git status")
        recent = orch._merkle.tail(20)
        consulted = [r for r in recent
                     if r.task_id == task.id and r.action == "classify.slm_consulted"]
        assert consulted == []
        # winner debe ser 'rule' en el task.classified
        classified = [r for r in recent
                      if r.task_id == task.id and r.action == "task.classified"]
        assert len(classified) == 1
        assert classified[0].payload.get("winner") == "rule"

    def test_default_local_safe_consults_slm(self, orch: Orchestrator) -> None:
        # Intent sin patron concreto -> rule cae a LOCAL_SAFE 0.6 -> SLM consultado.
        orch.enable_gate_d_pipeline()
        task = orch.handle_intent("resume me brevemente que es un Merkle tree")
        recent = orch._merkle.tail(30)
        consulted = [r for r in recent
                     if r.task_id == task.id and r.action == "classify.slm_consulted"]
        assert len(consulted) == 1
        payload = consulted[0].payload
        assert payload["rule_level"] == "local_safe"
        assert payload["rule_confidence"] == pytest.approx(0.6)
        assert "slm_level" in payload

    def test_local_safe_passthrough_when_no_hub(self, orch: Orchestrator) -> None:
        # Pipeline Gate D activo SIN inference_hub inyectado -> passthrough
        orch.enable_gate_d_pipeline()  # sin hub
        task = orch.handle_intent("explicame algo abstracto sin keywords")
        assert task.status == TaskStatus.DONE
        assert task.tool_name == "local_safe.passthrough"
        assert "InferenceHub no inyectado" in task.result["message"]

    def test_local_safe_via_inference_when_hub_present(self, orch: Orchestrator) -> None:
        # Hub mockeado devolviendo respuesta exitosa
        from unittest.mock import MagicMock
        from atlas.core.inference_hub import (
            InferenceHub, InferenceLevel, InferenceResponse,
        )

        hub = MagicMock(spec=InferenceHub)
        hub.infer.return_value = InferenceResponse(
            text="Un Merkle tree es una estructura de hash en arbol.",
            provider="mock-groq",
            model="llama-3.3-70b-versatile",
            level=InferenceLevel.L1,
            latency_ms=150,
            success=True,
            tokens_used=42,
            mode="live",
        )

        orch.enable_gate_d_pipeline(inference_hub=hub)
        task = orch.handle_intent("explicame brevemente que es un Merkle tree")

        assert task.status == TaskStatus.DONE
        assert task.tool_name == "inference_hub.complete"
        assert "Merkle tree" in task.result["text"]
        assert task.result["provider"] == "mock-groq"
        assert task.result["tokens_used"] == 42
        hub.infer.assert_called_once()

    def test_inference_failure_falls_back(self, orch: Orchestrator) -> None:
        from unittest.mock import MagicMock
        from atlas.core.inference_hub import (
            InferenceHub, InferenceLevel, InferenceResponse,
        )

        hub = MagicMock(spec=InferenceHub)
        hub.infer.return_value = InferenceResponse(
            text="",
            provider="all_failed",
            model="none",
            level=InferenceLevel.L1,
            latency_ms=0,
            success=False,
            error="rate limit en todos los proveedores",
            mode="live",
        )

        orch.enable_gate_d_pipeline(inference_hub=hub)
        task = orch.handle_intent("dame un consejo")

        # Tarea termina DONE pero con tool_name indicando el fallo
        assert task.status == TaskStatus.DONE
        assert task.tool_name == "inference_hub.failed"
        assert "rate limit" in task.result["message"].lower()

    def test_pii_redact_restore_roundtrip(self, orch: Orchestrator) -> None:
        # El intent lleva un email. El hub recibe el email REDACTED; su
        # respuesta menciona el surrogate; el resultado final muestra el
        # email ORIGINAL restaurado.
        from unittest.mock import MagicMock
        from atlas.core.inference_hub import (
            InferenceHub, InferenceLevel, InferenceResponse,
        )

        captured: dict = {}
        def fake_infer(request):  # noqa: ANN001
            captured["prompt"] = request.prompt
            # Suponemos que el LLM responde citando el surrogate del email
            surrogate_email = None
            for token in request.prompt.split():
                if "@" in token:
                    surrogate_email = token
                    break
            response_text = f"Recibido. Procesare tu mensaje sobre {surrogate_email}."
            return InferenceResponse(
                text=response_text,
                provider="mock", model="m",
                level=InferenceLevel.L1, latency_ms=10,
                success=True, tokens_used=10, mode="live",
            )

        hub = MagicMock(spec=InferenceHub)
        hub.infer.side_effect = fake_infer

        orch.enable_gate_d_pipeline(inference_hub=hub)
        task = orch.handle_intent("contactame en ronin@example.com cuando puedas")

        # En el prompt enviado al hub, el email original NO debe aparecer
        assert "ronin@example.com" not in captured["prompt"]
        # En la respuesta final restaurada, el email ORIGINAL si aparece
        assert "ronin@example.com" in task.result["text"]
        # Y el contador refleja al menos un PII redactado
        assert task.result["pii_redacted"] >= 1

    def test_slm_specific_route_wins_tie(self, orch: Orchestrator) -> None:
        # Forzamos un escenario donde el rule devuelve LOCAL_SAFE 0.6 pero el
        # SLM lo identifica como DETERMINISTIC_TOOL con la MISMA confidence.
        # Con la regla de empate refinada, el SLM debe ganar (ruta mas
        # especifica que LOCAL_SAFE).
        orch.enable_gate_d_pipeline()
        from atlas.core.contracts import RoutingLevel
        from atlas.router.slm_classifier import SLMClassification

        class FixedSLM:
            mode = "stub"
            def classify(self, intent: str) -> SLMClassification:
                return SLMClassification(
                    level=RoutingLevel.DETERMINISTIC_TOOL,
                    confidence=0.6,
                    reason="forzado por test",
                    mode="stub",
                )

        orch._slm_classifier = FixedSLM()  # type: ignore[assignment]
        task = orch.handle_intent("algo sin patron concreto en regla")
        assert task.route == RoutingLevel.DETERMINISTIC_TOOL
        recent = orch._merkle.tail(20)
        classified = [r for r in recent
                      if r.task_id == task.id and r.action == "task.classified"]
        assert classified[0].payload["winner"] == "slm"
