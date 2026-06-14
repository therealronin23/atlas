"""Tests for KnowledgeBase (T6, ADR-049)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.core.verify import Evidence, Verdict
from atlas.knowledge.artifact import KnowledgeArtifact
from atlas.knowledge.base import KnowledgeBase, KnowledgeRejected


def _artifact(id: str = "a1", domain: str = "test/domain") -> KnowledgeArtifact:
    return KnowledgeArtifact(
        id=id,
        domain=domain,
        source_id="src-1",
        content={"value": 42},
        provenance={"url": "https://example.com", "fetched_at": "2026-06-14T00:00:00Z"},
    )


def _evidence(verdict: Verdict) -> Evidence:
    return Evidence(verdict=verdict)


class TestKnowledgeBaseAdd:
    def test_add_pass_persists_and_query_returns(self, tmp_path: Path) -> None:
        kb = KnowledgeBase(tmp_path)
        art = _artifact()
        kb.add(art, _evidence(Verdict.PASS))

        results = kb.query("test/domain")
        assert len(results) == 1
        assert results[0].id == "a1"
        assert results[0].domain == "test/domain"
        assert results[0].content == {"value": 42}

    def test_add_fail_raises_and_does_not_persist(self, tmp_path: Path) -> None:
        kb = KnowledgeBase(tmp_path)
        art = _artifact()
        with pytest.raises(KnowledgeRejected):
            kb.add(art, _evidence(Verdict.FAIL))

        # fichero no debe existir
        jsonl = tmp_path / "test__domain.jsonl"
        assert not jsonl.exists()

    def test_add_unknown_raises_and_does_not_persist(self, tmp_path: Path) -> None:
        kb = KnowledgeBase(tmp_path)
        art = _artifact()
        with pytest.raises(KnowledgeRejected):
            kb.add(art, _evidence(Verdict.UNKNOWN))

        jsonl = tmp_path / "test__domain.jsonl"
        assert not jsonl.exists()

    def test_multiple_adds_append(self, tmp_path: Path) -> None:
        kb = KnowledgeBase(tmp_path)
        for i in range(3):
            kb.add(_artifact(id=f"a{i}"), _evidence(Verdict.PASS))

        results = kb.query("test/domain")
        assert len(results) == 3
        assert {r.id for r in results} == {"a0", "a1", "a2"}


class TestKnowledgeBaseQuery:
    def test_query_nonexistent_domain_returns_empty(self, tmp_path: Path) -> None:
        kb = KnowledgeBase(tmp_path)
        assert kb.query("nonexistent") == []

    def test_query_filters_by_domain(self, tmp_path: Path) -> None:
        kb = KnowledgeBase(tmp_path)
        kb.add(_artifact(id="x", domain="domain/a"), _evidence(Verdict.PASS))
        kb.add(_artifact(id="y", domain="domain/b"), _evidence(Verdict.PASS))

        assert [r.id for r in kb.query("domain/a")] == ["x"]
        assert [r.id for r in kb.query("domain/b")] == ["y"]

    def test_query_skips_corrupt_lines(self, tmp_path: Path) -> None:
        kb = KnowledgeBase(tmp_path)
        art = _artifact()
        kb.add(art, _evidence(Verdict.PASS))

        # Inyectar línea corrupta en el jsonl
        jsonl = tmp_path / "test__domain.jsonl"
        with jsonl.open("a", encoding="utf-8") as fh:
            fh.write("NOT_VALID_JSON\n")

        results = kb.query("test/domain")
        # La línea corrupta se salta; la buena sigue ahí
        assert len(results) == 1
        assert results[0].id == "a1"

    def test_domain_slash_sanitation(self, tmp_path: Path) -> None:
        kb = KnowledgeBase(tmp_path)
        art = _artifact(domain="security/cve")
        kb.add(art, _evidence(Verdict.PASS))

        jsonl = tmp_path / "security__cve.jsonl"
        assert jsonl.is_file()

        results = kb.query("security/cve")
        assert len(results) == 1
        assert results[0].domain == "security/cve"
