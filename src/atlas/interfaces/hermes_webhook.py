"""
Atlas Core — Hermes Webhook Handler (Item 2, post-audit).

Reemplaza el polling de OfflineMonitor con un endpoint event-driven.
Hermes-VPS hace POST a /api/hermes/webhook cuando detecta cambios de estado.

HMAC-SHA256 verification. Publica eventos al EventBus.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from atlas.core.contracts import EventType
from atlas.core.event_bus import EventBus

_log = logging.getLogger(__name__)


class HermesWebhookHandler:
    """
    Webhook endpoint para eventos de Hermes-VPS.

    Recibe POST con payload JSON firmado con HMAC-SHA256.
    Verifica firma, parsea evento y publica al EventBus.

    Uso:
        handler = HermesWebhookHandler(bus, hmac_key="...")
        app.include_router(handler.router)
    """

    def __init__(self, bus: EventBus, hmac_key: str) -> None:
        self._bus = bus
        self._hmac_key = hmac_key.encode("utf-8") if isinstance(hmac_key, str) else hmac_key
        self.router = APIRouter(prefix="/api/hermes")
        self._setup_routes()

    def _setup_routes(self) -> None:
        @self.router.post("/webhook")
        async def webhook_event(request: Request) -> dict[str, str]:
            body = await request.body()
            if not body:
                raise HTTPException(status_code=400, detail="Empty body")

            # Parse JSON
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid JSON")

            if not isinstance(payload, dict):
                raise HTTPException(status_code=400, detail="Payload must be JSON object")

            # Extract and verify HMAC signature
            # NOTE: the client signs the body WITHOUT the "signature" field, then
            # embeds the sig in the same JSON. We pop the sig first and re-serialize
            # the cleaned dict so we verify the same bytes the client originally signed.
            signature = payload.pop("signature", None)
            if not signature:
                _log.warning("Webhook recibido sin signature")
                raise HTTPException(status_code=401, detail="Missing HMAC signature")

            # Verify against canonical body (no "signature" field, same key order)
            canonical_body = json.dumps(payload).encode("utf-8")
            if not self._verify_signature(canonical_body, signature):
                _log.warning("Webhook HMAC signature inválida")
                raise HTTPException(status_code=401, detail="Invalid HMAC signature")

            # Validate event_type
            event_type = payload.get("event_type")
            if event_type not in ("online", "offline"):
                _log.warning(f"Webhook event_type desconocido: {event_type}")
                raise HTTPException(status_code=400, detail=f"Unknown event_type: {event_type}")

            timestamp = payload.get("timestamp", datetime.now(timezone.utc).isoformat())
            elapsed = payload.get("elapsed_minutes", 0)

            _log.info(f"Hermes webhook recibido: {event_type} (elapsed={elapsed}m)")

            # Publish to EventBus
            if event_type == "offline":
                self._bus.publish_type(
                    EventType.SHADOW_ALERT,
                    payload={
                        "elapsed_minutes": elapsed,
                        "timestamp": timestamp,
                        "source": "hermes_webhook",
                    },
                    producer="hermes_webhook",
                )
            elif event_type == "online":
                self._bus.publish_type(
                    EventType.HERMES_ONLINE_CONFIRMED,
                    payload={
                        "source": "hermes_webhook",
                        "timestamp": timestamp,
                        "note": "Hermes pushed online event via webhook",
                    },
                    producer="hermes_webhook",
                )
                # Also trigger HERMES_RECONNECTED for backwards compat
                self._bus.publish_type(
                    EventType.HERMES_RECONNECTED,
                    payload={
                        "source": "hermes_webhook",
                        "note": "Triggered by webhook online event",
                    },
                    producer="hermes_webhook",
                )

            # Publish generic webhook received event
            self._bus.publish_type(
                EventType.HERMES_WEBHOOK_RECEIVED,
                payload={"event_type": event_type, "timestamp": timestamp},
                producer="hermes_webhook",
            )

            return {"status": "received", "event_type": event_type}

    def _verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify HMAC-SHA256 signature from Hermes payload (raw bytes)."""
        expected = hmac.new(
            self._hmac_key,
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Public wrapper for testing."""
        return self._verify_signature(payload, signature)