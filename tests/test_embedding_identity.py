"""Regression tests for persistent embedding-space identity guards."""

from __future__ import annotations

import importlib.metadata
import sqlite3
import sys
import types
from pathlib import Path

import pytest

import atlas.memory.embeddings as embeddings_module
from atlas.memory.embeddings import (
    LiteLLMEmbedder,
    LiteLLMEmbedderConfig,
    StubEmbedder,
)
from atlas.memory.memory_index import SqliteMemoryIndex
from atlas.memory.record import GenericRecord
from atlas.memory.vector_store import KuzuVectorStore, VectorStoreError


def _litellm_stub(model: str, *, dim: int = 32) -> LiteLLMEmbedder:
    return LiteLLMEmbedder(
        LiteLLMEmbedderConfig(model=model, dim=dim),
        mode="stub",
    )


def _delete_kuzu_identity(store: KuzuVectorStore) -> None:
    for key in ("embedding_identity", "embedding_fingerprint"):
        store._conn.execute(
            "MATCH (m:AtlasMeta {key: $key}) DELETE m",
            {"key": key},
        )


class TestEmbedderIdentity:
    def test_stub_identity_is_deterministic_and_dimension_bound(self) -> None:
        first = StubEmbedder(dim=32)
        same = StubEmbedder(dim=32)
        other_dim = StubEmbedder(dim=64)

        assert first.identity == same.identity
        assert first.fingerprint == same.fingerprint
        assert first.identity != other_dim.identity
        assert first.fingerprint != other_dim.fingerprint
        assert "sha256" in first.identity

    def test_litellm_identity_binds_model_and_effective_mode(self) -> None:
        config_a = LiteLLMEmbedderConfig(model="provider/model-a", dim=32)
        config_b = LiteLLMEmbedderConfig(model="provider/model-b", dim=32)

        stub_a = LiteLLMEmbedder(config_a, mode="stub")
        stub_b = LiteLLMEmbedder(config_b, mode="stub")
        live_a = LiteLLMEmbedder(config_a, mode="live")

        assert stub_a.identity != stub_b.identity
        assert stub_a.identity != live_a.identity
        assert "provider/model-a" in stub_a.identity
        assert "effective_mode=stub" in stub_a.identity
        assert "effective_mode=live" in live_a.identity

    def test_auto_effective_mode_does_not_change_after_construction(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("AUTO_EMBED_KEY", raising=False)
        monkeypatch.setattr(embeddings_module, "_HAS_LITELLM", True)
        config = LiteLLMEmbedderConfig(
            model="provider/model-a",
            dim=32,
            api_key_env="AUTO_EMBED_KEY",
        )

        resolved_stub = LiteLLMEmbedder(config, mode="auto")
        identity = resolved_stub.identity
        monkeypatch.setenv("AUTO_EMBED_KEY", "appeared-later")

        assert resolved_stub.effective_mode == "stub"
        assert resolved_stub.identity == identity

    def test_fastembed_identity_binds_implementation_version(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        artifact_dir = tmp_path / "model"
        artifact_dir.mkdir()
        (artifact_dir / "model.onnx").write_bytes(b"model-v1")
        (artifact_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

        class _ConcreteModel:
            _model_dir = artifact_dir

        class _FakeModel:
            def __init__(self, model_name: str) -> None:
                self.model_name = model_name
                self.model = _ConcreteModel()

            def embed(self, texts: list[str]) -> list[list[float]]:
                return [[0.0] * 32 for _ in texts]

        fake_module = types.ModuleType("fastembed")
        fake_module.TextEmbedding = _FakeModel  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "fastembed", fake_module)
        monkeypatch.setattr(
            importlib.metadata,
            "version",
            lambda package: "9.9.9",
        )
        monkeypatch.setattr(embeddings_module.FastEmbedEmbedder, "_MODEL_CACHE", {})
        monkeypatch.setattr(
            embeddings_module.FastEmbedEmbedder,
            "_ARTIFACT_DIGEST_CACHE",
            {},
        )

        embedder = embeddings_module.FastEmbedEmbedder(
            model_name="provider/model-a", dim=32
        )

        assert "implementation_version=9.9.9" in embedder.identity
        assert "artifact_sha256=" in embedder.identity

    def test_fastembed_identity_changes_when_artifact_bytes_change(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _ConcreteModel:
            def __init__(self, model_dir: Path) -> None:
                self._model_dir = model_dir

        class _FakeModel:
            def __init__(self, model_name: str) -> None:
                self.model_name = model_name
                self.model = _ConcreteModel(tmp_path)

            def embed(self, texts: list[str]) -> list[list[float]]:
                return [[0.0] * 32 for _ in texts]

        fake_module = types.ModuleType("fastembed")
        fake_module.TextEmbedding = _FakeModel  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "fastembed", fake_module)
        monkeypatch.setattr(importlib.metadata, "version", lambda package: "9.9.9")
        monkeypatch.setattr(embeddings_module.FastEmbedEmbedder, "_MODEL_CACHE", {})
        monkeypatch.setattr(
            embeddings_module.FastEmbedEmbedder,
            "_ARTIFACT_DIGEST_CACHE",
            {},
        )
        artifact = tmp_path / "model.onnx"
        artifact.write_bytes(b"model-v1")
        first = embeddings_module.FastEmbedEmbedder("model-a", dim=32)

        artifact.write_bytes(b"model-v2")
        monkeypatch.setattr(embeddings_module.FastEmbedEmbedder, "_MODEL_CACHE", {})
        monkeypatch.setattr(
            embeddings_module.FastEmbedEmbedder,
            "_ARTIFACT_DIGEST_CACHE",
            {},
        )
        second = embeddings_module.FastEmbedEmbedder("model-a", dim=32)

        assert first.identity != second.identity


class TestSqliteEmbeddingIdentityGuard:
    def test_embedder_with_self_inconsistent_fingerprint_is_rejected(
        self, tmp_path: Path
    ) -> None:
        class _ForgedEmbedder:
            dim = 2
            identity = "custom:v1;model=example;dim=2"
            fingerprint = "sha256:not-the-digest-of-identity"

            def embed(self, text: str) -> list[float]:
                return [1.0, 0.0]

            def embed_batch(self, texts: list[str]) -> list[list[float]]:
                return [self.embed(text) for text in texts]

        with pytest.raises(ValueError, match="fingerprint is inconsistent"):
            SqliteMemoryIndex(tmp_path / "memory.db", embedder=_ForgedEmbedder())

    def test_same_dimension_different_model_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "memory.db"
        first = SqliteMemoryIndex(path, embedder=_litellm_stub("provider/model-a"))
        first.upsert(GenericRecord(record_id="one", text="stored vector"))
        first.close()

        with pytest.raises(ValueError, match="identity mismatch"):
            SqliteMemoryIndex(path, embedder=_litellm_stub("provider/model-b"))

    def test_legacy_empty_index_adopts_current_identity(self, tmp_path: Path) -> None:
        path = tmp_path / "memory.db"
        original = SqliteMemoryIndex(path, embedder=StubEmbedder(dim=32))
        original.close()
        with sqlite3.connect(path) as conn:
            conn.execute(
                "DELETE FROM meta WHERE key IN (?, ?)",
                ("embedder_identity", "embedder_fingerprint"),
            )

        reopened = SqliteMemoryIndex(path, embedder=StubEmbedder(dim=32))
        stored = dict(reopened._conn.execute("SELECT key, value FROM meta"))
        assert stored["embedder_identity"] == reopened._embedder.identity
        assert stored["embedder_fingerprint"] == reopened._embedder.fingerprint

    def test_legacy_populated_index_without_identity_fails_closed(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "memory.db"
        original = SqliteMemoryIndex(path, embedder=StubEmbedder(dim=32))
        original.upsert(GenericRecord(record_id="one", text="stored vector"))
        original._conn.execute(
            "DELETE FROM meta WHERE key IN (?, ?)",
            ("embedder_identity", "embedder_fingerprint"),
        )
        original._conn.commit()
        original.close()

        with pytest.raises(ValueError, match="lacks embedder identity"):
            SqliteMemoryIndex(path, embedder=StubEmbedder(dim=32))


class TestKuzuEmbeddingIdentityGuard:
    def test_same_dimension_different_model_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "vectors.kuzu"
        first = KuzuVectorStore(path, embedder=_litellm_stub("provider/model-a"))
        first.add_pattern("stored vector")
        first.close()

        with pytest.raises(VectorStoreError, match="identity mismatch"):
            KuzuVectorStore(path, embedder=_litellm_stub("provider/model-b"))

    def test_legacy_empty_store_adopts_current_identity(self, tmp_path: Path) -> None:
        path = tmp_path / "vectors.kuzu"
        original = KuzuVectorStore(path, embedder=StubEmbedder(dim=32))
        _delete_kuzu_identity(original)
        original.close()

        reopened = KuzuVectorStore(path, embedder=StubEmbedder(dim=32))
        assert reopened._read_meta("embedding_identity") == reopened.embedder.identity
        assert (
            reopened._read_meta("embedding_fingerprint")
            == reopened.embedder.fingerprint
        )

    def test_legacy_populated_store_without_identity_fails_closed(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "vectors.kuzu"
        original = KuzuVectorStore(path, embedder=StubEmbedder(dim=32))
        original.add_pattern("stored vector")
        _delete_kuzu_identity(original)
        original.close()

        with pytest.raises(VectorStoreError, match="lacks embedder identity"):
            KuzuVectorStore(path, embedder=StubEmbedder(dim=32))
