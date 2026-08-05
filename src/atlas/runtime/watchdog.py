"""Vigilante local con aviso a Telegram (2026-07-31).

Nace de un fallo REAL y medido: el 2026-07-30 a las 18:19 se paró
`atlas-core.service`; tras el reinicio de las 18:45 no rearrancó (el gestor
systemd tenía cargado un estado sin la dependencia de `default.target`) y
estuvo **~23 h muerto sin que nadie se enterara**. Grafo 31 commits atrás,
cero ticks de mantenimiento, `cold_update` en `degraded` y ningún canal que
lo dijera.

**Restricción de diseño heredada de `scripts/daemon_idle_guard.sh`**, que ya
la razonó: el vigilante NO puede vivir dentro del daemon. Un radar que corre
en el tick de `self_maintenance` nunca detectará que el daemon está muerto,
porque si el daemon no corre, el radar tampoco. Por eso esto se ejecuta desde
un timer de systemd independiente.

Qué añade sobre ese guard, que es exactamente lo que el operador pidió:
- el guard sólo corre al ARRANCAR una sesión de agente, así que no puede
  avisar a un humano ausente ("cuando no esté, monitoriza el servidor");
- su umbral es 24 h y esta caída duró 23 h — silencio correcto según su
  regla, daemon muerto igualmente.

Regla del operador: **"sólo lo grave, nada de ruido"**. De ahí las tres
decisiones de este módulo:
1. se avisa en la TRANSICIÓN a mal estado, no en cada pasada;
2. si sigue mal, se repite sólo pasado `REALERT_SECONDS` (12 h);
3. una sonda que no puede medir queda `ok=None` y **no avisa** — no saber no
   es una emergencia, y avisarlo sería el ruido que se quiere evitar.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path

REALERT_SECONDS = 12 * 3600.0

# Umbrales deliberadamente ALTOS: la orden es "sólo lo grave". Un disco al 80%
# no es una emergencia; uno al 95% sí lo es y además tiene precedente medido
# en este repo (el /tmp tmpfs de 4G lleno tiró el escritorio).
DISK_CRITICAL_PCT = 95.0
MEM_CRITICAL_AVAILABLE_PCT = 5.0
# Reinicios acumulados que dejan de ser mantenimiento y pasan a ser crash-loop.
# 5 coincide con el `StartLimitBurst` del drop-in de la unidad: si systemd está
# dispuesto a rendirse a los 5, el vigilante debe avisar a los 5.
FLAPPING_RESTARTS = 5


@dataclass(frozen=True)
class Check:
    """Una señal. ``ok=None`` significa NO MEDIBLE, que no es lo mismo que mal."""

    name: str
    ok: bool | None
    detail: str = ""


@dataclass(frozen=True)
class Alert:
    name: str
    detail: str
    recovered: bool = False


@dataclass
class WatchdogState:
    """Persistente entre pasadas: cada ejecución del timer es un proceso
    nuevo, así que sin esto no habría transiciones que detectar."""

    failing: dict[str, float] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> WatchdogState:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        failing = raw.get("failing") if isinstance(raw, dict) else None
        if not isinstance(failing, dict):
            return cls()
        return cls(
            failing={k: float(v) for k, v in failing.items() if isinstance(v, int | float)}
        )

    def save(self, path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"failing": self.failing}, sort_keys=True), encoding="utf-8"
            )
        except OSError:
            # Un vigilante que revienta por no poder escribir su estado es
            # peor que uno que repite un aviso.
            pass


def decide_alerts(
    checks: list[Check], state: WatchdogState, *, now: float
) -> tuple[list[Alert], WatchdogState]:
    """Qué merece molestar al operador AHORA, y el estado resultante."""
    failing = dict(state.failing)
    alerts: list[Alert] = []

    for check in checks:
        if check.ok is None:
            # No medible: ni avisa ni cuenta como recuperación. Se conserva el
            # estado previo para no perder una caída en curso por una pasada
            # ciega.
            continue
        if check.ok:
            if check.name in failing:
                del failing[check.name]
                alerts.append(Alert(check.name, check.detail, recovered=True))
            continue
        last = failing.get(check.name)
        if last is None or now - last >= REALERT_SECONDS:
            failing[check.name] = now
            alerts.append(Alert(check.name, check.detail))

    return alerts, WatchdogState(failing=failing)


def format_alert(alerts: list[Alert]) -> str:
    """Mensaje corto y accionable: qué, y por qué se dice."""
    if not alerts:
        return ""
    lines: list[str] = []
    broken = [a for a in alerts if not a.recovered]
    fixed = [a for a in alerts if a.recovered]
    if broken:
        lines.append("🔴 Atlas — algo se ha roto:")
        lines += [f"  · {a.name}: {a.detail}" for a in broken]
    if fixed:
        lines.append("🟢 Atlas — recuperado:")
        lines += [f"  · {a.name}: {a.detail}" for a in fixed]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sondas. Cada una devuelve `ok=None` cuando NO PUEDE medir, nunca `ok=False`:
# confundir "no sé" con "está roto" genera falsas alarmas, y una falsa alarma
# repetida enseña al operador a ignorar el canal.
# ---------------------------------------------------------------------------


def service_probe(unit: str = "atlas-core.service") -> Check:
    """El caso que motivó todo esto. `is-active` no necesita al daemon vivo."""
    try:
        out = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return Check(unit, None, "systemctl no disponible")
    state = out.stdout.strip()
    if state == "active":
        return Check(unit, True, "activo")
    return Check(unit, False, f"NO activo (estado={state or 'desconocido'})")


def flapping_probe(
    unit: str = "atlas-core.service", threshold: int = FLAPPING_RESTARTS,
) -> Check:
    """El punto ciego de `service_probe`: "vivo e inútil".

    `is-active` responde `active` durante casi todo el ciclo de un crash-loop,
    así que el 2026-08-02 el daemon se reinició 4.872 veces en 23 h y esa sonda
    habría dicho "activo" en cada pasada. systemd ya publica el contador que lo
    delata; aquí sólo se lee.

    Un reinicio suelto (un `restart` a mano, un despliegue) NO alarma: la regla
    del operador es "sólo lo grave". `systemctl --user reset-failed` pone el
    contador a cero tras atender un incidente.
    """
    name = f"reinicios {unit}"
    try:
        out = subprocess.run(
            ["systemctl", "--user", "show", unit, "-p", "NRestarts"],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return Check(name, None, "systemctl no disponible")
    raw = out.stdout.strip().partition("=")[2].strip()
    if not raw.isdigit():
        return Check(name, None, f"NRestarts no legible ({out.stdout.strip()[:60]!r})")
    restarts = int(raw)
    if restarts >= threshold:
        return Check(
            name, False,
            f"{restarts} reinicios acumulados (umbral {threshold}) — la unidad "
            "está VIVA pero reiniciándose; 'is-active' no lo distingue",
        )
    return Check(name, True, f"{restarts} reinicios")


def disk_probe(path: str = "/", threshold_pct: float = DISK_CRITICAL_PCT) -> Check:
    name = f"disco {path}"
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return Check(name, None, "no medible")
    pct = (usage.used / usage.total) * 100 if usage.total else 0.0
    free_gb = usage.free / (1024**3)
    if pct >= threshold_pct:
        return Check(name, False, f"al {pct:.0f}% ({free_gb:.1f} GB libres)")
    return Check(name, True, f"al {pct:.0f}%")


def memory_probe(threshold_pct: float = MEM_CRITICAL_AVAILABLE_PCT) -> Check:
    """`MemAvailable` es la métrica honesta: 'libre' ignora la caché
    reclamable y dispararía falsas alarmas constantemente."""
    try:
        fields = dict(
            (parts[0].rstrip(":"), float(parts[1]))
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
            if len(parts := line.split()) >= 2
        )
        total, available = fields["MemTotal"], fields["MemAvailable"]
    except (OSError, KeyError, ValueError):
        return Check("memoria", None, "no medible")
    pct = (available / total) * 100 if total else 0.0
    if pct <= threshold_pct:
        return Check("memoria", False, f"sólo {pct:.0f}% disponible")
    return Check("memoria", True, f"{pct:.0f}% disponible")


def merkle_probe(workspace: Path | None = None) -> Check:
    """Integridad de la cadena Merkle: si se rompe, toda la auditoría deja de
    valer. Es de las pocas cosas que merecen despertar a alguien."""
    root = workspace or (Path.home() / "atlas")
    try:
        from atlas.logging.merkle_logger import MerkleLogger

        logger = MerkleLogger(root / "transparency")
        ok = bool(logger.verify_chain())
    except Exception:  # noqa: BLE001 — no medible, jamás una falsa alarma
        return Check("cadena Merkle", None, "no verificable")
    return Check("cadena Merkle", ok, "íntegra" if ok else "ROTA")


#: Severidades de Hermes que merecen molestar al operador. `warning` NO entra:
#: dos tareas llevan 198 h bloqueadas y eso es real, pero no es una emergencia,
#: y la orden en pie es "sólo lo grave, nada de ruido".
GRAVE_HERMES_SEVERITIES = frozenset({"critical", "error"})


def hermes_probe(
    diagnose: Callable[[], list[dict[str, Any]]] | None = None,
) -> Check:
    """Hermes lleva 23 días diagnosticándose solo y nadie le escuchaba.

    ``hermes kanban diagnostics`` detecta tareas varadas, atascadas o con
    fallos repetidos, y lo emite en JSON con acciones sugeridas. Atlas ni
    siquiera tenía la acción en su lista de permitidas hasta hoy.
    """
    if diagnose is None:
        diagnose = _default_hermes_diagnose
    try:
        findings = diagnose()
    except Exception:  # noqa: BLE001 — no medible jamás es "roto"
        return Check("Hermes", None, "tablero no interrogable")

    grave: list[str] = []
    for task in findings or []:
        for item in task.get("diagnostics", []):
            if str(item.get("severity", "")).lower() in GRAVE_HERMES_SEVERITIES:
                grave.append(f"{item.get('kind', '?')}: {task.get('title', '?')[:40]}")
    if grave:
        return Check("Hermes", False, "; ".join(grave[:4]))
    return Check("Hermes", True, "sin hallazgos graves")


def _default_hermes_diagnose() -> list[dict[str, Any]]:
    from atlas.hermes.kanban_bridge import KanbanBridge

    parsed = KanbanBridge().diagnostics().parsed
    return parsed if isinstance(parsed, list) else []


def default_probes() -> list[Callable[[], Check]]:
    return [
        service_probe,
        # `service_probe` ve "muerto"; ésta ve "vivo e inútil". Sin las dos, el
        # crash-loop de 23 h del 2026-08-02 vuelve a pasar desapercibido.
        flapping_probe,
        lambda: disk_probe("/"),
        lambda: disk_probe("/tmp"),
        memory_probe,
        merkle_probe,
        hermes_probe,
    ]


def run_once(
    *,
    probes: Sequence[Callable[[], Check]] | None = None,
    send: Callable[[str], object] | None = None,
    state_path: Path | None = None,
    now: float | None = None,
) -> int:
    """Una pasada. Devuelve cuántos MENSAJES se enviaron (0 o 1).

    Un solo mensaje agregado, no uno por señal: cinco avisos seguidos son
    ruido aunque cada uno sea correcto."""
    state_path = state_path or (Path.home() / ".atlas" / "watchdog_state.json")
    now = time.time() if now is None else now
    probe_list = list(probes) if probes is not None else default_probes()

    checks: list[Check] = []
    for probe in probe_list:
        try:
            checks.append(probe())
        except Exception:  # noqa: BLE001 — una sonda rota no tumba el vigilante
            continue

    state = WatchdogState.load(state_path)
    alerts, new_state = decide_alerts(checks, state, now=now)
    if not alerts:
        new_state.save(state_path)
        return 0

    if send is None:
        send = _telegram_sender()
    try:
        send(format_alert(alerts))
    except Exception:  # noqa: BLE001
        # NO se persiste el estado: si el envío falló, la caída no está
        # avisada, y marcarla silenciaría el problema durante 12 horas.
        return 0
    new_state.save(state_path)
    return 1


def _telegram_sender() -> Callable[[str], object]:
    import os

    from atlas.interfaces.telegram_bot import TelegramClient

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID no configurados")
    client = TelegramClient(token)
    return lambda text: client.send_message(int(chat_id), text)


def main() -> int:
    run_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
