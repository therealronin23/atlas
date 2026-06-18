"""Gate H6 — environment sensor tests."""

from __future__ import annotations

from atlas.core.environment_sensor import (
    EnvironmentFingerprint,
    capture_fingerprint,
    fingerprint_tag,
    fingerprint_from_tags,
    is_stale,
)
from atlas import __version__


def test_fingerprint_tag_roundtrip() -> None:
    fp = capture_fingerprint(atlas_version="0.7.0-test")
    tag = fingerprint_tag(fp)
    restored = fingerprint_from_tags([tag, "generated_tool"])
    assert restored is not None
    assert restored.python_version == fp.python_version


from atlas import __version__


def test_default_fingerprint_uses_current_runtime_version() -> None:
    fp = capture_fingerprint()
    assert fp.atlas_version == __version__


def test_is_stale_on_python_change() -> None:
    stored = EnvironmentFingerprint(
        python_version="0.0.0",
        atlas_version="0.6.1",
        dependency_hash="abc",
    )
    current = capture_fingerprint()
    assert is_stale(stored, current)
