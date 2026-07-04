"""PanoramaScout — descubrimiento por TEMA DE INTERES, no por lista de fuentes fijas.

El usuario corrigio al asistente: el ecosistema no es una lista de fuentes
conocidas (Hermes/Cursor/Odysseus) -- puede ser un paper, un lenguaje nuevo,
un SaaS sin nombre todavia. Los scouts existentes (RegistryScout,
CommunityScout) descubren contra URLs fijas -- exactamente esa limitacion.
PanoramaScout busca por tema en GitHub (repos search API, ya en la allowlist
de SSRFBridge). HN Algolia y arXiv quedan para despues, mismo patron.

Reglas que estos tests fijan:

- **CERO red real:** ``fetch`` falso inyectado.
- **Fail-closed por tema:** un tema roto (egress denegado o fetch/parseo
  fallido) no tumba el descubrimiento de los demas temas.
- **max_results_per_topic** limita el numero de findings devueltos.
- **to_dict()** hace roundtrip de los campos.
- **Auditoria:** al menos una entrada Merkle por tema procesado.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.core.self_maintenance.panorama_scout import PanoramaFinding, PanoramaScout
from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.ssrf_bridge import BridgeDecision, SSRFBridge


@pytest.fixture
def merkle(tmp_path: Path) -> MerkleLogger:
    return MerkleLogger(tmp_path / "merkle")


def _github_body(*repos: dict) -> str:
    import json

    return json.dumps({"items": list(repos)})


def _repo(full_name: str, html_url: str, description: str | None) -> dict:
    return {"full_name": full_name, "html_url": html_url, "description": description}


class TestDiscoverySingleTopic:
    def test_valid_json_two_repos_yields_two_findings(self, merkle) -> None:
        body = _github_body(
            _repo("acme/mempalace", "https://github.com/acme/mempalace", "A memory palace tool"),
            _repo("acme/other-repo", "https://github.com/acme/other-repo", "Another thing"),
        )
        scout = PanoramaScout(
            merkle=merkle,
            bridge=SSRFBridge(),
            fetch=lambda u: body,
            topics=["memory palace"],
        )
        findings = scout.discover()
        assert len(findings) == 2
        for f in findings:
            assert f.source == "github"
            assert f.topic == "memory palace"
        assert findings[0].title == "acme/mempalace"
        assert findings[0].url == "https://github.com/acme/mempalace"
        assert findings[0].excerpt == "A memory palace tool"


class TestMultipleTopics:
    def test_two_topics_each_with_correct_topic_field(self, merkle) -> None:
        def fake_fetch(url: str) -> str:
            if "memory+palace" in url:
                return _github_body(_repo("a/mempalace", "https://github.com/a/mempalace", "x"))
            return _github_body(_repo("b/newlang", "https://github.com/b/newlang", "y"))

        scout = PanoramaScout(
            merkle=merkle,
            bridge=SSRFBridge(),
            fetch=fake_fetch,
            topics=["memory palace", "new language"],
        )
        findings = scout.discover()
        assert {f.topic for f in findings} == {"memory palace", "new language"}
        assert len(findings) == 2


class TestFailClosedPerTopic:
    def test_egress_denied_for_one_topic_skips_only_that_topic(self, merkle) -> None:
        allowed_body = _github_body(_repo("a/ok-repo", "https://github.com/a/ok-repo", "fine"))

        class _PartialDeny(SSRFBridge):
            def check(self, url: str) -> BridgeDecision:  # type: ignore[override]
                if "blocked+topic" in url:
                    return BridgeDecision(allowed=False, url=url, reason="denied", domain="")
                return BridgeDecision(allowed=True, url=url, reason="ok", domain="api.github.com")

        scout = PanoramaScout(
            merkle=merkle,
            bridge=_PartialDeny(),
            fetch=lambda u: allowed_body,
            topics=["blocked topic", "allowed topic"],
        )
        findings = scout.discover()
        assert [f.topic for f in findings] == ["allowed topic"]

    def test_fetch_exception_for_one_topic_does_not_break_others(self, merkle) -> None:
        ok_body = _github_body(_repo("a/ok-repo", "https://github.com/a/ok-repo", "fine"))

        def fake_fetch(url: str) -> str:
            if "boom+topic" in url:
                raise ConnectionError("down")
            return ok_body

        scout = PanoramaScout(
            merkle=merkle,
            bridge=SSRFBridge(),
            fetch=fake_fetch,
            topics=["boom topic", "good topic"],
        )
        findings = scout.discover()
        assert [f.topic for f in findings] == ["good topic"]


class TestEmptyOrMissingItems:
    def test_response_without_items_key_yields_zero_findings(self, merkle) -> None:
        scout = PanoramaScout(
            merkle=merkle,
            bridge=SSRFBridge(),
            fetch=lambda u: "{}",
            topics=["some topic"],
        )
        assert scout.discover() == []

    def test_response_with_empty_items_yields_zero_findings(self, merkle) -> None:
        scout = PanoramaScout(
            merkle=merkle,
            bridge=SSRFBridge(),
            fetch=lambda u: _github_body(),
            topics=["some topic"],
        )
        assert scout.discover() == []


class TestMaxResults:
    def test_max_results_per_topic_limits_findings(self, merkle) -> None:
        body = _github_body(
            *[_repo(f"a/repo{i}", f"https://github.com/a/repo{i}", "d") for i in range(10)]
        )
        scout = PanoramaScout(
            merkle=merkle,
            bridge=SSRFBridge(),
            fetch=lambda u: body,
            topics=["some topic"],
            max_results_per_topic=3,
        )
        findings = scout.discover()
        assert len(findings) == 3


class TestToDictRoundtrip:
    def test_to_dict_contains_all_fields(self) -> None:
        finding = PanoramaFinding(
            topic="memory palace",
            source="github",
            title="acme/mempalace",
            url="https://github.com/acme/mempalace",
            excerpt="A memory palace tool",
        )
        d = finding.to_dict()
        assert d["topic"] == "memory palace"
        assert d["source"] == "github"
        assert d["title"] == "acme/mempalace"
        assert d["url"] == "https://github.com/acme/mempalace"
        assert d["excerpt"] == "A memory palace tool"
        assert "discovered_at" in d


class TestAudit:
    def test_audits_at_least_once_per_topic(self, merkle) -> None:
        body = _github_body(_repo("a/repo", "https://github.com/a/repo", "d"))
        scout = PanoramaScout(
            merkle=merkle,
            bridge=SSRFBridge(),
            fetch=lambda u: body,
            topics=["topic one", "topic two"],
        )
        scout.discover()
        entries = list(merkle.read_all())
        actions = [e.action for e in entries if e.agent == PanoramaScout.AGENT]
        assert len(actions) >= 2
