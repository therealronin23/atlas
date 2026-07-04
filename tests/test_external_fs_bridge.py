"""Tests for ExternalFsBridge — SEC-1 hardening."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.security.external_fs_bridge import ExternalFsBridge, FsDecision


# ---------------------------------------------------------------------------
# Tests basicos (regresion)
# ---------------------------------------------------------------------------


class TestBasicAllowlist:
    def test_extra_root_allowed(self) -> None:
        bridge = ExternalFsBridge(extra_roots={"/tmp"})
        result = bridge.check("/tmp/foo.txt")
        assert result.allowed
        assert result.resolved_path is not None

    def test_path_outside_root_denied(self) -> None:
        bridge = ExternalFsBridge(extra_roots={"/tmp"})
        result = bridge.check("/etc/passwd")
        assert not result.allowed
        assert "fuera" in result.reason.lower() or "root" in result.reason.lower()

    def test_no_extra_roots_denies_everything(self) -> None:
        bridge = ExternalFsBridge()
        result = bridge.check("/tmp/foo.txt")
        assert not result.allowed
        assert "fail-closed" in result.reason.lower()


# ---------------------------------------------------------------------------
# SEC-1: traversal y symlinks
# ---------------------------------------------------------------------------


class TestTraversalAndSymlinks:
    def test_traversal_resolved_outside_denied(self) -> None:
        bridge = ExternalFsBridge(extra_roots={"/tmp/allowed"})
        result = bridge.check("/tmp/allowed/../../etc/passwd")
        assert not result.allowed
        assert "fuera" in result.reason.lower() or "root" in result.reason.lower()

    def test_symlink_outside_root_denied(self, tmp_path: Path) -> None:
        # Crear estructura:
        #   root/  (permitido)
        #   secret.txt  (fuera del root)
        #   root/link -> ../secret.txt  (symlink que apunta fuera)
        root = tmp_path / "root"
        root.mkdir()
        secret = tmp_path / "secret.txt"
        secret.write_text("secret")
        symlink = root / "link"
        symlink.symlink_to(tmp_path / "secret.txt")

        bridge = ExternalFsBridge(extra_roots={str(root)})
        result = bridge.check(str(symlink))
        assert not result.allowed
        assert "fuera" in result.reason.lower() or "root" in result.reason.lower()


# ---------------------------------------------------------------------------
# SEC-1: add_root en caliente
# ---------------------------------------------------------------------------


class TestAddRoot:
    def test_add_root_enables_previously_denied(self) -> None:
        bridge = ExternalFsBridge()
        # Sin roots, todo denegado
        result_before = bridge.check("/tmp/foo.txt")
        assert not result_before.allowed

        # Anadir root en caliente
        bridge.add_root("/tmp")
        result_after = bridge.check("/tmp/foo.txt")
        assert result_after.allowed
        assert result_after.resolved_path is not None

    def test_add_root_exact_match(self) -> None:
        bridge = ExternalFsBridge(extra_roots={"/tmp"})
        bridge.add_root("/var")
        result = bridge.check("/var/log/syslog")
        assert result.allowed


# ---------------------------------------------------------------------------
# SEC-1: decision shape
# ---------------------------------------------------------------------------


class TestFsDecisionShape:
    def test_allowed_decision_has_correct_fields(self) -> None:
        bridge = ExternalFsBridge(extra_roots={"/tmp"})
        d = bridge.check("/tmp/foo.txt")
        assert d.allowed is True
        assert d.path == "/tmp/foo.txt"
        assert isinstance(d.reason, str)
        assert d.resolved_path is not None

    def test_denied_decision_shape(self) -> None:
        bridge = ExternalFsBridge()
        d = bridge.check("/etc/passwd")
        assert d.allowed is False
        assert d.path == "/etc/passwd"
        assert isinstance(d.reason, str)
        assert d.resolved_path is not None or d.resolved_path is None

    def test_fs_decision_is_frozen(self) -> None:
        d = FsDecision(allowed=True, path="/tmp", reason="ok", resolved_path="/tmp")
        with pytest.raises(AttributeError):
            d.allowed = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SEC-1: multiple roots
# ---------------------------------------------------------------------------


class TestMultipleRoots:
    def test_path_matches_any_root(self) -> None:
        bridge = ExternalFsBridge(extra_roots={"/tmp", "/var"})
        assert bridge.check("/tmp/foo.txt").allowed
        assert bridge.check("/var/log/syslog").allowed

    def test_path_outside_all_roots_denied(self) -> None:
        bridge = ExternalFsBridge(extra_roots={"/tmp", "/var"})
        result = bridge.check("/etc/passwd")
        assert not result.allowed
