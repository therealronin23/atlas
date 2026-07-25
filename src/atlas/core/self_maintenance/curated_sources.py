"""Operator-curated research sources for the normal discovery pipeline.

The manifest is intentionally declarative: publisher-owned exact domains are
reviewable data, while the loader only obtains bounded reference text.  A
source is never a trust bypass for executable adoption.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from atlas.core.self_maintenance.panorama_scout import PanoramaFinding

_GITHUB_REPO_RE = re.compile(
    r"github\.com/([\w.-]+/[\w.-]+?)(?:\.git)?(?:[/?#]|\s|$)", re.IGNORECASE
)
_OFFICIAL_KINDS = frozenset({
    "official_docs", "official_registry", "package_registry",
    "security_advisory", "research_index",
})
_EXCERPT_MAX = 300


class _VisibleText(HTMLParser):
    """Extract visible text without treating source markup as instructions."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "template"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "template"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self._parts.append(data)

    def text(self) -> str:
        return " ".join(" ".join(self._parts).split())[:_EXCERPT_MAX]


def _publisher_domains(data: dict[str, Any]) -> dict[str, frozenset[str]]:
    publishers = data.get("publishers", [])
    if not isinstance(publishers, list):
        return {}
    domains: dict[str, frozenset[str]] = {}
    for raw in publishers:
        if not isinstance(raw, dict):
            continue
        publisher = str(raw.get("id", "")).strip()
        values = raw.get("domains", [])
        if not publisher or not isinstance(values, list):
            continue
        parsed = frozenset(str(value).strip().lower() for value in values if str(value).strip())
        if parsed:
            domains[publisher] = parsed
    return domains


def _is_declared_official_source(entry: dict[str, Any], publishers: dict[str, frozenset[str]]) -> tuple[str, str] | None:
    publisher = str(entry.get("publisher", "")).strip()
    kind = str(entry.get("kind", "")).strip()
    url = str(entry.get("url", "")).strip()
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if kind not in _OFFICIAL_KINDS or not publisher or parsed.scheme != "https":
        return None
    if host not in publishers.get(publisher, frozenset()):
        return None
    return publisher, url


def _official_finding(
    entry: dict[str, Any],
    *,
    publishers: dict[str, frozenset[str]],
    bridge: Any | None,
    fetch: Callable[[str], str] | None,
) -> PanoramaFinding | None:
    validated = _is_declared_official_source(entry, publishers)
    if validated is None:
        return None
    publisher, url = validated
    note = str(entry.get("note", "")).strip() or publisher
    topic = str(entry.get("topic", "")).strip() or f"curated: {note}"
    excerpt = note
    if bridge is not None or fetch is not None:
        if bridge is None or fetch is None:
            return None
        try:
            decision = bridge.check(url)
            if not decision.allowed:
                return None
            parser = _VisibleText()
            parser.feed(fetch(url))
            parser.close()
            material = parser.text()
        except Exception:  # noqa: BLE001 - one source cannot break discovery
            return None
        if material:
            excerpt = f"{note} — {material}"[:_EXCERPT_MAX]
    return PanoramaFinding(topic=topic, source="official", title=note, url=url, excerpt=excerpt)


def load_curated_findings(
    path: Path,
    *,
    bridge: Any | None = None,
    fetch: Callable[[str], str] | None = None,
) -> list[PanoramaFinding]:
    """Load validated curated references, failing closed per malformed source.

    Legacy GitHub records remain supported.  Non-GitHub entries require a
    declared publisher and exact HTTPS host; they emit ``official`` research
    findings and never directly become executable catalog candidates.
    """
    if not path.is_file():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    if not isinstance(data, dict):
        return []
    sources = data.get("sources", [])
    if not isinstance(sources, list):
        return []
    publishers = _publisher_domains(data)
    findings: list[PanoramaFinding] = []
    for entry in sources:
        if not isinstance(entry, dict):
            continue
        official = _official_finding(entry, publishers=publishers, bridge=bridge, fetch=fetch)
        if official is not None:
            findings.append(official)
            continue
        url = str(entry.get("url", "")).strip()
        note = str(entry.get("note", "")).strip()
        match = _GITHUB_REPO_RE.search(url)
        if not match:
            continue
        findings.append(PanoramaFinding(
            topic=f"curated: {note}" if note else "curated",
            source="github", title=match.group(1), url=url, excerpt=note,
        ))
    return findings
