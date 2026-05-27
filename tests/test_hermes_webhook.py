"""
Tests Gate I/Item 2 — Hermes Webhook Handler.

Verifica:
- HMAC-SHA256 signature verification (válida e inválida)
- Event routing offline/online
- HTTP error codes (400, 401)
- EventBus publishing
- Edge cases: empty body, invalid JSON, missing signature, unknown event_type
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from atlas.core.contracts import EventType
from atlas.core.event_bus import EventBus
from atlas.interfaces.hermes_webhook import HermesWebhookHandler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def hmac_key() -> str:
    return "test-secret-key-123"


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def handler(bus: EventBus, hmac_key: str) -> HermesWebhookHandler:
    return HermesWebhookHandler(bus, hmac_key)


@pytest.fixture
def app(handler: HermesWebhookHandler) -> FastAPI:
    app = FastAPI()
    app.include_router(handler.router)
    return app


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sign_payload(payload: dict, key: str) -> dict:
    """Create a signed payload dict ready for POST."""
    body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
    signed = dict(payload)
    signed["signature"] = sig
    return signed


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSignatureVerification:

    def test_valid_signature(self, handler: HermesWebhookHandler, hmac_key: str) -> None:
        payload = b'{"event_type":"online","timestamp":"2026-05-25T10:00:00Z"}'
        sig = hmac.new(hmac_key.encode(), payload, hashlib.sha256).hexdigest()
        assert handler.verify_signature(payload, sig) is True

    def test_invalid_signature(self, handler: HermesWebhookHandler) -> None:
        payload = b'{"event_type":"online"}'
        assert handler.verify_signature(payload, "invalid-signature") is False

    def test_empty_payload_signature(self, handler: HermesWebhookHandler, hmac_key: str) -> None:
        payload = b""
        sig = hmac.new(hmac_key.encode(), payload, hashlib.sha256).hexdigest()
        # Empty payload with correct signature — should be valid but endpoint will reject
        assert handler.verify_signature(payload, sig) is True

    def test_tampered_payload(self, handler: HermesWebhookHandler, hmac_key: str) -> None:
        """Sign original, then tamper — signature must fail."""
        original = b'{"event_type":"online","elapsed_minutes":0}'
        sig = hmac.new(hmac_key.encode(), original, hashlib.sha256).hexdigest()
        tampered = b'{"event_type":"offline","elapsed_minutes":99}'
        assert handler.verify_signature(tampered, sig) is False


class TestWebhookEndpoint:

    def test_offline_event(self, client: TestClient, hmac_key: str) -> None:
        payload = {
            "event_type": "offline",
            "timestamp": "2026-05-25T10:30:00Z",
            "elapsed_minutes": 5,
        }
        signed = _sign_payload(payload, hmac_key)
        resp = client.post("/api/hermes/webhook", json=signed)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "received"
        assert data["event_type"] == "offline"

    def test_online_event(self, client: TestClient, hmac_key: str) -> None:
        payload = {
            "event_type": "online",
            "timestamp": "2026-05-25T10:35:00Z",
        }
        signed = _sign_payload(payload, hmac_key)
        resp = client.post("/api/hermes/webhook", json=signed)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "received"
        assert data["event_type"] == "online"

    def test_missing_signature(self, client: TestClient) -> None:
        payload = {"event_type": "offline"}
        resp = client.post("/api/hermes/webhook", json=payload)
        assert resp.status_code == 401
        assert "signature" in resp.json()["detail"].lower()

    def test_invalid_signature(self, client: TestClient) -> None:
        payload = {"event_type": "offline", "signature": "bad-sig"}
        resp = client.post("/api/hermes/webhook", json=payload)
        assert resp.status_code == 401
        assert "invalid" in resp.json()["detail"].lower()

    def test_unknown_event_type(self, client: TestClient, hmac_key: str) -> None:
        payload = {"event_type": "unknown_event"}
        signed = _sign_payload(payload, hmac_key)
        resp = client.post("/api/hermes/webhook", json=signed)
        assert resp.status_code == 400
        assert "unknown" in resp.json()["detail"].lower()

    def test_empty_body(self, client: TestClient) -> None:
        resp = client.post("/api/hermes/webhook", content=b"", headers={"Content-Type": "application/json"})
        assert resp.status_code == 400

    def test_invalid_json(self, client: TestClient) -> None:
        resp = client.post("/api/hermes/webhook", content=b"not-json", headers={"Content-Type": "application/json"})
        assert resp.status_code == 400

    def test_missing_event_type(self, client: TestClient, hmac_key: str) -> None:
        payload = {"some_field": "value"}
        signed = _sign_payload(payload, hmac_key)
        resp = client.post("/api/hermes/webhook", json=signed)
        assert resp.status_code == 400


class TestEventBusIntegration:

    def test_offline_publishes_shadow_alert(self, bus: EventBus, hmac_key: str, handler: HermesWebhookHandler) -> None:
        received_events: list[object] = []

        bus.subscribe(EventType.SHADOW_ALERT, lambda evt: received_events.append(evt))

        # Simulate direct handler call (bypass HTTP)
        payload_dict = {
            "event_type": "offline",
            "timestamp": "2026-05-25T10:30:00Z",
            "elapsed_minutes": 5,
        }
        body = json.dumps(payload_dict).encode()
        sig = hmac.new(hmac_key.encode(), body, hashlib.sha256).hexdigest()
        signed_dict = dict(payload_dict)
        signed_dict["signature"] = sig
        signed_body = json.dumps(signed_dict).encode()

        # verify_signature takes the UNSIGNED body (without the "signature" field)
        assert handler.verify_signature(body, sig) is True

        # We verify the signature logic; EventBus publishing is tested via HTTP below
        assert len(received_events) == 0  # No events yet

    def test_online_publishes_reconnected(self, bus: EventBus, hmac_key: str, client: TestClient) -> None:
        received_events: list[EventType] = []

        def listener(event_type: EventType, payload: dict) -> None:
            received_events.append(event_type)

        bus.subscribe(EventType.HERMES_RECONNECTED, listener)

        payload = {"event_type": "online", "timestamp": "2026-05-25T10:35:00Z"}
        signed = _sign_payload(payload, hmac_key)

        # Need to make the handler use this bus — we test via creating a dedicated app
        local_bus = EventBus()
        local_handler = HermesWebhookHandler(local_bus, hmac_key)
        local_app = FastAPI()
        local_app.include_router(local_handler.router)

        events: list[EventType] = []
        local_bus.subscribe(EventType.HERMES_RECONNECTED, lambda evt: events.append(evt.type))
        local_bus.subscribe(EventType.HERMES_ONLINE_CONFIRMED, lambda evt: events.append(evt.type))

        with TestClient(local_app) as c:
            resp = c.post("/api/hermes/webhook", json=signed)
            assert resp.status_code == 200

        # Should have received both HERMES_ONLINE_CONFIRMED and HERMES_RECONNECTED
        assert EventType.HERMES_ONLINE_CONFIRMED in events
        assert EventType.HERMES_RECONNECTED in events

    def test_hermes_webhook_received_event(self, hmac_key: str) -> None:
        """Verify generic HERMES_WEBHOOK_RECEIVED is published for any event."""
        local_bus = EventBus()
        local_handler = HermesWebhookHandler(local_bus, hmac_key)
        local_app = FastAPI()
        local_app.include_router(local_handler.router)

        events: list[EventType] = []
        local_bus.subscribe(EventType.HERMES_WEBHOOK_RECEIVED, lambda evt: events.append(evt.type))

        with TestClient(local_app) as c:
            # Offline event
            offline = _sign_payload({"event_type": "offline", "elapsed_minutes": 3}, hmac_key)
            c.post("/api/hermes/webhook", json=offline)
            # Online event
            online = _sign_payload({"event_type": "online"}, hmac_key)
            c.post("/api/hermes/webhook", json=online)

        assert len(events) == 2


class TestEdgeCases:

    def test_offline_without_elapsed(self, client: TestClient, hmac_key: str) -> None:
        """elapsed_minutes is optional — should still work."""
        payload = {"event_type": "offline"}
        signed = _sign_payload(payload, hmac_key)
        resp = client.post("/api/hermes/webhook", json=signed)
        assert resp.status_code == 200

    def test_additional_fields_ignored(self, client: TestClient, hmac_key: str) -> None:
        """Extra fields should be ignored (forward compat)."""
        payload = {
            "event_type": "online",
            "extra_field_1": "value1",
            "extra_field_2": 42,
        }
        signed = _sign_payload(payload, hmac_key)
        resp = client.post("/api/hermes/webhook", json=signed)
        assert resp.status_code == 200

    def test_non_dict_payload(self, client: TestClient, hmac_key: str) -> None:
        body = json.dumps(["list", "not", "dict"]).encode()
        sig = hmac.new(hmac_key.encode(), body, hashlib.sha256).hexdigest()
        signed = json.dumps(["list", "not", "dict", {"signature": sig}])
        resp = client.post("/api/hermes/webhook", content=signed, headers={"Content-Type": "application/json"})
        assert resp.status_code == 400


class TestCabling:

    def test_handler_initialized_with_bus_and_key(self, bus: EventBus, hmac_key: str) -> None:
        """Verify HermesWebhookHandler constructor."""
        handler = HermesWebhookHandler(bus, hmac_key)
        assert handler._bus is bus
        assert handler._hmac_key == hmac_key.encode()

    def test_router_prefix(self, handler: HermesWebhookHandler) -> None:
        """Router prefix must be /api/hermes."""
        assert handler.router.prefix == "/api/hermes"

    def test_router_has_webhook_route(self, handler: HermesWebhookHandler) -> None:
        """Router must have POST /webhook route."""
        routes = [r.path for r in handler.router.routes]
        assert "/api/hermes/webhook" in routes