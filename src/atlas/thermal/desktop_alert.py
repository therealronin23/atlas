"""Aviso térmico al escritorio, independiente de Telegram.

El 2026-08-09 se rastreó la cadena completa del aviso térmico y terminaba en
nada:

    ThermalWatchdog -> alert_callback -> publica THERMAL_ALERT en el bus
    -> el bus SÓLO se conectaba al bot dentro de `_wire_bus_to_bot(bot)`
    -> que únicamente se llama si el bot de Telegram arrancó
    -> y Telegram está desactivado (ATLAS_DISABLE_TELEGRAM=1, arquitectura twin)

El evento se publicaba a un bus sin suscriptores. Las 25 transiciones de modo
medidas en dos días, con picos de 81-83 °C, quedaban sólo en el ledger Merkle
— que nadie lee en tiempo real.

Importa por un motivo concreto que dio el operador: en verano a veces se le
olvida conectar el ventilador de apoyo. Es un riesgo de hardware con un modo de
fallo humano conocido y sin canal de aviso.

Este módulo es ese canal. **Independiente de Telegram a propósito**: la
arquitectura twin puede apagarlo cuando quiera, y el aviso local tiene que
sobrevivir a esa decisión. Mejor esfuerzo en todo: un escritorio ausente
(servidor, sesión sin D-Bus) no puede tumbar el termostato.
"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable
from typing import Any

__all__ = ["DesktopNotifier", "thermal_alert_message"]

logger = logging.getLogger(__name__)

_NOTIFY_TIMEOUT_S = 5.0


def thermal_alert_message(state: Any) -> str:
    """Texto del aviso. Lleva el NÚMERO: un aviso sin temperatura obliga a ir
    a buscarla, que es justo lo que no va a pasar a las 3 de la mañana."""
    temp = getattr(state, "temperature_celsius", 0.0)
    ram = getattr(state, "ram_free_mb", 0)
    mode = getattr(getattr(state, "operational_mode", None), "value", "?")
    texto = f"{temp:.0f} °C · {ram} MB libres · modo {mode}"
    if getattr(state, "emergency", False):
        return f"EMERGENCIA TÉRMICA — {texto}"
    return f"Atlas: tensión térmica — {texto}"


class DesktopNotifier:
    """Notificación de escritorio vía `notify-send`."""

    def __init__(self, *, runner: Callable[..., Any] | None = None) -> None:
        self._run = runner or subprocess.run

    def notify(self, state: Any) -> None:
        """Nunca lanza: un fallo del canal de aviso no puede propagarse al
        termostato, que es lo único que protege el hardware."""
        if os.environ.get("ATLAS_DISABLE_DESKTOP_ALERTS", "").strip() == "1":
            return
        emergencia = bool(getattr(state, "emergency", False))
        # `critical` no se auto-descarta: para >=90 °C eso es justo lo que hace
        # falta. Para una degradación normal sería ruido que enseña a ignorar.
        urgencia = "critical" if emergencia else "normal"
        try:
            self._run(
                [
                    "notify-send",
                    "--app-name=Atlas",
                    f"--urgency={urgencia}",
                    "Atlas — térmico",
                    thermal_alert_message(state),
                ],
                capture_output=True,
                timeout=_NOTIFY_TIMEOUT_S,
                check=False,
            )
        except Exception as exc:  # noqa: BLE001 — sin escritorio no hay aviso, y ya
            logger.debug("notify-send no disponible: %s", exc)
