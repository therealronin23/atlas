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
    # InferenceHub auto-carga .env (que en el despliegue real trae estos
    # flags a 1) en os.environ a mitad de suite — sin delenv, el orden de
    # los tests decide si el flag está puesto (verificado 2026-07-09).
    monkeypatch.delenv("ATLAS_RESEARCH", raising=False)
    monkeypatch.delenv("ATLAS_PROVIDER_SMOKE", raising=False)
    monkeypatch.delenv("ATLAS_KNOWLEDGE_INGEST", raising=False)
    monkeypatch.delenv("ATLAS_MEMORY_DB", raising=False)
    monkeypatch.delenv("ATLAS_PROJECT_GRAPH", raising=False)
    # La marca anti-recursión viene puesta cuando ESTA suite corre dentro del
    # propio lazo (ToolCoder/ValidationRunner la inyectan); estos tests
    # ejercitan los ticks con fakes y deben ver el comportamiento normal.
    monkeypatch.delenv("ATLAS_NESTED_TEST_RUN", raising=False)
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

    def test_nested_run_guard_beats_everything(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Incidente 2026-07-09 (producción): la suite que el lazo corre en su
        worktree hereda ATLAS_SELF_BUILD=1 del daemon; un test que arrancaba
        el scheduler real disparaba OTRO run_item real → cascada de worktrees
        + pytest anidados. La marca ATLAS_NESTED_TEST_RUN gana a todo."""
        monkeypatch.setenv("ATLAS_SELF_BUILD", "1")
        monkeypatch.setenv("ATLAS_NESTED_TEST_RUN", "1")
        assert orch.maintenance_self_build_tick() == {"status": "nested_run_guard"}
        monkeypatch.setenv("ATLAS_RESEARCH", "1")
        assert orch.maintenance_research_tick() == {"status": "nested_run_guard"}
        monkeypatch.setenv("ATLAS_PROVIDER_SMOKE", "1")
        assert orch.maintenance_provider_smoke_tick() == {"status": "nested_run_guard"}
        monkeypatch.setenv("ATLAS_KNOWLEDGE_INGEST", "1")
        assert orch.maintenance_knowledge_ingest_tick() == {"status": "nested_run_guard"}
        monkeypatch.setenv("ATLAS_PROJECT_GRAPH", "1")
        assert orch.maintenance_project_graph_tick() == {"status": "nested_run_guard"}

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


class TestProviderSmokeTick:
    """Fase 5 (2026-07-09): la cadena de proveedores se pudre en silencio
    (modelos decomisionados/renombrados upstream) sin nada que la camine
    proactivamente. CERO red real: probe_provider se monkeypatchea."""

    def test_disabled_without_env_flag(self, orch: Orchestrator) -> None:
        assert orch.maintenance_provider_smoke_tick() == {"status": "disabled"}

    def test_runs_and_classifies_providers(
        self,
        orch: Orchestrator,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ATLAS_PROVIDER_SMOKE", "1")

        from atlas.core.inference_hub import DEFAULT_PROVIDERS

        class _FakeHub:
            def probe_provider(self, provider: Any, request: Any) -> Any:
                class _Resp:
                    pass
                resp = _Resp()
                resp.success = provider is DEFAULT_PROVIDERS[0]
                resp.error = None if resp.success else "model_decommissioned"
                resp.latency_ms = 5
                resp.mode = "live"
                return resp

        monkeypatch.setattr(orch, "_inference_hub", _FakeHub())

        result = orch.maintenance_provider_smoke_tick()

        assert result["status"] == "ran"
        assert DEFAULT_PROVIDERS[0].name in result["ok"]
        assert len(result["dead"]) == len(DEFAULT_PROVIDERS) - 1

    def test_second_call_same_day_is_a_noop(
        self,
        orch: Orchestrator,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ATLAS_PROVIDER_SMOKE", "1")

        class _FakeHub:
            def probe_provider(self, provider: Any, request: Any) -> Any:
                class _Resp:
                    success = False
                    error = "sin key"
                    latency_ms = 0
                    mode = "auto-skip"
                return _Resp()

        monkeypatch.setattr(orch, "_inference_hub", _FakeHub())

        first = orch.maintenance_provider_smoke_tick()
        second = orch.maintenance_provider_smoke_tick()

        assert first["status"] == "ran"
        assert second == {"status": "already_ran_today"}


class TestKnowledgeIngestTick:
    """Cierre investigación→acción (2026-07-09): los informes de research
    morían en docs/inbox/. El tick los triage-a (regla determinista, sin LLM)
    a docs/knowledge como 'propuesto' y los ingiere al sustrato de memoria.
    CERO LLM/red real: todo es determinista por diseño."""

    @staticmethod
    def _seed_repo(repo: Path) -> None:
        # Scripts reales del repo (el tick los carga por importlib): triage +
        # su dependencia docs_index_audit.
        import shutil

        real_repo = Path(__file__).resolve().parent.parent
        (repo / "scripts").mkdir(parents=True, exist_ok=True)
        for name in ("docs_triage.py", "docs_index_audit.py"):
            shutil.copy(real_repo / "scripts" / name, repo / "scripts" / name)
        inbox = repo / "docs" / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / "research_2026-07-09.md").write_text(
            "# Informe de investigación 2026-07-09\n\n"
            "## Hallazgos\n\n- repo estrella: org/ejemplo — patrón de memoria episódica\n",
            encoding="utf-8",
        )
        (repo / "docs" / "INDEX.yaml").write_text("entries: []\n", encoding="utf-8")

    def test_disabled_without_env_flag(self, orch: Orchestrator) -> None:
        assert orch.maintenance_knowledge_ingest_tick() == {"status": "disabled"}

    def test_triages_and_ingests_research_report(
        self, orch: Orchestrator, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = tmp_path / "repo"
        self._seed_repo(repo)
        monkeypatch.setenv("ATLAS_KNOWLEDGE_INGEST", "1")
        monkeypatch.setenv("ATLAS_MEMORY_DB", str(tmp_path / "memoria" / "memory.db"))
        (tmp_path / "memoria").mkdir()

        result = orch.maintenance_knowledge_ingest_tick()

        assert result["status"] == "ran"
        # Triage: movido del inbox a docs/knowledge con alta 'propuesto'.
        assert result["triaged"] == 1
        moved = repo / "docs" / "knowledge" / "research_2026-07-09.md"
        assert moved.is_file()
        assert not (repo / "docs" / "inbox" / "research_2026-07-09.md").exists()
        import yaml

        idx = yaml.safe_load((repo / "docs" / "INDEX.yaml").read_text(encoding="utf-8"))
        entry = next(e for e in idx["entries"] if "research_2026-07-09" in e["path"])
        assert entry["status"] == "propuesto"
        # Ingesta: el informe entró al sustrato y el recall lo devuelve.
        assert result["research_records"] >= 1
        from atlas.mcp.memory_server import build_gated_index
        from atlas.mcp.memory_trunk import MemoryTrunk

        index = build_gated_index(tmp_path / "memoria" / "memory.db")
        try:
            hits = MemoryTrunk(index).recall("memoria episódica org/ejemplo", k=5)
        finally:
            index.close()
        assert any("org/ejemplo" in h.text for h in hits)

    def test_second_call_same_day_is_a_noop_and_unchanged_files_skip(
        self, orch: Orchestrator, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = tmp_path / "repo"
        self._seed_repo(repo)
        monkeypatch.setenv("ATLAS_KNOWLEDGE_INGEST", "1")
        monkeypatch.setenv("ATLAS_MEMORY_DB", str(tmp_path / "memory.db"))

        first = orch.maintenance_knowledge_ingest_tick()
        assert first["status"] == "ran"
        assert orch.maintenance_knowledge_ingest_tick() == {"status": "already_ran_today"}

        # Al día siguiente (estado con fecha vieja), los ficheros sin cambios
        # NO se re-embeben: la pasada diaria es ~gratis en reposo.
        import json

        state_path = repo / "workspace" / "knowledge" / "ingest_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["last_run_date"] = "2000-01-01"
        state_path.write_text(json.dumps(state), encoding="utf-8")

        rerun = orch.maintenance_knowledge_ingest_tick()
        assert rerun["status"] == "ran"
        assert rerun["research_records"] == 0
        assert rerun["repo_records"] == 0


class TestProjectGraphTick:
    """Fase 3bis: el grafo vivo se quedaba atrás en cuanto había commits
    nuevos (19 vs 20 importers vs grep). Gating por HEAD, no por reloj: cero
    trabajo en reposo, regeneración al primer poll tras un commit. CERO Kuzu
    real: build_project_graph se monkeypatchea."""

    @staticmethod
    def _git_repo(repo: Path) -> None:
        import subprocess

        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / "x.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
            cwd=repo, check=True,
        )

    def test_disabled_without_env_flag(self, orch: Orchestrator) -> None:
        assert orch.maintenance_project_graph_tick() == {"status": "disabled"}

    def test_no_git_is_a_clean_noop(
        self, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_PROJECT_GRAPH", "1")
        # tmp repo sin .git (y GIT_DIR aislado para no resolver el repo real
        # por el árbol de directorios padre).
        monkeypatch.setenv("GIT_DIR", str(Path("/nonexistent")))
        assert orch.maintenance_project_graph_tick() == {"status": "no_git"}

    def test_regenerates_on_new_head_and_skips_when_unchanged(
        self, orch: Orchestrator, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_PROJECT_GRAPH", "1")
        db = tmp_path / "graphdb" / "project_graph.kuzu"
        monkeypatch.setenv("ATLAS_PROJECT_GRAPH_DB", str(db))
        repo = tmp_path / "repo"
        self._git_repo(repo)
        cache = repo / "graphify-out" / "cache" / "ast" / "v0.9.11"
        cache.mkdir(parents=True)

        builds: list[Path] = []
        callgraph_loads: list[tuple[Path, Path, dict[str, Any]]] = []

        def _fake_build(root: Path, db_path: Path, **kw: Any) -> dict[str, Any]:
            # El tick construye sobre la COPIA .rebuild y hace swap después.
            assert db_path.name.endswith(".rebuild")
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_path.write_text("kuzu-fake", encoding="utf-8")
            builds.append(root)
            return {"commits": ["abc"]}

        monkeypatch.setattr(
            "atlas.memory.project_graph.build_project_graph", _fake_build,
        )

        def _fake_callgraph(
            cache_dir: Path, db_path: Path, **kwargs: Any
        ) -> dict[str, Any]:
            callgraph_loads.append((cache_dir, db_path, kwargs))
            return {"files": 266, "symbols": 1200, "calls": 700}

        monkeypatch.setattr(
            "atlas.memory.callgraph_to_kuzu.load_callgraph_into_kuzu",
            _fake_callgraph,
        )

        first = orch.maintenance_project_graph_tick()
        assert first["status"] == "ran"
        assert builds == [repo.resolve()]
        assert first["metrics"]["callgraph"]["symbols"] == 1200
        assert callgraph_loads == [
            (
                repo / "graphify-out" / "cache" / "ast",
                db.with_name(db.name + ".rebuild"),
                {
                    "source_prefix": "src/atlas",
                    "replace": True,
                    "strict": True,
                },
            )
        ]
        # Swap hecho: la BD servida existe y la copia .rebuild ya no.
        assert db.read_text(encoding="utf-8") == "kuzu-fake"
        assert not db.with_name(db.name + ".rebuild").exists()

        # Mismo HEAD → ni toca Kuzu.
        second = orch.maintenance_project_graph_tick()
        assert second["status"] == "up_to_date"
        assert len(builds) == 1

        # Commit nuevo → regenera.
        import subprocess

        (repo / "y.txt").write_text("y", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "dos"],
            cwd=repo, check=True,
        )
        third = orch.maintenance_project_graph_tick()
        assert third["status"] == "ran"
        assert len(builds) == 2
        assert len(callgraph_loads) == 2

    def test_callgraph_errors_abort_without_swapping_or_advancing_state(
        self, orch: Orchestrator, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_PROJECT_GRAPH", "1")
        db = tmp_path / "graphdb" / "project_graph.kuzu"
        monkeypatch.setenv("ATLAS_PROJECT_GRAPH_DB", str(db))
        repo = tmp_path / "repo"
        self._git_repo(repo)
        (repo / "graphify-out" / "cache" / "ast" / "v0.9.11").mkdir(
            parents=True
        )

        def _fake_build(root: Path, db_path: Path, **kw: Any) -> dict[str, Any]:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_path.write_text("rebuild-only", encoding="utf-8")
            return {"commits": ["abc"]}

        def _broken_callgraph(*args: Any, **kwargs: Any) -> dict[str, Any]:
            raise ValueError("broken Graphify cache")

        monkeypatch.setattr(
            "atlas.memory.project_graph.build_project_graph", _fake_build
        )
        monkeypatch.setattr(
            "atlas.memory.callgraph_to_kuzu.load_callgraph_into_kuzu",
            _broken_callgraph,
        )

        with pytest.raises(ValueError, match="broken Graphify cache"):
            orch.maintenance_project_graph_tick()

        assert not db.exists()
        assert not (
            repo / "workspace" / "knowledge" / "project_graph_state.json"
        ).exists()

    def test_zero_symbol_callgraph_is_not_a_successful_regeneration(
        self, orch: Orchestrator, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_PROJECT_GRAPH", "1")
        db = tmp_path / "graphdb" / "project_graph.kuzu"
        monkeypatch.setenv("ATLAS_PROJECT_GRAPH_DB", str(db))
        repo = tmp_path / "repo"
        self._git_repo(repo)
        (repo / "graphify-out" / "cache" / "ast" / "v0.9.11").mkdir(
            parents=True
        )

        def _fake_build(root: Path, db_path: Path, **kw: Any) -> dict[str, Any]:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_path.write_text("rebuild-only", encoding="utf-8")
            return {"commits": ["abc"]}

        monkeypatch.setattr(
            "atlas.memory.project_graph.build_project_graph", _fake_build
        )
        monkeypatch.setattr(
            "atlas.memory.callgraph_to_kuzu.load_callgraph_into_kuzu",
            lambda *args, **kwargs: {"files": 0, "symbols": 0, "calls": 0},
        )

        with pytest.raises(RuntimeError, match="zero symbols"):
            orch.maintenance_project_graph_tick()

        assert not db.exists()
