from __future__ import annotations

import pytest

from atlas.knowledge.artifact import KnowledgeArtifact
from atlas.knowledge.self_improvement import SelfImprovementBridge, SelfRelevantFinding

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
