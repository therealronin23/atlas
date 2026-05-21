"""
Atlas Core — OfflineMonitor.

Polleo periodico de HermesAdapter.check_offline_fallback(). En la transicion
False -> True publica EventType.SHADOW_ALERT en el EventBus. Los suscriptores
(p.ej. TelegramBot.on_shadow_alert) deciden como notificar.

Gate D sustituira este polling local por una alerta empujada desde el VPS de
Hermes (webhook o callback). Por ahora, el mock vive en el mismo proceso y el
monitor lee su estado.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from atlas.core.contracts import EventType


class OfflineMonitor:
    def __init__(
        self,
        hermes: Any,
        bus: Any,
        poll_interval_seconds: int = 60,
    ) -> None:
        self._hermes = hermes
        self._bus = bus
        self._poll_interval = poll_interval_seconds
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_state: bool = False

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="atlas-offline-monitor",
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while self._running:
            try:
                self.tick()
            except Exception:
                pass
            time.sleep(self._poll_interval)

    def tick(self) -> bool:
        """Comprueba el estado una vez. Util para tests. Retorna el estado actual."""
        current = bool(self._hermes.check_offline_fallback())
        if current and not self._last_state:
            self._bus.publish_type(EventType.SHADOW_ALERT, {
                "elapsed_minutes": getattr(self._hermes, "SHADOW_TIMEOUT_MINUTES", None),
            })
        self._last_state = current
        return current
