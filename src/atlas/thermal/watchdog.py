"""
Atlas Core — Thermal Watchdog con Triage Alfa/Omega
Monitoriza temperatura y RAM. Activa modo degradado antes de throttling.
Critico para hardware limitado (HP Omen laptop, 16GB RAM).

Modos del chat de Gemini:
  NORMAL tier: Docker efimero sin red, 512MB RAM, bajo riesgo, velocidad.
  OMEGA (10% del tiempo): VM Proxmox + Snapshot + HITL via Telegram, alto riesgo.
  
Politica de respuesta escalonada (reconciliada 2026-08-09):
  < 74C    → NORMAL: sin restricciones
  74-79C   → NORMAL + AVISO: no cambia el modo, sólo notifica
  >= 80C   → DEGRADED: LLMs pesados pausados
  vuelve a NORMAL sólo por debajo de 74C  ← histéresis
  >= 90C   → OMEGA: sólo L-det + delegacion Hermes, emergencia

DOS ARREGLOS DE 2026-08-09, ambos medidos:

1. El docstring decía `70-79C → DEGRADED` mientras la constante era 80.0 y el
   código comprobaba `>= 80`. Llevaban contradiciéndose desde el primer commit.
   Manda el código: bajar a 70 dejaría el portátil permanentemente degradado
   (en trabajo normal ronda 72-79).

2. Sin histéresis, el termostato conmutaba 25 veces en dos días (50
   `service.alert` en el ledger): subía a 81-83 y degradaba, bajaba a 72-79 y
   volvía. Cada conmutación enciende y apaga la invariante 5 (sin LLMs pesados
   en DEGRADED). Ahora se sube en 80 y no se vuelve hasta por debajo de 74.

La BANDA DE AVISO existe por un motivo concreto del operador: en verano a veces
se le olvida conectar el ventilador de apoyo, así que hace falta avisar ANTES de
tener que restringir. El aviso sale por `thermal/desktop_alert.py`, que no
depende de Telegram.
"""

from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from atlas.core.contracts import OperationalMode


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

TEMP_NORMAL_THRESHOLD   = 70.0   # histórico; conservado por compatibilidad
TEMP_ADVISORY_THRESHOLD = 74.0   # >= 74C → avisa SIN cambiar de modo
TEMP_DEGRADED_THRESHOLD = 80.0   # >= 80C → DEGRADED: sin LLMs pesados
TEMP_RECOVER_THRESHOLD  = 74.0   # sólo se vuelve a NORMAL por debajo de esto
                                  # (histéresis: sin ella, 25 conmutaciones en
                                  # dos días medidas el 2026-08-09)
TEMP_OMEGA_THRESHOLD    = 90.0   # >= 90C → OMEGA: solo L-det + Hermes

RAM_DEGRADED_THRESHOLD_MB = 1024  # < 1GB libre → al menos DEGRADED


@dataclass
class ThermalState:
    temperature_celsius: float
    ram_free_mb: int
    operational_mode: OperationalMode
    policy: str                   # descripcion de la politica activa
    should_pause_local_llm: bool
    should_delegate_all: bool
    emergency: bool
    #: Banda de aviso: hay tensión térmica pero NO se cambia de modo. Existe por
    #: el ventilador de apoyo que a veces se queda sin conectar — avisar antes
    #: de tener que restringir.
    advisory: bool = False
    sampled_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ThermalWatchdog:
    """
    Monitoriza temperatura y RAM. Expone el modo de Triage actual.
    Si detecta condicion critica, notifica via callback (Telegram, CLI, etc.).
    Corre en un thread de fondo con muestreo cada N segundos.
    """

    def __init__(
        self,
        poll_interval_seconds: int = 30,
        alert_callback: Callable[[ThermalState], None] | None = None,
    ) -> None:
        self._poll_interval = poll_interval_seconds
        self._alert_callback = alert_callback
        self._current_state: ThermalState | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._hwmon_path: Path | None = self._autodiscover_hwmon()

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Arranca el thread de monitoreo en segundo plano."""
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="atlas-thermal")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def current_operational_mode(self) -> OperationalMode:
        """Retorna el modo de triage actual. NORMAL por defecto si aun no hay lectura."""
        with self._lock:
            if self._current_state is None:
                return OperationalMode.NORMAL
            return self._current_state.operational_mode

    def current_state(self) -> ThermalState:
        """Retorna el estado termico completo."""
        with self._lock:
            if self._current_state is None:
                return ThermalState(
                    temperature_celsius=0.0,
                    ram_free_mb=self._read_ram_free_mb(),
                    operational_mode=OperationalMode.NORMAL,
                    policy="Sin lectura termica aun. Modo NORMAL por defecto.",
                    should_pause_local_llm=False,
                    should_delegate_all=False,
                    emergency=False,
                )
            return self._current_state

    def sample_now(self) -> ThermalState:
        """Toma una muestra inmediata (bloqueante, util para CLI)."""
        state = self._compute_state()
        with self._lock:
            self._current_state = state
        return state

    # ------------------------------------------------------------------
    # Loop de monitoreo
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while self._running:
            state = self._compute_state()
            prev_mode = None
            prev_advisory = False
            with self._lock:
                if self._current_state:
                    prev_mode = self._current_state.operational_mode
                    prev_advisory = self._current_state.advisory
                self._current_state = state

            # Notificar si cambia el modo, hay emergencia, o se ENTRA en la
            # banda de aviso.
            #
            # Lo tercero no es un extra: la banda de aviso no cambia el modo a
            # propósito, así que sin esta condición no dispararía nunca y toda
            # su razón de ser —avisar del ventilador olvidado ANTES de degradar—
            # quedaría anulada. Sólo en la TRANSICIÓN a advisory, no en cada
            # pasada, o serían decenas de notificaciones por hora.
            if self._alert_callback and (
                state.emergency
                or (prev_mode is not None and prev_mode != state.operational_mode)
                or (state.advisory and not prev_advisory)
            ):
                try:
                    self._alert_callback(state)
                except Exception:
                    pass

            time.sleep(self._poll_interval)

    def _compute_state(self) -> ThermalState:
        temp = self._read_temperature()
        ram_free = self._read_ram_free_mb()

        # Tier 3 — OMEGA: emergencia real, parar todo lo no critico
        if temp >= TEMP_OMEGA_THRESHOLD:
            return ThermalState(
                temperature_celsius=temp,
                ram_free_mb=ram_free,
                operational_mode=OperationalMode.OMEGA,
                policy=(
                    f"OMEGA: {temp:.1f}C / {ram_free}MB RAM. "
                    "Solo L-det y delegacion a Hermes. Parar ejecucion no critica."
                ),
                should_pause_local_llm=True,
                should_delegate_all=True,
                emergency=True,
            )

        # Tier 2 — DEGRADED: tension termica o RAM baja, funciones criticas OK.
        #
        # HISTÉRESIS: si YA estábamos en DEGRADED, no se vuelve a NORMAL hasta
        # bajar de TEMP_RECOVER_THRESHOLD. Sin esto, oscilar alrededor de 80
        # producía 25 conmutaciones de modo en dos días, encendiendo y apagando
        # la invariante 5 (sin LLMs pesados en DEGRADED) doce veces al día.
        # La emergencia (Tier 3) se evalúa ANTES, así que esto no atrapa nunca
        # una escalada a OMEGA.
        venia_degradado = (
            self._current_state is not None
            and self._current_state.operational_mode is OperationalMode.DEGRADED
        )
        sigue_caliente = venia_degradado and temp >= TEMP_RECOVER_THRESHOLD
        if (
            temp >= TEMP_DEGRADED_THRESHOLD
            or ram_free < RAM_DEGRADED_THRESHOLD_MB
            or sigue_caliente
        ):
            return ThermalState(
                temperature_celsius=temp,
                ram_free_mb=ram_free,
                operational_mode=OperationalMode.DEGRADED,
                policy=(
                    f"DEGRADED: {temp:.1f}C / {ram_free}MB RAM. "
                    "LLMs pesados pausados. Funciones criticas activas."
                ),
                should_pause_local_llm=True,
                should_delegate_all=False,
                emergency=False,
            )

        # Tier 1 — NORMAL, con o sin aviso. La banda 74-79 NO cambia el modo:
        # sólo enciende `advisory` para que el aviso de escritorio salga ANTES
        # de que haya que restringir nada. Existe por el ventilador de apoyo que
        # a veces se queda sin conectar en verano.
        advisory = temp >= TEMP_ADVISORY_THRESHOLD
        politica = (
            f"NORMAL (aviso): {temp:.1f}C / {ram_free}MB RAM libre. "
            f"Tensión térmica por encima de {TEMP_ADVISORY_THRESHOLD:.0f}C; "
            "sin restricciones todavía. ¿Ventilador de apoyo conectado?"
            if advisory
            else f"NORMAL: {temp:.1f}C / {ram_free}MB RAM libre. Sin restricciones."
        )
        return ThermalState(
            temperature_celsius=temp,
            ram_free_mb=ram_free,
            operational_mode=OperationalMode.NORMAL,
            policy=politica,
            should_pause_local_llm=False,
            should_delegate_all=False,
            emergency=False,
            advisory=advisory,
        )

    # ------------------------------------------------------------------
    # Lectura de hardware
    # ------------------------------------------------------------------

    def _autodiscover_hwmon(self) -> Path | None:
        """
        Autodescubre el sensor de temperatura correcto en /sys/class/hwmon/.
        Busca primero 'Package id 0' (CPU Intel) o 'Tdie' (AMD).
        """
        hwmon_base = Path("/sys/class/hwmon")
        if not hwmon_base.exists():
            return None
        for hwmon in sorted(hwmon_base.iterdir()):
            for temp_label in sorted(hwmon.glob("temp*_label")):
                try:
                    label = temp_label.read_text().strip().lower()
                    if "package id 0" in label or "tdie" in label or "cpu" in label:
                        input_path = Path(str(temp_label).replace("_label", "_input"))
                        if input_path.exists():
                            return input_path
                except Exception:
                    continue
        # Fallback: primer temp1_input disponible
        for hwmon in sorted(hwmon_base.iterdir()):
            candidate = hwmon / "temp1_input"
            if candidate.exists():
                return candidate
        return None

    def _read_temperature(self) -> float:
        """Lee temperatura en grados Celsius. Retorna 0.0 si no disponible."""
        if self._hwmon_path is None or not self._hwmon_path.exists():
            return 0.0
        try:
            raw = self._hwmon_path.read_text().strip()
            return float(raw) / 1000.0  # millidegrees → degrees
        except Exception:
            return 0.0

    def _read_ram_free_mb(self) -> int:
        """Lee RAM libre en MB desde /proc/meminfo."""
        try:
            meminfo = Path("/proc/meminfo").read_text()
            for line in meminfo.splitlines():
                if line.startswith("MemAvailable:"):
                    match = re.search(r"\d+", line)
                    if match is None:
                        continue
                    return int(match.group()) // 1024
        except Exception:
            pass
        return 9999   # Si no podemos leer, asumir que hay suficiente RAM
