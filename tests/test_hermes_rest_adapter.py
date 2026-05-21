"""
Tests para HermesRestAdapter — Gate C / C3.
Servidor HTTP local en thread para verificar protocolo, firma HMAC, retry y
fallback a OfflineQueue.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from atlas.hermes.hermes import (
    DelegationBuilder,
    HermesAuthError,
    HermesBadResponse,
    HermesMockAdapter,
    HermesRestAdapter,
    HermesUnreachable,
    OfflineQueue,
)


SECRET = "atlas-rest-test-secret"


# ---------------------------------------------------------------------------
# Servidor mock controlable por test
# ---------------------------------------------------------------------------

class _MockState:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.script: list[tuple[int, dict | None]] = []  # (status, body) por request
        self.default = (200, {})
        self.lock = threading.Lock()

    def next_response(self) -> tuple[int, dict | None]:
        with self.lock:
            if self.script:
                return self.script.pop(0)
            return self.default


def _make_handler(state: _MockState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_a, **_k):  # silenciar
            pass

        def _record_and_reply(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            state.requests.append({
                "method": self.command,
                "path": self.path,
                "headers": dict(self.headers),
                "body": body,
            })
            status, payload = state.next_response()
            self.send_response(status)
            if payload is None:
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            raw = json.dumps(payload).encode("utf-8")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        do_GET = _record_and_reply
        do_POST = _record_and_reply
        do_DELETE = _record_and_reply

    return Handler


@pytest.fixture
def mock_server():
    state = _MockState()
    server = HTTPServer(("127.0.0.1", 0), _make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
    try:
        yield base_url, state
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_constructor_validates_args():
    with pytest.raises(ValueError):
        HermesRestAdapter(base_url="", shared_secret="x")
    with pytest.raises(ValueError):
        HermesRestAdapter(base_url="http://h", shared_secret="")


def test_health_check_ok(mock_server):
    base_url, state = mock_server
    state.script.append((200, {
        "reachable": True, "mode": "live", "queue_depth": 2,
        "last_seen": "2026-01-01T00:00:00Z", "version": "0.2.0",
    }))
    adapter = HermesRestAdapter(base_url=base_url, shared_secret=SECRET, max_retries=1)
    status = adapter.health_check()
    assert status.reachable is True
    assert status.mode == "live"
    assert status.queue_depth == 2
    assert status.version == "0.2.0"


def test_health_check_network_error_returns_offline():
    adapter = HermesRestAdapter(
        base_url="http://127.0.0.1:1",  # puerto cerrado
        shared_secret=SECRET, max_retries=2, backoff_base_s=0,
    )
    status = adapter.health_check()
    assert status.reachable is False
    assert status.mode == "offline"


def test_signature_headers_are_present_and_correct(mock_server):
    base_url, state = mock_server
    state.default = (200, {"depth": 0, "oldest_task_age_seconds": None,
                           "next_task_id": None, "processing": False})
    adapter = HermesRestAdapter(base_url=base_url, shared_secret=SECRET, max_retries=1)
    adapter.get_queue_status()
    assert len(state.requests) == 1
    req = state.requests[0]
    ts = req["headers"]["X-Atlas-Timestamp"]
    sig = req["headers"]["X-Atlas-Signature"]
    expected = hmac.new(
        SECRET.encode(), ts.encode() + b"\n" + req["body"], hashlib.sha256,
    ).hexdigest()
    assert hmac.compare_digest(sig, expected)
    # ±5s del tiempo actual
    assert abs(int(ts) - int(time.time())) < 5


def test_enqueue_task_signs_payload_and_returns_receipt(mock_server):
    base_url, state = mock_server
    state.script.append((200, {
        "delegation_id": "to-be-overwritten", "accepted": True,
        "queue_position": 1, "estimated_eta_seconds": 30,
    }))
    adapter = HermesRestAdapter(base_url=base_url, shared_secret=SECRET, max_retries=1)
    payload = DelegationBuilder.build(task_id="t-1", intent="echo hello", priority=2)
    receipt = adapter.enqueue_task(payload)
    assert receipt.accepted is True
    assert receipt.queue_position == 1

    # Verificar que el body enviado lleva un payload firmado (signature no vacia)
    sent_body = json.loads(state.requests[0]["body"].decode("utf-8"))
    assert sent_body["signature"] != ""
    # Y que esa firma es valida segun el mismo algoritmo del mock (interop)
    mock = HermesMockAdapter(simulated_latency_ms=0, shared_secret=SECRET)
    from atlas.core.contracts import DelegationPayload
    rebuilt = DelegationPayload(**sent_body)
    assert mock.verify_signature(rebuilt) is True


def test_enqueue_task_retries_then_succeeds(mock_server):
    base_url, state = mock_server
    state.script.append((503, {"error": "busy"}))
    state.script.append((200, {
        "delegation_id": "id-1", "accepted": True,
        "queue_position": 1, "estimated_eta_seconds": 30,
    }))
    adapter = HermesRestAdapter(
        base_url=base_url, shared_secret=SECRET, max_retries=3, backoff_base_s=0,
    )
    payload = DelegationBuilder.build(task_id="t-retry", intent="x", priority=1)
    receipt = adapter.enqueue_task(payload)
    assert receipt.accepted is True
    assert len(state.requests) == 2


def test_enqueue_task_unreachable_drops_into_offline_queue(tmp_path):
    queue = OfflineQueue(store_path=tmp_path)
    adapter = HermesRestAdapter(
        base_url="http://127.0.0.1:1",  # puerto cerrado
        shared_secret=SECRET,
        offline_queue=queue,
        max_retries=2,
        backoff_base_s=0,
    )
    payload = DelegationBuilder.build(task_id="t-off", intent="x", priority=3)
    with pytest.raises(HermesUnreachable):
        adapter.enqueue_task(payload)
    assert queue.depth == 1
    pending = queue.all_pending()
    assert pending[0].delegation.task_id == "t-off"
    assert pending[0].delegation.signature != ""


def test_auth_error_is_raised_on_401(mock_server):
    base_url, state = mock_server
    state.default = (401, {"error": "bad signature"})
    adapter = HermesRestAdapter(base_url=base_url, shared_secret=SECRET, max_retries=1)
    with pytest.raises(HermesAuthError):
        adapter.get_queue_status()


def test_get_task_result_returns_none_on_404(mock_server):
    base_url, state = mock_server
    state.default = (404, {"error": "not found"})
    adapter = HermesRestAdapter(base_url=base_url, shared_secret=SECRET, max_retries=1)
    assert adapter.get_task_result("missing-id") is None


def test_get_task_result_returns_result_on_200(mock_server):
    base_url, state = mock_server
    state.script.append((200, {
        "delegation_id": "d-1", "task_id": "t-1", "status": "completed",
        "result": {"stdout": "ok"}, "skill_generated": False,
    }))
    adapter = HermesRestAdapter(base_url=base_url, shared_secret=SECRET, max_retries=1)
    result = adapter.get_task_result("t-1")
    assert result is not None
    assert result.status == "completed"
    assert result.result == {"stdout": "ok"}


def test_cancel_task_true_and_false(mock_server):
    base_url, state = mock_server
    state.script.append((204, None))
    state.script.append((404, {"error": "no"}))
    adapter = HermesRestAdapter(base_url=base_url, shared_secret=SECRET, max_retries=1)
    assert adapter.cancel_task("present") is True
    assert adapter.cancel_task("absent") is False
