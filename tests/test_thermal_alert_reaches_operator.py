"""El aviso térmico tiene que LLEGAR, y hoy no llegaba a nadie.

Rastreado el 2026-08-09:

    ThermalWatchdog -> alert_callback -> publica THERMAL_ALERT en el bus
    -> el bus SÓLO se conecta al bot dentro de `_wire_bus_to_bot(bot)`
    -> que únicamente se llama si el bot de Telegram arrancó
    -> y Telegram está desactivado (ATLAS_DISABLE_TELEGRAM=1,
       4.967 `telegram.skip` sólo en agosto)

El evento se publicaba a un bus sin suscriptores. Los 81-83 °C medidos —25
transiciones en dos días— quedaban en el ledger Merkle, que nadie lee en tiempo
real.

Importa porque el operador lo dijo: en verano a veces se le olvida conectar el
ventilador de apoyo. Es un riesgo de hardware con un modo de fallo humano
conocido y un canal de aviso muerto.

`notify-send` existe en el sistema y el operador está sentado delante del
portátil. Ése es el canal, y es independiente de Telegram a propósito: la
arquitectura twin puede apagar Telegram cuando quiera y el aviso local debe
sobrevivir a esa decisión.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atlas.thermal.desktop_alert import (
    DesktopNotifier,
    thermal_alert_message,
)


class _FakeRun:
    def __init__(self, raises: Exception | None = None) -> None:
        self.calls: list[list[str]] = []
        self.raises = raises

    def __call__(self, cmd: list[str], **kw: Any) -> Any:
        self.calls.append(cmd)
        if self.raises:
            raise self.raises

        class _R:
            returncode = 0
        return _R()


def _state(temp: float = 82.0, mode: str = "degraded", emergency: bool = False) -> Any:
    from types import SimpleNamespace

    from atlas.core.contracts import OperationalMode

    return SimpleNamespace(
        temperature_celsius=temp,
        ram_free_mb=8000,
        operational_mode=OperationalMode(mode),
        policy=f"{mode.upper()}: {temp}C",
        emergency=emergency,
        should_pause_local_llm=True,
    )


# --------------------------------------------------------------------------
# El canal
# --------------------------------------------------------------------------


def test_notifica_de_verdad_por_notify_send() -> None:
    run = _FakeRun()
    DesktopNotifier(runner=run).notify(_state())

    assert run.calls, "no se invocó ningún notificador"
    assert "notify-send" in run.calls[0][0]


def test_el_mensaje_lleva_la_temperatura() -> None:
    """Un aviso que no dice el número obliga a ir a mirarlo."""
    msg = thermal_alert_message(_state(temp=83.0))

    assert "83" in msg


def test_una_emergencia_se_marca_como_critica() -> None:
    """`notify-send -u critical` no se auto-descarta: para 90 °C eso importa."""
    run = _FakeRun()
    DesktopNotifier(runner=run).notify(_state(temp=91.0, mode="omega", emergency=True))

    assert "critical" in " ".join(run.calls[0])


def test_un_estado_normal_no_es_critico() -> None:
    run = _FakeRun()
    DesktopNotifier(runner=run).notify(_state(temp=60.0, mode="normal"))

    assert "critical" not in " ".join(run.calls[0])


def test_si_no_hay_notify_send_no_revienta() -> None:
    """En un servidor sin escritorio esto no puede tumbar el termostato."""
    DesktopNotifier(runner=_FakeRun(raises=FileNotFoundError("notify-send"))).notify(
        _state()
    )


def test_no_depende_de_telegram(monkeypatch: pytest.MonkeyPatch) -> None:
    """La razón de existir: Telegram está desactivado y el aviso debe llegar."""
    monkeypatch.setenv("ATLAS_DISABLE_TELEGRAM", "1")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    run = _FakeRun()

    DesktopNotifier(runner=run).notify(_state())

    assert run.calls


def test_se_puede_desactivar(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin escape explícito, un headless llenaría los logs de intentos."""
    monkeypatch.setenv("ATLAS_DISABLE_DESKTOP_ALERTS", "1")
    run = _FakeRun()

    DesktopNotifier(runner=run).notify(_state())

    assert run.calls == []


# --------------------------------------------------------------------------
# Cableado: el fallo original era exactamente que nadie lo suscribía
# --------------------------------------------------------------------------


def test_el_orquestador_suscribe_el_aviso_de_escritorio() -> None:
    """Un notificador que existe y nadie conecta es el bug que este módulo
    corrige, no una versión nueva de él."""
    from atlas.core.orchestrator_parts import maintenance_facade  # noqa: F401
    from atlas.core import orchestrator as orch_mod

    source = Path(str(orch_mod.__file__)).read_text(encoding="utf-8")
    assert "DesktopNotifier" in source
    assert "THERMAL_ALERT" in source


def test_la_suscripcion_no_vive_dentro_de_wire_bus_to_bot() -> None:
    """El bug original: la única suscripción a THERMAL_ALERT estaba dentro de
    `_wire_bus_to_bot`, que sólo corre si Telegram arrancó. La nueva no puede
    heredar esa dependencia."""
    from atlas.core import orchestrator as orch_mod

    source = Path(str(orch_mod.__file__)).read_text(encoding="utf-8")
    bloque = source.split("def _wire_bus_to_bot")[1].split("\n    def ")[0]

    assert "DesktopNotifier" not in bloque
