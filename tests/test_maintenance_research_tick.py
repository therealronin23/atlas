"""Integration seams for the opt-in research tick."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.core.orchestrator import Orchestrator
from atlas.core.self_maintenance.panorama_scout import PanoramaFinding
from atlas.core.self_maintenance.topic_expander import TopicExpansion


def test_egress_fetch_uses_checked_pinned_ip(monkeypatch) -> None:
    from atlas.core.orchestrator_parts.maintenance_facade import _egress_fetch_text

    seen: dict[str, object] = {}

    class Response:
        headers = SimpleNamespace(get_content_type=lambda: "text/html")
        def read(self, _limit: int) -> bytes: return b"official material"
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    class Opener:
        def open(self, request, *, timeout):
            seen["url"] = request.full_url
            seen["timeout"] = timeout
            return Response()

    monkeypatch.setattr(
        "atlas.security.executor._build_opener_with_pinned_ip",
        lambda pinned_ip, url, timeout_s: seen.update({"pinned_ip": pinned_ip, "build_url": url, "build_timeout": timeout_s}) or Opener(),
    )
    decision = SimpleNamespace(pinned_ip="93.184.216.34")
    assert _egress_fetch_text("https://developers.openai.com/resources/", decision=decision) == "official material"
    assert seen["pinned_ip"] == "93.184.216.34"
    assert seen["url"] == "https://developers.openai.com/resources/"


def test_egress_fetch_rejects_binary_content_before_reading(monkeypatch) -> None:
    from atlas.core.orchestrator_parts.maintenance_facade import _egress_fetch_text

    class Response:
        headers = SimpleNamespace(get_content_type=lambda: "application/octet-stream")
        def read(self, _limit: int) -> bytes: raise AssertionError("binary body must not be read")
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    class Opener:
        def open(self, _request, *, timeout): return Response()

    monkeypatch.setattr(
        "atlas.security.executor._build_opener_with_pinned_ip",
        lambda *_args: Opener(),
    )
    with pytest.raises(ValueError, match="content type"):
        _egress_fetch_text(
            "https://developers.openai.com/resources/",
            decision=SimpleNamespace(pinned_ip="93.184.216.34"),
        )


def test_research_tick_threads_seed_and_min_stars(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_RESEARCH", "1")
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "core"))
    monkeypatch.setenv("ATLAS_MCP_DISCOVERY_MIN_STARS", "7")
    (tmp_path / "core").mkdir()
    (tmp_path / "atlas").mkdir()

    class Expander:
        def __init__(self, **_kwargs) -> None: pass
        def expand_detailed(self, _seeds, *, queries_per_seed):
            assert queries_per_seed == 4
            return [TopicExpansion(seed="memoria de agentes de IA", queries=["agent memory"])]

    seen: dict[str, object] = {}
    class Scout:
        def __init__(self, **kwargs) -> None: seen.update(kwargs)
        def discover(self):
            return [PanoramaFinding(topic="agent memory", source="github", title="acme/memory", url="https://github.com/acme/memory", excerpt="x", seed=seen["topic_seeds"]["agent memory"])]

    monkeypatch.setattr("atlas.core.self_maintenance.topic_expander.TopicExpander", Expander)
    monkeypatch.setattr("atlas.core.self_maintenance.panorama_scout.PanoramaScout", Scout)
    result = Orchestrator(workspace=tmp_path / "atlas").maintenance_research_tick()
    report = Path(result["report_path"]).read_text(encoding="utf-8")
    assert result["status"] == "ran"
    assert seen["min_stars"] == 7
    assert "- seed: memoria de agentes de IA" in report


def test_research_tick_includes_curated_findings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_RESEARCH", "1")
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "core"))
    (tmp_path / "core" / "docs" / "knowledge").mkdir(parents=True)
    (tmp_path / "atlas").mkdir()
    (tmp_path / "core" / "docs" / "knowledge" / "curated_sources.yaml").write_text(
        "sources:\n  - url: https://github.com/vercel-labs/agent-skills\n    note: Vercel skills\n",
        encoding="utf-8",
    )
    class Expander:
        def __init__(self, **_kwargs) -> None: pass
        def expand_detailed(self, _seeds, *, queries_per_seed):
            return [TopicExpansion(seed="x", queries=["x"])]
    class Scout:
        def __init__(self, **_kwargs) -> None: pass
        def discover(self): return []
    monkeypatch.setattr("atlas.core.self_maintenance.topic_expander.TopicExpander", Expander)
    monkeypatch.setattr("atlas.core.self_maintenance.panorama_scout.PanoramaScout", Scout)
    result = Orchestrator(workspace=tmp_path / "atlas").maintenance_research_tick()
    assert "vercel-labs/agent-skills" in Path(result["report_path"]).read_text(encoding="utf-8")


def test_research_tick_fetches_curated_official_material_via_injected_egress(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_RESEARCH", "1")
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "core"))
    (tmp_path / "core" / "docs" / "knowledge").mkdir(parents=True)
    (tmp_path / "atlas").mkdir()
    (tmp_path / "core" / "docs" / "knowledge" / "curated_sources.yaml").write_text(
        "publishers:\n  - id: openai\n    domains: [developers.openai.com]\n"
        "sources:\n  - publisher: openai\n    kind: official_docs\n"
        "    url: https://developers.openai.com/resources/\n    note: OpenAI resources\n",
        encoding="utf-8",
    )

    class Expander:
        def __init__(self, **_kwargs) -> None: pass
        def expand_detailed(self, _seeds, *, queries_per_seed):
            return [TopicExpansion(seed="x", queries=["x"])]
    class Scout:
        def __init__(self, **_kwargs) -> None: pass
        def discover(self): return []

    monkeypatch.setattr("atlas.core.self_maintenance.topic_expander.TopicExpander", Expander)
    monkeypatch.setattr("atlas.core.self_maintenance.panorama_scout.PanoramaScout", Scout)
    monkeypatch.setattr(
        "atlas.core.orchestrator_parts.maintenance_facade._egress_fetch_text",
        lambda _url, **_kwargs: "<h1>Official material</h1>",
    )
    result = Orchestrator(workspace=tmp_path / "atlas").maintenance_research_tick()
    report = Path(result["report_path"]).read_text(encoding="utf-8")
    assert result["curated_findings_count"] == 1
    assert "[official] OpenAI resources" in report
    assert "Official material" in report


def test_research_tick_reruns_once_when_curated_manifest_changes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_RESEARCH", "1")
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "core"))
    manifest = tmp_path / "core" / "docs" / "knowledge" / "curated_sources.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("sources: []\n", encoding="utf-8")
    (tmp_path / "atlas").mkdir()

    class Expander:
        def __init__(self, **_kwargs) -> None: pass
        def expand_detailed(self, _seeds, *, queries_per_seed):
            return [TopicExpansion(seed="x", queries=["x"])]

    class Scout:
        def __init__(self, **_kwargs) -> None: pass
        def discover(self): return []

    monkeypatch.setattr("atlas.core.self_maintenance.topic_expander.TopicExpander", Expander)
    monkeypatch.setattr("atlas.core.self_maintenance.panorama_scout.PanoramaScout", Scout)
    orchestrator = Orchestrator(workspace=tmp_path / "atlas")
    assert orchestrator.maintenance_research_tick()["status"] == "ran"
    manifest.write_text("sources: []\n# changed\n", encoding="utf-8")
    assert orchestrator.maintenance_research_tick()["status"] == "ran"
    assert orchestrator.maintenance_research_tick()["status"] == "already_ran_today"


# ---------------------------------------------------------------------------
# La criba corre DENTRO del tick, no sólo en su módulo
#
# El módulo `atlas.discovery` llevaba desde el 2026-08-06 escrito y probado con
# cero callers: sus tests pasaban mientras nadie lo invocaba. Estos tests fijan
# la costura — que el tick lo llama de verdad — que es justo lo que un test de
# módulo no puede ver.
# ---------------------------------------------------------------------------


def _tick_con_hallazgos(tmp_path: Path, monkeypatch, findings: list[PanoramaFinding]):
    monkeypatch.setenv("ATLAS_RESEARCH", "1")
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "core"))
    (tmp_path / "core").mkdir()
    (tmp_path / "atlas").mkdir()

    class Expander:
        def __init__(self, **_kwargs) -> None: pass
        def expand_detailed(self, _seeds, *, queries_per_seed):
            return [TopicExpansion(seed="s", queries=["q"])]

    class Scout:
        def __init__(self, **_kwargs) -> None: pass
        def discover(self): return list(findings)

    monkeypatch.setattr("atlas.core.self_maintenance.topic_expander.TopicExpander", Expander)
    monkeypatch.setattr("atlas.core.self_maintenance.panorama_scout.PanoramaScout", Scout)
    result = Orchestrator(workspace=tmp_path / "atlas").maintenance_research_tick()
    return result, Path(result["report_path"]).read_text(encoding="utf-8")


def _repo(name: str, *, source: str = "github", **kw) -> PanoramaFinding:
    base = dict(
        metadata_known=True, license="MIT", archived=False,
        pushed_at="2026-08-01T00:00:00Z", stars=50,
    )
    if source != "github":  # otros canales no publican metadatos de repo
        base = {}
    base.update(kw)
    return PanoramaFinding(
        topic="q", source=source, title=name,
        url=f"https://github.com/{name}", excerpt="d", **base,
    )


def test_el_tick_publica_las_cifras_de_la_criba(tmp_path: Path, monkeypatch) -> None:
    """Sin esto, el filtro corre y nadie puede saber qué descartó."""
    result, _ = _tick_con_hallazgos(tmp_path, monkeypatch, [_repo("acme/bueno")])

    assert result["triage_sightings"] == 1
    assert result["triage_eligible"] == 1
    assert result["triage_rejected"] == 0


def test_el_tick_descarta_un_repo_archivado_y_lo_dice_en_el_informe(
    tmp_path: Path, monkeypatch
) -> None:
    result, report = _tick_con_hallazgos(
        tmp_path, monkeypatch, [_repo("acme/muerto", archived=True)]
    )

    assert result["triage_eligible"] == 0 and result["triage_rejected"] == 1
    assert "acme/muerto" in report and "archivado" in report


def test_el_tick_corrobora_entre_canales_independientes(
    tmp_path: Path, monkeypatch
) -> None:
    """El caso que justifica todo: GitHub y un Show HN sobre el mismo repo."""
    result, report = _tick_con_hallazgos(
        tmp_path, monkeypatch,
        [_repo("acme/tool"), _repo("acme/tool", source="hackernews")],
    )

    assert result["triage_corroborated"] == 1
    assert result["corroborated_names"] == ["acme/tool"]
    assert "Corroborados" in report


def test_un_paper_no_se_descarta_por_no_tener_licencia(
    tmp_path: Path, monkeypatch
) -> None:
    """Regresión: pasar un arXiv por la criba de repos lo rechazaría por
    `sin_licencia`, que es una afirmación falsa sobre un paper."""
    paper = PanoramaFinding(
        topic="q", source="arxiv", title="Un paper",
        url="http://arxiv.org/abs/2508.01234v1", excerpt="resumen",
    )

    result, _ = _tick_con_hallazgos(tmp_path, monkeypatch, [paper])

    assert result["triage_rejected"] == 0
    assert result["triage_no_repo"] == 1


def test_la_criba_no_tira_hallazgos_del_informe(tmp_path: Path, monkeypatch) -> None:
    """Cribar ordena la lectura; NO recorta la evidencia. Los 122 hallazgos
    crudos siguen enteros debajo de la sección de criba."""
    findings = [_repo("acme/bueno"), _repo("acme/muerto", archived=True)]

    result, report = _tick_con_hallazgos(tmp_path, monkeypatch, findings)

    assert result["findings_count"] == 2
    assert "## Hallazgos (2)" in report
    assert report.count("### [github]") == 2
