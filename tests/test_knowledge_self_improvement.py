from __future__ import annotations

import pytest

from atlas.knowledge.artifact import KnowledgeArtifact
from atlas.knowledge.self_improvement import (
    CveDepProposer,
    SelfImprovementBridge,
    SelfRelevantFinding,
)

# --- fixtures helpers ---

_OSV_VULN = {
    "id": "GHSA-xxxx-yyyy-zzzz",
    "severity": [{"type": "CVSS_V3", "score": "7.5"}],
    "affected": [
        {
            "package": {"ecosystem": "PyPI", "name": "requests"},
            "ranges": [
                {
                    "type": "ECOSYSTEM",
                    "events": [{"introduced": "0"}, {"fixed": "2.32.0"}],
                }
            ],
        }
    ],
}

_ARTIFACT_CVE = KnowledgeArtifact(
    id="art-1",
    domain="security/cve",
    source_id="osv/GHSA-xxxx-yyyy-zzzz",
    content={"vulns": [_OSV_VULN]},
    provenance={"url": "https://api.osv.dev/v1/query"},
)


def _provider_installed(dep: str) -> str | None:
    """Mock: 'requests' instalado en 2.31.0, nada más."""
    return "2.31.0" if dep == "requests" else None


def _provider_nothing(dep: str) -> str | None:
    return None


# --- tests ---


def test_installed_dep_yields_finding():
    bridge = SelfImprovementBridge(installed_provider=_provider_installed)
    findings = bridge.scan(_ARTIFACT_CVE)
    assert len(findings) == 1
    f = findings[0]
    assert isinstance(f, SelfRelevantFinding)
    assert f.dep == "requests"
    assert f.installed_version == "2.31.0"
    assert f.vuln_id == "GHSA-xxxx-yyyy-zzzz"
    assert f.severity == "7.5"
    assert f.fixed_version == "2.32.0"


def test_uninstalled_dep_yields_no_findings():
    bridge = SelfImprovementBridge(installed_provider=_provider_nothing)
    findings = bridge.scan(_ARTIFACT_CVE)
    assert findings == []


def test_wrong_domain_yields_no_findings():
    artifact = KnowledgeArtifact(
        id="art-2",
        domain="news/tech",
        source_id="rss/foo",
        content={"vulns": [_OSV_VULN]},
        provenance={},
    )
    bridge = SelfImprovementBridge(installed_provider=_provider_installed)
    assert bridge.scan(artifact) == []


def test_content_without_vulns_key():
    artifact = KnowledgeArtifact(
        id="art-3",
        domain="security/cve",
        source_id="osv/x",
        content={"items": []},
        provenance={},
    )
    bridge = SelfImprovementBridge(installed_provider=_provider_installed)
    assert bridge.scan(artifact) == []


def test_finding_is_frozen():
    bridge = SelfImprovementBridge(installed_provider=_provider_installed)
    f = bridge.scan(_ARTIFACT_CVE)[0]
    with pytest.raises((AttributeError, TypeError)):
        f.dep = "other"  # type: ignore[misc]


# --- version-range matching tests ---


def test_installed_above_fixed_yields_no_finding():
    vuln = {
        "id": "GHSA-fast-api-old",
        "severity": [],
        "affected": [{
            "package": {"ecosystem": "PyPI", "name": "fastapi"},
            "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "0.65.2"}]}],
        }],
    }
    artifact = KnowledgeArtifact(
        id="art-fa", domain="security/cve", source_id="osv/x",
        content={"vulns": [vuln]}, provenance={},
    )
    bridge = SelfImprovementBridge(installed_provider=lambda dep: "0.136.3" if dep == "fastapi" else None)
    assert bridge.scan(artifact) == []


def test_installed_exactly_at_fixed_yields_no_finding():
    vuln = {
        "id": "GHSA-exact",
        "severity": [],
        "affected": [{
            "package": {"ecosystem": "PyPI", "name": "requests"},
            "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2.32.0"}]}],
        }],
    }
    artifact = KnowledgeArtifact(
        id="art-exact", domain="security/cve", source_id="osv/x",
        content={"vulns": [vuln]}, provenance={},
    )
    bridge = SelfImprovementBridge(installed_provider=lambda dep: "2.32.0" if dep == "requests" else None)
    assert bridge.scan(artifact) == []


def test_installed_below_introduced_yields_no_finding():
    vuln = {
        "id": "GHSA-intro",
        "severity": [],
        "affected": [{
            "package": {"ecosystem": "PyPI", "name": "requests"},
            "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "2.0.0"}, {"fixed": "3.0.0"}]}],
        }],
    }
    artifact = KnowledgeArtifact(
        id="art-intro", domain="security/cve", source_id="osv/x",
        content={"vulns": [vuln]}, provenance={},
    )
    bridge = SelfImprovementBridge(installed_provider=lambda dep: "1.5.0" if dep == "requests" else None)
    assert bridge.scan(artifact) == []


def test_git_range_ignored_yields_no_finding():
    vuln = {
        "id": "GHSA-git",
        "severity": [],
        "affected": [{
            "package": {"ecosystem": "PyPI", "name": "requests"},
            "ranges": [{"type": "GIT", "events": [{"introduced": "abc123"}, {"fixed": "def456"}]}],
        }],
    }
    artifact = KnowledgeArtifact(
        id="art-git", domain="security/cve", source_id="osv/x",
        content={"vulns": [vuln]}, provenance={},
    )
    bridge = SelfImprovementBridge(installed_provider=lambda dep: "2.31.0" if dep == "requests" else None)
    assert bridge.scan(artifact) == []


def test_empty_ranges_yields_no_finding():
    vuln = {
        "id": "GHSA-empty",
        "severity": [],
        "affected": [{
            "package": {"ecosystem": "PyPI", "name": "requests"},
            "ranges": [],
        }],
    }
    artifact = KnowledgeArtifact(
        id="art-empty", domain="security/cve", source_id="osv/x",
        content={"vulns": [vuln]}, provenance={},
    )
    bridge = SelfImprovementBridge(installed_provider=lambda dep: "2.31.0" if dep == "requests" else None)
    assert bridge.scan(artifact) == []


def test_open_range_no_fixed_yields_finding():
    vuln = {
        "id": "GHSA-open",
        "severity": [{"type": "CVSS_V3", "score": "5.0"}],
        "affected": [{
            "package": {"ecosystem": "PyPI", "name": "requests"},
            "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "2.0.0"}]}],
        }],
    }
    artifact = KnowledgeArtifact(
        id="art-open", domain="security/cve", source_id="osv/x",
        content={"vulns": [vuln]}, provenance={},
    )
    bridge = SelfImprovementBridge(installed_provider=lambda dep: "2.31.0" if dep == "requests" else None)
    findings = bridge.scan(artifact)
    assert len(findings) == 1
    assert findings[0].dep == "requests"


# --- CveDepProposer tests ---


import tempfile
from pathlib import Path
from unittest.mock import MagicMock


def _make_pyproject(content: str) -> Path:
    """Crea un pyproject.toml temporal con el contenido dado."""
    tmp = tempfile.NamedTemporaryFile(
        "w", suffix=".toml", delete=False, encoding="utf-8"
    )
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


_FINDING_VALID = SelfRelevantFinding(
    dep="requests",
    installed_version="2.31.0",
    vuln_id="GHSA-xxxx-yyyy-zzzz",
    severity="7.5",
    fixed_version="2.32.0",
)

_FINDING_NO_FIX = SelfRelevantFinding(
    dep="requests",
    installed_version="2.31.0",
    vuln_id="GHSA-open",
    severity="5.0",
    fixed_version=None,
)

_PYPROJECT_WITH_DEP = '[project]\ndependencies = [\n  "requests>=2.31.0",\n]\n'
_PYPROJECT_WITHOUT_DEP = '[project]\ndependencies = [\n  "httpx>=0.24.0",\n]\n'


def test_propose_bump_none_when_no_fixed_version():
    """AC2: devuelve None y NO llama propose cuando fixed_version is None."""
    propose = MagicMock()
    merkle = MagicMock()
    pyproject = _make_pyproject(_PYPROJECT_WITH_DEP)
    proposer = CveDepProposer(pyproject_path=pyproject, propose=propose, merkle=merkle)

    result = proposer.propose_bump(_FINDING_NO_FIX)

    assert result is None
    propose.assert_not_called()


def test_propose_bump_none_when_dep_not_in_pyproject():
    """AC3: devuelve None cuando la dep no está en pyproject."""
    propose = MagicMock()
    merkle = MagicMock()
    pyproject = _make_pyproject(_PYPROJECT_WITHOUT_DEP)
    proposer = CveDepProposer(pyproject_path=pyproject, propose=propose, merkle=merkle)

    result = proposer.propose_bump(_FINDING_VALID)

    assert result is None
    propose.assert_not_called()


def test_propose_bump_calls_propose_with_correct_args():
    """AC4: genera patch y llama propose con origin='self_audit'."""
    proposal_obj = MagicMock()
    proposal_obj.id = "prop-001"
    propose = MagicMock(return_value=proposal_obj)
    merkle = MagicMock()
    pyproject = _make_pyproject(_PYPROJECT_WITH_DEP)
    proposer = CveDepProposer(pyproject_path=pyproject, propose=propose, merkle=merkle)

    result = proposer.propose_bump(_FINDING_VALID)

    assert result is proposal_obj
    propose.assert_called_once()
    call_kwargs = propose.call_args
    # origin="self_audit" debe estar en kwargs
    assert call_kwargs.kwargs.get("origin") == "self_audit"
    # El intent menciona la dep y versiones
    intent_arg = call_kwargs.args[0]
    assert "requests" in intent_arg
    assert "2.31.0" in intent_arg
    assert "2.32.0" in intent_arg


def test_propose_bump_patch_contains_version_change():
    """AC4: el patch generado contiene el bump de versión."""
    proposal_obj = MagicMock()
    proposal_obj.id = "prop-002"
    propose = MagicMock(return_value=proposal_obj)
    merkle = MagicMock()
    pyproject = _make_pyproject(_PYPROJECT_WITH_DEP)
    proposer = CveDepProposer(pyproject_path=pyproject, propose=propose, merkle=merkle)

    proposer.propose_bump(_FINDING_VALID)

    patch_path: Path = propose.call_args.args[1]
    patch_content = patch_path.read_text(encoding="utf-8")
    assert "2.31.0" in patch_content
    assert "2.32.0" in patch_content


def test_risk_high_when_severity_above_7():
    """AC5: risk='high' cuando severity > 7.0."""
    finding = SelfRelevantFinding(
        dep="requests", installed_version="2.31.0", vuln_id="X",
        severity="9.8", fixed_version="2.32.0",
    )
    propose = MagicMock(return_value=MagicMock(id="x"))
    merkle = MagicMock()
    pyproject = _make_pyproject(_PYPROJECT_WITH_DEP)
    proposer = CveDepProposer(pyproject_path=pyproject, propose=propose, merkle=merkle)

    proposer.propose_bump(finding)

    assert propose.call_args.kwargs.get("risk") == "high"


def test_risk_medium_when_severity_below_or_equal_7():
    """AC5: risk='medium' cuando severity <= 7.0."""
    finding = SelfRelevantFinding(
        dep="requests", installed_version="2.31.0", vuln_id="X",
        severity="7.0", fixed_version="2.32.0",
    )
    propose = MagicMock(return_value=MagicMock(id="x"))
    merkle = MagicMock()
    pyproject = _make_pyproject(_PYPROJECT_WITH_DEP)
    proposer = CveDepProposer(pyproject_path=pyproject, propose=propose, merkle=merkle)

    proposer.propose_bump(finding)

    assert propose.call_args.kwargs.get("risk") == "medium"


def test_risk_medium_when_severity_none():
    """AC5: risk='medium' cuando severity es None."""
    assert CveDepProposer._risk(None) == "medium"


def test_risk_medium_when_severity_not_parseable():
    """AC5: risk='medium' cuando severity no parsea como float."""
    assert CveDepProposer._risk("CRITICAL") == "medium"


def test_merkle_log_called_with_applied_false():
    """AC6: registra en merkle con applied=False."""
    proposal_obj = MagicMock()
    proposal_obj.id = "prop-003"
    propose = MagicMock(return_value=proposal_obj)
    merkle = MagicMock()
    pyproject = _make_pyproject(_PYPROJECT_WITH_DEP)
    proposer = CveDepProposer(pyproject_path=pyproject, propose=propose, merkle=merkle)

    proposer.propose_bump(_FINDING_VALID)

    merkle.log.assert_called_once()
    log_kwargs = merkle.log.call_args.kwargs
    assert log_kwargs["action"] == "knowledge.cve_dep_proposed"
    assert log_kwargs["payload"]["applied"] is False


def test_merkle_failure_does_not_propagate():
    """AC7: fallo de merkle.log no propaga excepción."""
    proposal_obj = MagicMock()
    proposal_obj.id = "prop-004"
    propose = MagicMock(return_value=proposal_obj)
    merkle = MagicMock()
    merkle.log.side_effect = RuntimeError("merkle down")
    pyproject = _make_pyproject(_PYPROJECT_WITH_DEP)
    proposer = CveDepProposer(pyproject_path=pyproject, propose=propose, merkle=merkle)

    # no debe lanzar
    result = proposer.propose_bump(_FINDING_VALID)
    assert result is proposal_obj


def test_no_import_dep_proposer_or_candidate():
    """AC8: el módulo no importa DepProposer ni candidate."""
    import ast
    import importlib
    import inspect

    mod = importlib.import_module("atlas.knowledge.self_improvement")
    source = inspect.getsource(mod)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom):
                assert node.module is None or "candidate" not in node.module
                if node.names:
                    for alias in node.names:
                        assert "DepProposer" not in alias.name or alias.name == "CveDepProposer"


# ---------------------------------------------------------------------------
# knowledge_scan_step flow tests (sin Orchestrator real, sin red)
# ---------------------------------------------------------------------------
# Estos tests reproducen la lógica de knowledge_scan_step() directamente,
# mockeando OsvDepSource.fetch para evitar llamadas HTTP reales.
# ---------------------------------------------------------------------------

import json as _json
from datetime import datetime, timezone
from unittest.mock import MagicMock

from atlas.knowledge.sources import OsvDepSource, RawRecord


def _run_scan_flow(
    floors: list[tuple[str, str]],
    fetcher_map: dict[str, RawRecord],
    installed_provider,
    propose_mock,
    pyproject_path,
) -> dict:
    """Reproduce el cuerpo de knowledge_scan_step() sin Orchestrator."""
    bridge = SelfImprovementBridge(installed_provider=installed_provider)

    # Inyectamos un fetcher stub: devuelve el RawRecord del mapa o 404
    def _stub_fetcher(method, url, body, headers):
        # La dep está codificada en el body JSON
        if body is not None:
            try:
                pkg_name = _json.loads(body)["package"]["name"]
            except (KeyError, ValueError):
                pkg_name = ""
        else:
            pkg_name = ""
        rec = fetcher_map.get(pkg_name)
        if rec is not None:
            return rec.status, rec.payload
        return 200, '{"vulns":[]}'

    osv = OsvDepSource(fetcher=_stub_fetcher)
    proposer = CveDepProposer(
        pyproject_path=pyproject_path,
        propose=propose_mock,
        merkle=MagicMock(),
    )

    scanned = 0
    total_findings = 0
    proposed = 0

    for dep_name, _floor in floors:
        records = osv.fetch(dep_name)
        record = records[0]
        if record.status != 200:
            scanned += 1
            continue
        content = _json.loads(record.payload)
        artifact = KnowledgeArtifact(
            id=f"osv/{dep_name}",
            domain="security/cve",
            source_id="osv.dev/pypi",
            content=content,
            provenance={
                "url": record.url,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        findings = bridge.scan(artifact)
        total_findings += len(findings)
        for f in findings:
            if f.fixed_version is not None:
                result = proposer.propose_bump(f)
                if result is not None:
                    proposed += 1
        scanned += 1

    return {"scanned": scanned, "findings": total_findings, "proposed": proposed}


_VULN_REQUESTS = {
    "id": "GHSA-scan-test-0001",
    "severity": [{"type": "CVSS_V3", "score": "8.0"}],
    "affected": [{
        "package": {"ecosystem": "PyPI", "name": "requests"},
        "ranges": [{
            "type": "ECOSYSTEM",
            "events": [{"introduced": "0"}, {"fixed": "2.32.0"}],
        }],
    }],
}

_PYPROJECT_REQUESTS = '[project]\ndependencies = [\n  "requests>=2.31.0",\n]\n'


def test_knowledge_scan_flow_counts_correctly(tmp_path):
    """Flujo completo: 1 dep en rango vulnerable → scanned=1, findings=1, proposed=1."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(_PYPROJECT_REQUESTS, encoding="utf-8")

    raw_200 = RawRecord(
        payload=_json.dumps({"vulns": [_VULN_REQUESTS]}),
        url="https://api.osv.dev/v1/query",
        status=200,
    )
    fetcher_map = {"requests": raw_200}
    propose_mock = MagicMock(return_value=MagicMock(id="prop-scan-1"))

    result = _run_scan_flow(
        floors=[("requests", "2.31.0")],
        fetcher_map=fetcher_map,
        installed_provider=lambda dep: "2.31.0" if dep == "requests" else None,
        propose_mock=propose_mock,
        pyproject_path=pyproject,
    )

    assert result["scanned"] == 1
    assert result["findings"] == 1
    assert result["proposed"] == 1
    propose_mock.assert_called_once()


def test_knowledge_scan_blocked_status_no_findings(tmp_path):
    """Record con status != 200 → skip sin findings ni propuestas."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(_PYPROJECT_REQUESTS, encoding="utf-8")

    # status=-1 simula bloqueo SSRF; status=403 simula error HTTP
    for bad_status in (-1, 403):
        raw_bad = RawRecord(
            payload="blocked:ssrf" if bad_status == -1 else "Forbidden",
            url="https://api.osv.dev/v1/query",
            status=bad_status,
        )
        fetcher_map = {"requests": raw_bad}
        propose_mock = MagicMock()

        result = _run_scan_flow(
            floors=[("requests", "2.31.0")],
            fetcher_map=fetcher_map,
            installed_provider=lambda dep: "2.31.0" if dep == "requests" else None,
            propose_mock=propose_mock,
            pyproject_path=pyproject,
        )

        assert result["scanned"] == 1, f"status={bad_status}"
        assert result["findings"] == 0, f"status={bad_status}"
        assert result["proposed"] == 0, f"status={bad_status}"
        propose_mock.assert_not_called()


def test_knowledge_scan_no_fixed_version_no_proposed(tmp_path):
    """Finding sin fixed_version → findings=1 pero proposed=0."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(_PYPROJECT_REQUESTS, encoding="utf-8")

    vuln_open = {
        "id": "GHSA-scan-open-range",
        "severity": [{"type": "CVSS_V3", "score": "5.0"}],
        "affected": [{
            "package": {"ecosystem": "PyPI", "name": "requests"},
            "ranges": [{
                "type": "ECOSYSTEM",
                # sin evento "fixed" → rango abierto
                "events": [{"introduced": "2.0.0"}],
            }],
        }],
    }
    raw_200 = RawRecord(
        payload=_json.dumps({"vulns": [vuln_open]}),
        url="https://api.osv.dev/v1/query",
        status=200,
    )
    fetcher_map = {"requests": raw_200}
    propose_mock = MagicMock()

    result = _run_scan_flow(
        floors=[("requests", "2.31.0")],
        fetcher_map=fetcher_map,
        installed_provider=lambda dep: "2.31.0" if dep == "requests" else None,
        propose_mock=propose_mock,
        pyproject_path=pyproject,
    )

    assert result["scanned"] == 1
    assert result["findings"] == 1
    assert result["proposed"] == 0
    propose_mock.assert_not_called()


# ---------------------------------------------------------------------------
# AtlasServiceRunner knowledge_scheduler gating tests
# ---------------------------------------------------------------------------


import time as _time
from atlas.runtime.service_runner import AtlasServiceRunner


def test_knowledge_scheduler_off_by_default(monkeypatch):
    """Sin ATLAS_KNOWLEDGE_SCHEDULER en el entorno → _knowledge_thread permanece None."""
    monkeypatch.delenv("ATLAS_KNOWLEDGE_SCHEDULER", raising=False)

    # Mock minimalista del Orchestrator
    mock_orch = MagicMock()
    mock_orch.knowledge_scan_step.return_value = {"scanned": 0, "findings": 0, "proposed": 0}

    runner = AtlasServiceRunner(mock_orch)
    runner._start_knowledge_scheduler_if_enabled()

    assert runner._knowledge_thread is None


def test_knowledge_scheduler_on_with_env(monkeypatch):
    """Con ATLAS_KNOWLEDGE_SCHEDULER=1 → thread daemon arrancado con name='atlas-knowledge'."""
    monkeypatch.setenv("ATLAS_KNOWLEDGE_SCHEDULER", "1")

    # Mock minimalista del Orchestrator
    mock_orch = MagicMock()
    mock_orch.knowledge_scan_step.return_value = {"scanned": 0, "findings": 0, "proposed": 0}

    runner = AtlasServiceRunner(mock_orch)
    runner._running = True
    runner._start_knowledge_scheduler_if_enabled()

    try:
        assert runner._knowledge_thread is not None, "Thread debe crearse con ATLAS_KNOWLEDGE_SCHEDULER=1"
        assert runner._knowledge_thread.is_alive(), "Thread debe estar vivo"
        assert runner._knowledge_thread.name == "atlas-knowledge", "Thread debe llamarse 'atlas-knowledge'"
        assert runner._knowledge_thread.daemon is True, "Thread debe ser daemon"
    finally:
        runner._running = False
        if runner._knowledge_thread and runner._knowledge_thread.is_alive():
            runner._knowledge_thread.join(timeout=2.0)


def test_knowledge_scheduler_true_env(monkeypatch):
    """Con ATLAS_KNOWLEDGE_SCHEDULER='true' → también arranca el thread."""
    monkeypatch.setenv("ATLAS_KNOWLEDGE_SCHEDULER", "true")

    mock_orch = MagicMock()
    mock_orch.knowledge_scan_step.return_value = {"scanned": 0, "findings": 0, "proposed": 0}

    runner = AtlasServiceRunner(mock_orch)
    runner._running = True
    runner._start_knowledge_scheduler_if_enabled()

    try:
        assert runner._knowledge_thread is not None
        assert runner._knowledge_thread.is_alive()
        assert runner._knowledge_thread.name == "atlas-knowledge"
        assert runner._knowledge_thread.daemon is True
    finally:
        runner._running = False
        if runner._knowledge_thread and runner._knowledge_thread.is_alive():
            runner._knowledge_thread.join(timeout=2.0)


def test_knowledge_scheduler_yes_env(monkeypatch):
    """Con ATLAS_KNOWLEDGE_SCHEDULER='yes' → también arranca el thread."""
    monkeypatch.setenv("ATLAS_KNOWLEDGE_SCHEDULER", "yes")

    mock_orch = MagicMock()
    mock_orch.knowledge_scan_step.return_value = {"scanned": 0, "findings": 0, "proposed": 0}

    runner = AtlasServiceRunner(mock_orch)
    runner._running = True
    runner._start_knowledge_scheduler_if_enabled()

    try:
        assert runner._knowledge_thread is not None
        assert runner._knowledge_thread.is_alive()
        assert runner._knowledge_thread.name == "atlas-knowledge"
        assert runner._knowledge_thread.daemon is True
    finally:
        runner._running = False
        if runner._knowledge_thread and runner._knowledge_thread.is_alive():
            runner._knowledge_thread.join(timeout=2.0)


def test_knowledge_scheduler_invalid_value(monkeypatch):
    """Con ATLAS_KNOWLEDGE_SCHEDULER='0' o 'false' → thread no se crea."""
    for invalid_val in ("0", "false", "no", ""):
        monkeypatch.setenv("ATLAS_KNOWLEDGE_SCHEDULER", invalid_val)

        mock_orch = MagicMock()
        mock_orch.knowledge_scan_step.return_value = {"scanned": 0, "findings": 0, "proposed": 0}

        runner = AtlasServiceRunner(mock_orch)
        runner._start_knowledge_scheduler_if_enabled()

        assert runner._knowledge_thread is None, f"ATLAS_KNOWLEDGE_SCHEDULER={invalid_val} no debe crear thread"


def test_cve_proposal_origin_is_self_audit_not_swarm():
    """G0.8 HITL invariante: las propuestas CVE usan origin='self_audit', no 'swarm'.

    Esto garantiza que tier1_auto_apply (que solo acepta origin='swarm') no puede
    auto-aplicar un bump de seguridad. CVE → HITL por defecto.
    """
    proposal_obj = MagicMock()
    proposal_obj.id = "prop-cve-hitl"
    propose = MagicMock(return_value=proposal_obj)
    merkle = MagicMock()
    pyproject = _make_pyproject(_PYPROJECT_WITH_DEP)
    proposer = CveDepProposer(pyproject_path=pyproject, propose=propose, merkle=merkle)

    proposer.propose_bump(_FINDING_VALID)

    call_kwargs = propose.call_args
    origin = call_kwargs.kwargs.get("origin")
    assert origin == "self_audit", (
        f"CVE proposal origin debe ser 'self_audit' para forzar HITL, got {origin!r}"
    )
    assert origin != "swarm", "CVE no debe usar origin='swarm' — bloquearía tier1_auto_apply"
