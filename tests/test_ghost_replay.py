"""
Tests de GhostReplay (ADR-022, Gate D/D5).
Verifica lookup/record, TTL expiration, LRU eviction y purge.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from atlas.core.ghost_replay import (
    DEFAULT_TTL_SECONDS,
    GhostEntry,
    GhostReplay,
    GhostReplayError,
    compute_cache_key,
)


@pytest.fixture
def cache(tmp_path: Path) -> GhostReplay:
    return GhostReplay(tmp_path / "ghost")


# ===========================================================================
# Cache key
# ===========================================================================


class TestCacheKey:

    def test_deterministic(self) -> None:
        k1 = compute_cache_key("intent A", "safe", "ctx-1")
        k2 = compute_cache_key("intent A", "safe", "ctx-1")
        assert k1 == k2

    def test_differs_by_intent(self) -> None:
        a = compute_cache_key("intent A", "safe", "ctx")
        b = compute_cache_key("intent B", "safe", "ctx")
        assert a != b

    def test_differs_by_sensitivity(self) -> None:
        a = compute_cache_key("x", "safe", "ctx")
        b = compute_cache_key("x", "high", "ctx")
        assert a != b

    def test_differs_by_context(self) -> None:
        a = compute_cache_key("x", "safe", "ctx-1")
        b = compute_cache_key("x", "safe", "ctx-2")
        assert a != b


# ===========================================================================
# Constructor
# ===========================================================================


class TestConstructor:

    def test_negative_ttl_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            GhostReplay(tmp_path / "g", default_ttl_seconds=-1)

    def test_zero_max_entries_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            GhostReplay(tmp_path / "g", max_entries=0)


# ===========================================================================
# Lookup / Record
# ===========================================================================


class TestLookupRecord:

    def test_miss_returns_none(self, cache: GhostReplay) -> None:
        assert cache.lookup("nope", "safe", "ctx") is None
        assert cache.stats()["misses"] == 1

    def test_record_then_lookup_hit(self, cache: GhostReplay) -> None:
        cache.record("intent", "safe", "ctx", {"answer": 42})
        entry = cache.lookup("intent", "safe", "ctx")
        assert entry is not None
        assert entry.result == {"answer": 42}
        assert cache.stats()["hits"] == 1

    def test_different_context_no_hit(self, cache: GhostReplay) -> None:
        cache.record("intent", "safe", "ctx-1", {"r": 1})
        assert cache.lookup("intent", "safe", "ctx-2") is None

    def test_record_overwrites_same_key(self, cache: GhostReplay) -> None:
        cache.record("intent", "safe", "ctx", {"v": 1})
        cache.record("intent", "safe", "ctx", {"v": 2})
        entry = cache.lookup("intent", "safe", "ctx")
        assert entry is not None
        assert entry.result == {"v": 2}

    def test_record_with_metadata(self, cache: GhostReplay) -> None:
        cache.record(
            "intent", "safe", "ctx", {"r": 1},
            metadata={"provider": "groq", "tokens": 42},
        )
        entry = cache.lookup("intent", "safe", "ctx")
        assert entry is not None
        assert entry.metadata["provider"] == "groq"

    def test_lookup_touches_last_accessed(self, cache: GhostReplay) -> None:
        cache.record("intent", "safe", "ctx", {"r": 1})
        entry1 = cache.lookup("intent", "safe", "ctx")
        assert entry1 is not None
        before = entry1.last_accessed
        time.sleep(0.01)
        entry2 = cache.lookup("intent", "safe", "ctx")
        assert entry2 is not None
        assert entry2.last_accessed >= before


# ===========================================================================
# TTL
# ===========================================================================


class TestTTL:

    def test_expired_entry_returns_none(self, cache: GhostReplay) -> None:
        cache.record("i", "s", "c", {"x": 1}, ttl_seconds=0)
        # ttl_seconds=0 -> is_expired siempre False (sin TTL).
        # Necesitamos ttl=1 y esperar
        cache.record("i2", "s", "c", {"x": 2}, ttl_seconds=1)
        time.sleep(1.1)
        assert cache.lookup("i2", "s", "c") is None

    def test_zero_ttl_means_no_expiration(self, cache: GhostReplay) -> None:
        cache.record("i", "s", "c", {"x": 1}, ttl_seconds=0)
        time.sleep(0.1)
        assert cache.lookup("i", "s", "c") is not None

    def test_negative_ttl_means_no_expiration(self, cache: GhostReplay) -> None:
        # ttl_seconds <=0 lo tratamos como "no expira"
        cache.record("i", "s", "c", {"x": 1}, ttl_seconds=-1)
        assert cache.lookup("i", "s", "c") is not None

    def test_expire_removes_expired_only(self, cache: GhostReplay) -> None:
        cache.record("i-old", "s", "c-old", {"x": 1}, ttl_seconds=1)
        cache.record("i-new", "s", "c-new", {"x": 2}, ttl_seconds=3600)
        time.sleep(1.1)
        removed = cache.expire()
        assert removed == 1
        assert cache.lookup("i-old", "s", "c-old") is None
        assert cache.lookup("i-new", "s", "c-new") is not None


# ===========================================================================
# Purge + max_entries
# ===========================================================================


class TestPurgeAndEviction:

    def test_purge_clears_all(self, cache: GhostReplay) -> None:
        cache.record("a", "s", "c1", {"x": 1})
        cache.record("a", "s", "c2", {"x": 2})
        cache.record("a", "s", "c3", {"x": 3})
        assert cache.count() == 3
        removed = cache.purge()
        assert removed == 3
        assert cache.count() == 0

    def test_max_entries_evicts_oldest(self, tmp_path: Path) -> None:
        c = GhostReplay(tmp_path / "g", max_entries=2)
        c.record("a", "s", "c1", {"x": 1})
        time.sleep(0.01)
        c.record("b", "s", "c2", {"x": 2})
        time.sleep(0.01)
        c.record("c", "s", "c3", {"x": 3})
        # Tras la 3a entrada, la primera debe haber sido evictada
        assert c.lookup("a", "s", "c1") is None
        assert c.lookup("c", "s", "c3") is not None
        assert c.stats()["evictions"] >= 1


# ===========================================================================
# Stats
# ===========================================================================


class TestStats:

    def test_initial_counts(self, cache: GhostReplay) -> None:
        stats = cache.stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["entries"] == 0

    def test_hits_misses_tracked(self, cache: GhostReplay) -> None:
        cache.lookup("x", "s", "c")          # miss
        cache.record("x", "s", "c", {"r": 1})
        cache.lookup("x", "s", "c")          # hit
        stats = cache.stats()
        assert stats["misses"] == 1
        assert stats["hits"] == 1
        assert stats["entries"] == 1


# ===========================================================================
# Tolerancia a fallos
# ===========================================================================


class TestRobustness:

    def test_corrupted_file_skipped(self, cache: GhostReplay, tmp_path: Path) -> None:
        cache.record("x", "s", "c", {"r": 1})
        # Corromper el archivo manualmente
        for f in (tmp_path / "ghost").rglob("*.json"):
            f.write_text("{garbage}")
        # Lookup deberia tratarlo como miss
        assert cache.lookup("x", "s", "c") is None
