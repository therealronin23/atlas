"""Tests para KnowledgeVerifier (T5, ADR-049)."""

from __future__ import annotations

import hashlib

import pytest

from atlas.core.verify import CostTier, Verdict
from atlas.knowledge.artifact import KnowledgeArtifact
from atlas.knowledge.verifier import KnowledgeVerifier


def _sha(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _artifact(
    raw: str,
    content: object = None,
    url: str = "https://example.com/feed",
    fetched_at: str = "2026-06-14T10:00:00+00:00",
    raw_sha256: str | None = None,
) -> tuple[KnowledgeArtifact, str]:
    sha = raw_sha256 if raw_sha256 is not None else _sha(raw)
    prov: dict = {"url": url, "fetched_at": fetched_at, "raw_sha256": sha}
    if url == "":
        del prov["url"]
    if fetched_at == "":
        del prov["fetched_at"]
    if raw_sha256 == "":
        prov["raw_sha256"] = ""
    artifact = KnowledgeArtifact(
        id="art-1",
        domain="security/cve",
        source_id="nvd",
        content=content if content is not None else {"summary": "test data"},
        provenance=prov,
    )
    return artifact, raw


def make_verifier() -> KnowledgeVerifier:
    return KnowledgeVerifier()


# --- PASS ---

def test_pass_artifact_grounded() -> None:
    raw = '{"cve": "CVE-2026-0001", "score": 9.8}'
    artifact, raw_payload = _artifact(raw)
    ev = make_verifier().verify(artifact, raw_payload)
    assert ev.verdict is Verdict.PASS
    assert ev.total_cost is CostTier.STATIC
    assert all(c.passed for c in ev.checks)


# --- FAIL hash ---

def test_fail_hash_mismatch() -> None:
    raw = '{"cve": "CVE-2026-0001"}'
    artifact, _ = _artifact(raw, raw_sha256=_sha("otro payload"))
    ev = make_verifier().verify(artifact, raw)
    assert ev.verdict is Verdict.FAIL
    failed = [c for c in ev.checks if not c.passed]
    assert any(c.name == "hash_match" for c in failed)
    assert ev.reason != ""


# --- FAIL provenance incompleta ---

def test_fail_missing_fetched_at() -> None:
    raw = "payload"
    artifact, _ = _artifact(raw, fetched_at="")
    ev = make_verifier().verify(artifact, raw)
    assert ev.verdict is Verdict.FAIL
    failed_names = {c.name for c in ev.checks if not c.passed}
    assert "provenance_wellformed" in failed_names


def test_fail_missing_raw_sha256() -> None:
    raw = "payload"
    artifact, _ = _artifact(raw, raw_sha256="")
    ev = make_verifier().verify(artifact, raw)
    assert ev.verdict is Verdict.FAIL
    failed_names = {c.name for c in ev.checks if not c.passed}
    assert "provenance_wellformed" in failed_names
    # hash check también falla porque raw_sha256 vacío != hash calculado
    assert "hash_match" in failed_names


# --- FAIL content vacío ---

def test_fail_content_empty_dict() -> None:
    raw = "payload"
    artifact, _ = _artifact(raw, content={})
    ev = make_verifier().verify(artifact, raw)
    assert ev.verdict is Verdict.FAIL
    failed_names = {c.name for c in ev.checks if not c.passed}
    assert "content_nonempty" in failed_names


def test_fail_content_empty_string() -> None:
    raw = "payload"
    artifact, _ = _artifact(raw, content="")
    ev = make_verifier().verify(artifact, raw)
    assert ev.verdict is Verdict.FAIL
    failed_names = {c.name for c in ev.checks if not c.passed}
    assert "content_nonempty" in failed_names
