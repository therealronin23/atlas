"""maintenance_mcp_vetting_tick (B.3, ADR-076) — vetting continuo: stage1
completo cada ciclo (barato, read-only) + un lote de stage2 vía
select_stage2_batch/merge_stage2_report (B.2), nunca reprocesando
completed/terminal.

Esqueleto calcado de tests/test_mcp_trial_tick.py. run_stage2a_stdio/
run_stage2b_http se parchean directamente -- simular una descarga+extracción+
semgrep reales (2A) o un handshake HTTP real de terceros (2B) de principio a
fin no aporta nada a este test, que verifica el CURSOR (qué se procesa y qué
se preserva), no el resultado de cada etapa (ya cubierto por
tests/test_candidate_stage2.py)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

from atlas.core.orchestrator import Orchestrator
from atlas.core.orchestrator_parts import maintenance_facade
from atlas.mcp.candidate_stage2 import Stage2AResult, Stage2BResult


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "repo"))
    monkeypatch.delenv("ATLAS_MCP_VETTING", raising=False)
    monkeypatch.delenv("ATLAS_NESTED_TEST_RUN", raising=False)
    (tmp_path / "repo").mkdir()
    return Orchestrator(workspace=tmp_path / "atlas")


def _repo_root() -> Path:
    return Path(os.environ["ATLAS_CORE_ROOT"])


def _entry(name: str, transport: str) -> dict:
    return {
        "name": name, "sector": "uncategorized", "kind": "mcp", "mode": "connected",
        "purpose": "un server MCP normal, sin nada raro en la descripción",
        "version": "1.0.0", "transport": transport, "source": name,
        "install": f"npm:{name}" if transport == "stdio" else "",
        "package_registry": "npm" if transport == "stdio" else "",
        "package_identifier": name if transport == "stdio" else "",
        "repository_url": "", "remote_url": f"https://{name}.example" if transport == "http" else "",
        "status": "candidato", "tags": [], "provenance": {"source": "x", "fetched_at": "x"},
    }


def _write_seeded_catalog(entries: list[dict]) -> Path:
    design_dir = _repo_root() / "docs" / "design"
    design_dir.mkdir(parents=True, exist_ok=True)
    path = design_dir / "mcp_catalog_seeded.yaml"
    doc = {
        "_generated": {"by": "test", "at": "2026-07-24T00:00:00Z", "source": "x", "pages_fetched": 1},
        "sectors": {"uncategorized": {"label": "x", "entries": entries}},
    }
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _write_prior_report(rows: list[dict]) -> Path:
    path = _repo_root() / "docs" / "design" / "mcp_catalog_stage2_report.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return path


def _read_report_by_name() -> dict[str, dict]:
    path = _repo_root() / "docs" / "design" / "mcp_catalog_stage2_report.jsonl"
    if not path.is_file():
        return {}
    out = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            row = json.loads(ln)
            out[row["name"]] = row
    return out


def _stub_stage2(
    monkeypatch: pytest.MonkeyPatch,
    stdio_results: dict[str, object] | None = None,
    http_results: dict[str, object] | None = None,
) -> list[str]:
    """Reemplaza run_stage2a_stdio/run_stage2b_http por stubs deterministas.
    Devuelve la lista de nombres realmente invocados (para asserts de
    'nunca se llamó a X')."""
    stdio_results = stdio_results or {}
    http_results = http_results or {}
    called: list[str] = []

    def fake_stdio(entry: dict, *, quarantine_root, **kw):  # noqa: ANN001
        name = entry["name"]
        called.append(name)
        result = stdio_results[name]
        if isinstance(result, Exception):
            raise result
        return result

    def fake_http(entry: dict, *, fetcher, **kw):  # noqa: ANN001
        name = entry["name"]
        called.append(name)
        result = http_results[name]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("atlas.mcp.candidate_stage2.run_stage2a_stdio", fake_stdio)
    monkeypatch.setattr("atlas.mcp.candidate_stage2.run_stage2b_http", fake_http)
    return called


def test_disabled_without_env_flag(orch: Orchestrator) -> None:
    assert orch.maintenance_mcp_vetting_tick() == {"status": "disabled"}


def test_nested_run_guard_beats_enable_flag(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_MCP_VETTING", "1")
    monkeypatch.setenv("ATLAS_NESTED_TEST_RUN", "1")
    assert orch.maintenance_mcp_vetting_tick() == {"status": "nested_run_guard"}


def test_no_catalog_file_is_honest_not_silent(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_MCP_VETTING", "1")
    assert orch.maintenance_mcp_vetting_tick() == {"status": "no_catalog"}


def test_stage1_refreshes_every_cycle(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_MCP_VETTING", "1")
    _write_seeded_catalog([_entry("a", "stdio")])
    _stub_stage2(monkeypatch, stdio_results={"a": Stage2AResult(name="a", completed=True, stage_reached="static_scan", entrypoint_module="a.server")})

    result = orch.maintenance_mcp_vetting_tick()
    assert result["status"] == "ran"
    assert result["stage1"]["total"] == 1
    assert result["stage1"]["eligible"] == 1

    triage_path = _repo_root() / "docs" / "design" / "mcp_catalog_stage1_triage.jsonl"
    assert triage_path.is_file()


def test_only_processes_batch_limit_of_new_per_cycle(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_MCP_VETTING", "1")
    n = maintenance_facade._MCP_VETTING_STDIO_BATCH + 3
    entries = [_entry(f"s{i}", "stdio") for i in range(n)]
    _write_seeded_catalog(entries)
    stub_results = {
        e["name"]: Stage2AResult(name=e["name"], completed=True, stage_reached="static_scan", entrypoint_module="x")
        for e in entries
    }
    _stub_stage2(monkeypatch, stdio_results=stub_results)

    result = orch.maintenance_mcp_vetting_tick()
    assert result["stage2_stdio"] == maintenance_facade._MCP_VETTING_STDIO_BATCH

    report = _read_report_by_name()
    assert len(report) == maintenance_facade._MCP_VETTING_STDIO_BATCH


def test_skips_terminal_candidates_from_previous_cycles(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_MCP_VETTING", "1")
    _write_seeded_catalog([_entry("dead", "stdio")])
    _write_prior_report([
        {"track": "stdio", "name": "dead", "completed": False, "reason": "ambiguo: entrypoint"},
    ])
    called = _stub_stage2(monkeypatch, stdio_results={})  # si se llama, KeyError -> falla el test

    result = orch.maintenance_mcp_vetting_tick()
    assert result["status"] == "ran"
    assert "dead" not in called
    assert _read_report_by_name()["dead"]["reason"] == "ambiguo: entrypoint"  # intacto


def test_retries_retryable_candidates_from_previous_cycles(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_MCP_VETTING", "1")
    _write_seeded_catalog([_entry("flaky", "stdio")])
    _write_prior_report([
        {"track": "stdio", "name": "flaky", "completed": False, "reason": "crash: timeout"},
    ])
    _stub_stage2(monkeypatch, stdio_results={
        "flaky": Stage2AResult(name="flaky", completed=True, stage_reached="static_scan", entrypoint_module="flaky.server"),
    })

    orch.maintenance_mcp_vetting_tick()
    assert _read_report_by_name()["flaky"]["completed"] is True


def test_preserves_completed_entries_untouched_this_cycle(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_MCP_VETTING", "1")
    _write_seeded_catalog([_entry("already-done", "stdio"), _entry("brand-new", "stdio")])
    _write_prior_report([
        {"track": "stdio", "name": "already-done", "completed": True, "reason": "ok", "stage_reached": "static_scan"},
    ])
    called = _stub_stage2(monkeypatch, stdio_results={
        "brand-new": Stage2AResult(name="brand-new", completed=True, stage_reached="static_scan", entrypoint_module="x"),
    })

    orch.maintenance_mcp_vetting_tick()
    assert "already-done" not in called  # nunca se re-toca
    report = _read_report_by_name()
    assert report["already-done"]["reason"] == "ok"
    assert report["brand-new"]["completed"] is True


def test_crashing_candidate_does_not_abort_the_rest_of_the_batch(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_MCP_VETTING", "1")
    _write_seeded_catalog([_entry("crasher", "stdio"), _entry("survivor", "stdio")])
    _stub_stage2(monkeypatch, stdio_results={
        "crasher": RuntimeError("boom -- fallo no anticipado"),
        "survivor": Stage2AResult(name="survivor", completed=True, stage_reached="static_scan", entrypoint_module="x"),
    })

    result = orch.maintenance_mcp_vetting_tick()
    assert result["status"] == "ran"
    report = _read_report_by_name()
    assert report["survivor"]["completed"] is True
    assert report["crasher"]["completed"] is False
    assert "boom" in report["crasher"]["reason"]
