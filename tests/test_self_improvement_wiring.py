"""Cableado v0.1 del lazo de automejora (2026-07-08).

Las cuatro piezas del roadmap "juicio real" (2026-07-04) existían con tests
propios pero NADIE las inyectaba en producción: ``ColdUpdateManager`` y
``ColdUpdateBatcher`` se construían pelados y ``PreflightGate`` tenía 0
callers (radar de saneamiento: "PARK ... wiring not enabled"). Sin esto el
lazo hacía detect→propose→verify→apply pero era incapaz de APRENDER de sus
propios fallos. Estos tests fijan el contrato de producción:

- ``Orchestrator.cold_update()`` lleva ``RootCauseClassifier`` inyectado.
- El ``ColdUpdateBatcher`` del facade lleva ``BatchPremortemGate`` y
  ``FailureLessonSink`` (LessonStore unificado en <repo>/workspace/lessons).
- ``maintenance_self_build_tick`` corre ``PreflightGate`` ANTES de gastar
  LLM, se salta el ciclo con evidencia Merkle si no pasa, y solo con
  ``ATLAS_SELF_BUILD=1``.

CERO red/LLM real: el preflight se monkeypatchea; ningún test invoca un
proveedor (regla del proyecto).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atlas.core.orchestrator import Orchestrator
from atlas.core.self_maintenance.preflight_gate import PreflightGate, PreflightResult


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    # Aislar TODO el I/O del lazo en tmp: cold updates, lesson store y backlog.
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "repo"))
    monkeypatch.setenv("ATLAS_REPO_ROOT", str(tmp_path / "repo"))
    monkeypatch.delenv("ATLAS_PIPELINE_GATE_D", raising=False)
    monkeypatch.delenv("ATLAS_SELF_BUILD", raising=False)
    (tmp_path / "repo").mkdir()
    return Orchestrator(workspace=tmp_path / "atlas")


def _passing_preflight(self: PreflightGate) -> PreflightResult:
    return PreflightResult(
        passed=True, cve_found=False, cve_findings=[], sanitation_findings={},
    )


def _failing_preflight(self: PreflightGate) -> PreflightResult:
    return PreflightResult(
        passed=False,
        cve_found=True,
        cve_findings=["demo==1.0: CVE-2026-0001 (fix: 1.1)"],
        sanitation_findings={},
    )


class TestColdUpdateJudgmentWiring:
    def test_cold_update_manager_wires_root_cause_classifier(
        self, orch: Orchestrator
    ) -> None:
        from atlas.core.self_maintenance.root_cause_classifier import (
            RootCauseClassifier,
        )

        manager = orch.cold_update()
        assert isinstance(manager._root_cause_classifier, RootCauseClassifier)

    def test_batcher_wires_premortem_and_failure_lesson_sink(
        self, orch: Orchestrator
    ) -> None:
        from atlas.core.self_maintenance.batch_premortem import BatchPremortemGate
        from atlas.core.self_maintenance.failure_lesson_sink import FailureLessonSink

        batcher = orch.maintenance_cold_update_batcher()
        assert isinstance(batcher._premortem, BatchPremortemGate)
        assert isinstance(batcher._failure_lesson_sink, FailureLessonSink)


class TestSelfBuildTickPreflight:
    def test_disabled_without_env_flag(self, orch: Orchestrator) -> None:
        assert orch.maintenance_self_build_tick() == {"status": "disabled"}

    def test_preflight_blocks_and_leaves_merkle_evidence(
        self,
        orch: Orchestrator,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ATLAS_SELF_BUILD", "1")
        monkeypatch.setattr(PreflightGate, "check", _failing_preflight)

        runner_calls: list[Any] = []
        monkeypatch.setattr(
            orch, "maintenance_self_build_runner",
            lambda: runner_calls.append("called"),
        )

        result = orch.maintenance_self_build_tick()

        assert result["status"] == "preflight_blocked"
        assert result["preflight"]["cve_found"] is True
        assert runner_calls == []  # nunca se gastó LLM
        actions = [r.action for r in orch._merkle.tail(5)]
        assert "self_build.preflight_blocked" in actions

    def test_runs_one_pending_item_when_preflight_passes(
        self,
        orch: Orchestrator,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ATLAS_SELF_BUILD", "1")
        monkeypatch.setattr(PreflightGate, "check", _passing_preflight)

        backlog_dir = tmp_path / "repo" / "docs"
        backlog_dir.mkdir(parents=True, exist_ok=True)
        (backlog_dir / "backlog.yaml").write_text(
            "items:\n"
            "  - id: demo-item\n"
            "    title: demo\n"
            "    why: probar el tick\n"
            "    targets: []\n"
            "    acceptance: n/a\n"
            "    priority: 1\n"
            "    status: pending\n",
            encoding="utf-8",
        )

        ran: list[str] = []

        class _FakeRunner:
            def run_item(self, item: Any) -> dict[str, Any]:
                ran.append(item.id)
                return {"item_id": item.id, "status": "proposed"}

        monkeypatch.setattr(
            orch, "maintenance_self_build_runner", lambda: _FakeRunner(),
        )

        result = orch.maintenance_self_build_tick()

        assert result["status"] == "ran"
        assert ran == ["demo-item"]

    def test_no_pending_items_is_a_clean_noop(
        self,
        orch: Orchestrator,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ATLAS_SELF_BUILD", "1")
        monkeypatch.setattr(PreflightGate, "check", _passing_preflight)

        backlog_dir = tmp_path / "repo" / "docs"
        backlog_dir.mkdir(parents=True, exist_ok=True)
        (backlog_dir / "backlog.yaml").write_text("items: []\n", encoding="utf-8")

        assert orch.maintenance_self_build_tick() == {"status": "no_pending"}


class TestResearchTick:
    """Fase 4 (2026-07-09): panorama_scout + topic_expander estaban completos
    y probados pero sin dueño en el scheduler (self.PARK). CERO red real: el
    fetch se monkeypatchea a un fake determinista (regla del proyecto)."""

    def test_disabled_without_env_flag(self, orch: Orchestrator) -> None:
        assert orch.maintenance_research_tick() == {"status": "disabled"}

    def test_runs_and_writes_inbox_report(
        self,
        orch: Orchestrator,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ATLAS_RESEARCH", "1")

        import json as json_mod

        class _FakeHub:
            def infer(self, request: Any) -> Any:
                class _Resp:
                    success = True
                    text = json_mod.dumps(["consulta uno", "consulta dos"])
                return _Resp()

        monkeypatch.setattr(orch, "_inference_hub", _FakeHub())

        def _fake_fetch(url: str, **kwargs: Any) -> str:
            if "github" in url:
                return json_mod.dumps({"items": [
                    {"full_name": "org/repo", "html_url": "https://github.com/org/repo",
                     "description": "hallazgo de prueba"},
                ]})
            return json_mod.dumps({"hits": []})

        monkeypatch.setattr(
            "atlas.core.orchestrator_parts.maintenance_facade._egress_fetch_text",
            _fake_fetch,
        )

        result = orch.maintenance_research_tick()

        assert result["status"] == "ran"
        assert result["findings_count"] >= 1
        report_path = Path(result["report_path"])
        assert report_path.exists()
        content = report_path.read_text(encoding="utf-8")
        assert "status: propuesto" in content
        assert "org/repo" in content

    def test_second_call_same_day_is_a_noop(
        self,
        orch: Orchestrator,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ATLAS_RESEARCH", "1")

        class _FakeHub:
            def infer(self, request: Any) -> Any:
                class _Resp:
                    success = False
                    text = ""
                return _Resp()

        monkeypatch.setattr(orch, "_inference_hub", _FakeHub())
        monkeypatch.setattr(
            "atlas.core.orchestrator_parts.maintenance_facade._egress_fetch_text",
            lambda url, **kwargs: "{}",
        )

        first = orch.maintenance_research_tick()
        second = orch.maintenance_research_tick()

        assert first["status"] == "ran"
        assert second == {"status": "already_ran_today"}
