"""Tests TDD para pending_hmac_secret() — autogeneración de clave local y eliminación
del fallback a HERMES_API_KEY."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

import pytest

from atlas.security.pending_store import pending_hmac_secret


class TestPendingHmacSecret:
    """AC:
    a) Sin env vars, se autogenera una clave local persistente y se reutiliza.
    b) NO se usa HERMES_API_KEY como fallback.
    c) ATLAS_PENDING_HMAC_KEY explícita tiene prioridad.
    """

    def test_autogenera_clave_sin_env_vars(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC(a): sin env vars devuelve bytes no vacíos (no lanza)."""
        monkeypatch.delenv("ATLAS_PENDING_HMAC_KEY", raising=False)
        monkeypatch.delenv("HERMES_API_KEY", raising=False)
        monkeypatch.setenv("ATLAS_HOME", str(tmp_path))

        key = pending_hmac_secret()
        assert isinstance(key, bytes)
        assert len(key) > 0

    def test_clave_autogenerada_es_persistente(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC(a): segunda llamada devuelve la misma clave (persistencia)."""
        monkeypatch.delenv("ATLAS_PENDING_HMAC_KEY", raising=False)
        monkeypatch.delenv("HERMES_API_KEY", raising=False)
        monkeypatch.setenv("ATLAS_HOME", str(tmp_path))

        key1 = pending_hmac_secret()
        key2 = pending_hmac_secret()
        assert key1 == key2

    def test_hermes_api_key_no_es_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC(b): incluso con HERMES_API_KEY presente, no se usa como secreto HMAC."""
        monkeypatch.delenv("ATLAS_PENDING_HMAC_KEY", raising=False)
        monkeypatch.setenv("HERMES_API_KEY", "hermes-secret-value")
        monkeypatch.setenv("ATLAS_HOME", str(tmp_path))

        key = pending_hmac_secret()
        assert key != b"hermes-secret-value"

    def test_atlas_pending_hmac_key_tiene_prioridad(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC(c): ATLAS_PENDING_HMAC_KEY explícita tiene prioridad sobre autogenerada."""
        monkeypatch.setenv("ATLAS_PENDING_HMAC_KEY", "explicit-key-value")
        monkeypatch.delenv("HERMES_API_KEY", raising=False)
        monkeypatch.setenv("ATLAS_HOME", str(tmp_path))

        key = pending_hmac_secret()
        assert key == b"explicit-key-value"

    def test_no_lanza_sin_env_vars(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC(a): sin ninguna env var no debe lanzar ValueError."""
        monkeypatch.delenv("ATLAS_PENDING_HMAC_KEY", raising=False)
        monkeypatch.delenv("HERMES_API_KEY", raising=False)
        monkeypatch.setenv("ATLAS_HOME", str(tmp_path))

        # No debe lanzar
        pending_hmac_secret()
