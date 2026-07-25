from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from atlas.core.self_maintenance.curated_sources import load_curated_findings
from atlas.security.ssrf_bridge import DEFAULT_ALLOWED_DOMAINS


def test_missing_file_returns_empty_list(tmp_path: Path) -> None:
    assert load_curated_findings(tmp_path / "nope.yaml") == []


def test_loads_github_url_as_finding(tmp_path: Path) -> None:
    path = tmp_path / "curated_sources.yaml"
    path.write_text(yaml.safe_dump({"sources": [{"url": "https://github.com/vercel-labs/agent-skills", "note": "Vercel skills registry"}]}), encoding="utf-8")
    finding = load_curated_findings(path)[0]
    assert (finding.source, finding.title, finding.excerpt, finding.topic) == ("github", "vercel-labs/agent-skills", "Vercel skills registry", "curated: Vercel skills registry")


def test_non_github_or_malformed_input_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "curated_sources.yaml"
    path.write_text("sources:\n  - url: https://tododeia.com/community\n", encoding="utf-8")
    assert load_curated_findings(path) == []
    path.write_text("not: [valid, yaml:", encoding="utf-8")
    assert load_curated_findings(path) == []


def test_loads_official_publisher_source_with_cleaned_bounded_text(tmp_path: Path) -> None:
    path = tmp_path / "curated_sources.yaml"
    path.write_text(yaml.safe_dump({
        "publishers": [{"id": "openai", "domains": ["developers.openai.com"]}],
        "sources": [{
            "publisher": "openai",
            "kind": "official_docs",
            "url": "https://developers.openai.com/resources/",
            "note": "OpenAI developer resources",
        }],
    }), encoding="utf-8")
    bridge = SimpleNamespace(check=lambda _url: SimpleNamespace(allowed=True))

    findings = load_curated_findings(
        path,
        bridge=bridge,
        fetch=lambda _url: "<html><body><h1>Tools</h1><script>ignore()</script><p>Reliable agents</p></body></html>",
    )

    assert len(findings) == 1
    assert findings[0].source == "official"
    assert findings[0].title == "OpenAI developer resources"
    assert findings[0].excerpt == "OpenAI developer resources — Tools Reliable agents"


def test_official_source_rejects_undeclared_host_without_fetching(tmp_path: Path) -> None:
    path = tmp_path / "curated_sources.yaml"
    path.write_text(yaml.safe_dump({
        "publishers": [{"id": "openai", "domains": ["developers.openai.com"]}],
        "sources": [{
            "publisher": "openai",
            "kind": "official_docs",
            "url": "https://evil.example/resources/",
            "note": "not OpenAI",
        }],
    }), encoding="utf-8")

    assert load_curated_findings(path, fetch=lambda _url: (_ for _ in ()).throw(AssertionError())) == []


def test_official_source_denied_by_bridge_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "curated_sources.yaml"
    path.write_text(yaml.safe_dump({
        "publishers": [{"id": "openai", "domains": ["developers.openai.com"]}],
        "sources": [{
            "publisher": "openai",
            "kind": "official_docs",
            "url": "https://developers.openai.com/resources/",
            "note": "OpenAI developer resources",
        }],
    }), encoding="utf-8")
    bridge = SimpleNamespace(check=lambda _url: SimpleNamespace(allowed=False))

    assert load_curated_findings(path, bridge=bridge, fetch=lambda _url: "never") == []


def test_checked_in_source_manifest_validates_every_declared_source_without_network() -> None:
    path = Path(__file__).resolve().parent.parent / "docs" / "knowledge" / "curated_sources.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    findings = load_curated_findings(path)
    assert len(findings) == len(data["sources"])
    assert {finding.url for finding in findings} == {source["url"] for source in data["sources"]}


def test_checked_in_publisher_domains_are_ssrf_allowlisted() -> None:
    path = Path(__file__).resolve().parent.parent / "docs" / "knowledge" / "curated_sources.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    declared = {
        domain
        for publisher in data["publishers"]
        for domain in publisher["domains"]
    }
    assert declared <= DEFAULT_ALLOWED_DOMAINS
