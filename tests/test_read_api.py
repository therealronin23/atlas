"""
Tests for the Read-API endpoints exposed by exec_api.build_router.

Covers:
  GET /api/exec/api/v1/log/tree          — T1, T2
  GET /api/exec/api/v1/log/entries       — T3, T4, T5, T6
  GET /api/exec/api/v1/log/proof/inclusion/{leaf_index} — T7, T8
  503 when orch has no _transparency — T9

Note: the log sub-router has prefix=/api/v1/log and is included inside the
exec router which has prefix=/api/exec, so the full mount path becomes
/api/exec/api/v1/log/... (FastAPI stacks the prefixes).
"""

from __future__ import annotations

import base64
import json

import fastapi
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from atlas.interfaces.exec_api import build_router
from atlas.security.authorization import Ed25519Signer
from atlas.transparency.log import TransparencyLog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_test_app():
    """Build a minimal FastAPI app wired to a fresh TransparencyLog with 3 entries."""
    key = Ed25519PrivateKey.generate()
    signer = Ed25519Signer(key.private_bytes_raw())
    log = TransparencyLog(signer=signer)

    log.append(json.dumps({"seq": 0, "payload_hash": "abc"}).encode())
    log.append(json.dumps({"seq": 1, "payload_hash": "def"}).encode())
    log.append(b"\x00\xff\xfe")  # non-JSON binary entry

    class _MockGW:
        _log = log

    class _MockHub:
        _transparency = _MockGW()

    class _MockOrch:
        _inference_hub = _MockHub()

    app = fastapi.FastAPI()
    orch = _MockOrch()
    app.include_router(build_router(lambda: orch))
    return TestClient(app), log


# Base URL prefix for all Read-API endpoints.
# The log sub-router (prefix=/api/v1/log) is nested inside the exec router
# (prefix=/api/exec), so FastAPI stacks them.
_LOG_BASE = "/api/exec/api/v1/log"


def _make_app_no_log():
    """Build an app whose orchestrator has no _transparency at all."""

    class _MockOrch:
        pass  # no _inference_hub

    app = fastapi.FastAPI()
    orch = _MockOrch()
    app.include_router(build_router(lambda: orch))
    return TestClient(app)


# ---------------------------------------------------------------------------
# /api/v1/log/tree
# ---------------------------------------------------------------------------


def test_read_api_tree_returns_200():
    client, _ = _make_test_app()
    r = client.get(f"{_LOG_BASE}/tree")
    assert r.status_code == 200
    data = r.json()
    for key in ("tree_size", "root_hash", "timestamp", "signature", "algo"):
        assert key in data, f"missing key: {key}"


def test_read_api_tree_size_matches():
    client, log = _make_test_app()
    r = client.get(f"{_LOG_BASE}/tree")
    assert r.status_code == 200
    assert r.json()["tree_size"] == log.tree_size == 3


# ---------------------------------------------------------------------------
# /api/v1/log/entries
# ---------------------------------------------------------------------------


def test_read_api_entries_range():
    client, _ = _make_test_app()
    r = client.get(f"{_LOG_BASE}/entries?start=0&end=2")
    assert r.status_code == 200
    data = r.json()
    assert len(data["entries"]) == 2
    # Both entries 0 and 1 are valid JSON objects
    assert data["entries"][0]["seq"] == 0
    assert data["entries"][1]["seq"] == 1


def test_read_api_entries_non_json_as_b64():
    client, _ = _make_test_app()
    # Request entry 2 only
    r = client.get(f"{_LOG_BASE}/entries?start=2&end=3")
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert len(entries) == 1
    entry = entries[0]
    assert "b64" in entry
    # Verify the base64 decodes back to the original bytes
    assert base64.b64decode(entry["b64"]) == b"\x00\xff\xfe"


def test_read_api_entries_invalid_range_400():
    client, _ = _make_test_app()
    # start > end is invalid
    r = client.get(f"{_LOG_BASE}/entries?start=5&end=1")
    assert r.status_code == 400


def test_read_api_entries_beyond_tree_size_400():
    client, _ = _make_test_app()
    # end beyond tree_size (3) is invalid
    r = client.get(f"{_LOG_BASE}/entries?start=0&end=9999")
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# /api/v1/log/proof/inclusion/{leaf_index}
# ---------------------------------------------------------------------------


def test_read_api_inclusion_proof_200():
    client, _ = _make_test_app()
    r = client.get(f"{_LOG_BASE}/proof/inclusion/0")
    assert r.status_code == 200
    data = r.json()
    for key in ("leaf_index", "tree_size", "audit_path"):
        assert key in data, f"missing key: {key}"
    assert data["leaf_index"] == 0
    assert data["tree_size"] == 3
    assert isinstance(data["audit_path"], list)


def test_read_api_inclusion_proof_404():
    client, _ = _make_test_app()
    r = client.get(f"{_LOG_BASE}/proof/inclusion/9999")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 503 when no log available
# ---------------------------------------------------------------------------


def test_read_api_no_log_503():
    client = _make_app_no_log()

    r_tree = client.get(f"{_LOG_BASE}/tree")
    assert r_tree.status_code == 503

    r_entries = client.get(f"{_LOG_BASE}/entries?start=0&end=1")
    assert r_entries.status_code == 503

    r_proof = client.get(f"{_LOG_BASE}/proof/inclusion/0")
    assert r_proof.status_code == 503
