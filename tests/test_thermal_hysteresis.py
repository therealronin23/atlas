"""El termostato conmutaba de modo 25 veces en dos días.

Medido el 2026-08-09 sobre el ledger: 50 `service.alert`, que son 25
transiciones degraded↔normal. Sube a 81-83 °C y degrada; baja a 72-79 y vuelve
a normal; repetir. Sin histéresis, cruzar el umbral conmuta al instante, y cada
conmutación cambia el modo operativo — la invariante 5 prohíbe LLMs pesados en
DEGRADED, así que el sistema estaba encendiendo y apagando esa restricción doce
veces al día.

Y había una contradicción desde el primer commit: el docstring del módulo decía
`70-79C → DEGRADED` mientras `TEMP_DEGRADED_THRESHOLD = 80.0` y el código
comprobaba `>= 80`. Los datos siguen al código. Se conserva el 80 —es lo que ha
estado pasando de verdad, y bajarlo a 70 dejaría el portátil permanentemente
degradado, porque en trabajo normal ronda 72-79— y se corrige el texto.

Decisión del operador: respuesta GRADUADA, no un umbral. En verano a veces se
le olvida el ventilador de apoyo, así que hace falta un aviso ANTES de degradar.

    < 74      NORMAL
    74-79     NORMAL + aviso (no cambia el modo, sólo avisa)
    >= 80     DEGRADED
    vuelve a NORMAL sólo por debajo de 74   <- la histéresis
    >= 90     OMEGA / emergencia
"""

from __future__ import annotations

from typing import Any

import pytest

from atlas.core.contracts import OperationalMode
from atlas.thermal.watchdog import (
    TEMP_ADVISORY_THRESHOLD,
    TEMP_DEGRADED_THRESHOLD,
    TEMP_RECOVER_THRESHOLD,
    ThermalWatchdog,
)


def _wd(temp: float, ram_mb: int = 8000, prev: Any = None) -> Any:
    wd = ThermalWatchdog()
    wd._read_temperature = lambda: temp  # type: ignore[method-assign]
    wd._read_ram_free_mb = lambda: ram_mb  # type: ignore[method-assign]
    if prev is not None:
        wd._current_state = prev
    return wd


# --------------------------------------------------------------------------
# Histéresis
# --------------------------------------------------------------------------


def test_sube_a_degraded_en_80() -> None:
    assert _wd(80.0)._compute_state().operational_mode is OperationalMode.DEGRADED


def test_a_78_estando_ya_degradado_SIGUE_degradado() -> None:
    """El corazón del arreglo: 78 °C no devuelve a NORMAL si veníamos de
    DEGRADED. Sin esto, 25 conmutaciones en dos días."""
    previo = _wd(82.0)._compute_state()

    estado = _wd(78.0, prev=previo)._compute_state()

    assert estado.operational_mode is OperationalMode.DEGRADED


def test_vuelve_a_normal_por_debajo_del_umbral_de_recuperacion() -> None:
    previo = _wd(82.0)._compute_state()

    estado = _wd(TEMP_RECOVER_THRESHOLD - 1, prev=previo)._compute_state()

    assert estado.operational_mode is OperationalMode.NORMAL


def test_sin_historial_78_es_normal() -> None:
    """Arranque en frío a 78: no hay de dónde histerizar, y 78 < 80."""
    assert _wd(78.0)._compute_state().operational_mode is OperationalMode.NORMAL


def test_los_umbrales_dejan_banda_de_histeresis() -> None:
    assert TEMP_RECOVER_THRESHOLD < TEMP_DEGRADED_THRESHOLD


# --------------------------------------------------------------------------
# Banda de aviso: el ventilador olvidado
# --------------------------------------------------------------------------


def test_a_76_avisa_sin_degradar() -> None:
    """La banda que existe por el ventilador de apoyo: avisa ANTES de que el
    sistema tenga que restringirse."""
    estado = _wd(76.0)._compute_state()

    assert estado.operational_mode is OperationalMode.NORMAL
    assert estado.advisory is True


def test_a_60_ni_avisa() -> None:
    estado = _wd(60.0)._compute_state()

    assert estado.advisory is False


def test_el_umbral_de_aviso_va_por_debajo_del_de_degradacion() -> None:
    assert TEMP_ADVISORY_THRESHOLD < TEMP_DEGRADED_THRESHOLD


# --------------------------------------------------------------------------
# Lo que NO puede romperse
# --------------------------------------------------------------------------


def test_omega_sigue_siendo_omega() -> None:
    estado = _wd(91.0)._compute_state()

    assert estado.operational_mode is OperationalMode.OMEGA
    assert estado.emergency is True


def test_la_histeresis_no_atrapa_en_degraded_una_emergencia() -> None:
    """Subir a 91 desde DEGRADED tiene que escalar, no quedarse."""
    previo = _wd(82.0)._compute_state()

    assert _wd(91.0, prev=previo)._compute_state().operational_mode is OperationalMode.OMEGA


def test_la_ram_baja_sigue_degradando_sin_calor() -> None:
    """RAM y temperatura son causas independientes; la histéresis térmica no
    puede tapar la presión de memoria."""
    estado = _wd(50.0, ram_mb=100)._compute_state()

    assert estado.operational_mode is OperationalMode.DEGRADED


def test_entrar_en_la_banda_de_aviso_DISPARA_el_callback() -> None:
    """Sin esto, la banda de aviso no serviría de nada: el callback sólo saltaba
    al cambiar de MODO, y la banda de aviso no cambia el modo a propósito. El
    diseño se anulaba a sí mismo."""
    import threading

    avisos: list[Any] = []
    wd = ThermalWatchdog(alert_callback=avisos.append, poll_interval_seconds=0)
    temps = iter([60.0, 76.0, 76.0])
    wd._read_temperature = lambda: next(temps, 76.0)  # type: ignore[method-assign]
    wd._read_ram_free_mb = lambda: 8000  # type: ignore[method-assign]

    wd._running = True
    hilo = threading.Thread(target=wd._loop, daemon=True)
    hilo.start()
    try:
        for _ in range(200):
            if avisos:
                break
            import time as _t

            _t.sleep(0.01)
    finally:
        wd._running = False
        hilo.join(timeout=2)

    assert avisos, "entrar en la banda de aviso no notificó"
    assert avisos[0].advisory is True


def test_no_avisa_en_cada_pasada_dentro_de_la_banda() -> None:
    """Sólo en la TRANSICIÓN. Repetir a cada sondeo serían decenas de
    notificaciones por hora y enseñaría a ignorarlas."""
    import threading
    import time as _t

    avisos: list[Any] = []
    wd = ThermalWatchdog(alert_callback=avisos.append, poll_interval_seconds=0)
    wd._read_temperature = lambda: 76.0  # type: ignore[method-assign]
    wd._read_ram_free_mb = lambda: 8000  # type: ignore[method-assign]

    wd._running = True
    hilo = threading.Thread(target=wd._loop, daemon=True)
    hilo.start()
    _t.sleep(0.25)
    wd._running = False
    hilo.join(timeout=2)

    assert len(avisos) <= 1


def test_el_docstring_ya_no_contradice_a_la_constante() -> None:
    """La contradicción original: el texto decía 70-79 y la constante 80."""
    import atlas.thermal.watchdog as mod

    doc = mod.__doc__ or ""
    assert "70-79C  → DEGRADED" not in doc
    assert str(int(TEMP_DEGRADED_THRESHOLD)) in doc
