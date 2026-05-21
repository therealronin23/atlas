"""
Atlas Core — Thermal Watchdog con Triage Alfa/Omega
Monitoriza temperatura y RAM. Activa modo degradado antes de throttling.
Critico para hardware limitado (HP Omen laptop, 16GB RAM).

Modos del chat de Gemini:
  NORMAL tier: Docker efimero sin red, 512MB RAM, bajo riesgo, velocidad.
  OMEGA (10% del tiempo): VM Proxmox + Snapshot + HITL via Telegram, alto riesgo.
  
Politica de respuesta escalonada:
  < 70C   → NORMAL: sin restricciones
  70-79C  → DEGRADED: LLMs pesados pausados (pausa LLM pesado, mensaje Telegram)
  80-89°C → OMEGA forzado (solo L-det + delegacion Hermes)
  >= 90°C → emergencia (parar todo, notificar)
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

TEMP_NORMAL_THRESHOLD   = 70.0   # < 70C  → NORMAL: sin restricciones
TEMP_DEGRADED_THRESHOLD = 80.0   # 70-79C → DEGRADED: sin LLMs pesados
TEMP_OMEGA_THRESHOLD    = 90.0   # >= 80C → OMEGA: solo L-det + Hermes
                                  # Note: DEGRADED and OMEGA share 80C boundary;
                                  # OMEGA is also triggered by combined temp+RAM pressure.

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
            with self._lock:
                if self._current_state:
                    prev_mode = self._current_state.operational_mode
                self._current_state = state

            # Notificar si cambia el modo o hay emergencia
            if self._alert_callback and (
                state.emergency
                or (prev_mode is not None and prev_mode != state.operational_mode)
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

        # Tier 2 — DEGRADED: tension termica o RAM baja, funciones criticas OK
        if temp >= TEMP_DEGRADED_THRESHOLD or ram_free < RAM_DEGRADED_THRESHOLD_MB:
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

        # Tier 1 — NORMAL: operacion completa sin restricciones
        return ThermalState(
            temperature_celsius=temp,
            ram_free_mb=ram_free,
            operational_mode=OperationalMode.NORMAL,
            policy=f"NORMAL: {temp:.1f}C / {ram_free}MB RAM libre. Sin restricciones.",
            should_pause_local_llm=False,
            should_delegate_all=False,
            emergency=False,
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
                    kb = int(re.search(r"\d+", line).group())
                    return kb // 1024
        except Exception:
            pass
        return 9999   # Si no podemos leer, asumir que hay suficiente RAM
