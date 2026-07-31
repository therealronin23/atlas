"""Vigilante local con aviso a Telegram (2026-07-31, decisión del operador).

Existe por un fallo REAL y medido, no por completitud: el 2026-07-30 a las
18:19 se paró `atlas-core.service`; tras el reinicio de las 18:45 no rearrancó
(el gestor systemd tenía el estado cargado sin la dependencia) y estuvo **~23 h
muerto sin que nadie se enterara**. El grafo quedó 31 commits atrás, cero ticks
de mantenimiento, y `cold_update` en `degraded` sin canal que lo dijera.

`scripts/daemon_idle_guard.sh` ya cubría una parte, y su docstring fija la
restricción de diseño que este módulo hereda: **el vigilante NO puede vivir
dentro del daemon** — un radar que corre en el tick del daemon jamás detectará
que el daemon está muerto. Lo que le falta al guard, y es justo lo que el
operador pidió hace 22 días con "cuando no esté, monitoriza el servidor":

- sólo corre al ARRANCAR una sesión de agente, así que no puede avisar a un
  humano ausente;
- su umbral es 24 h y esta caída duró 23 h: silencio correcto según su regla,
  daemon muerto igualmente.

Regla del operador para este vigilante: **"sólo lo grave, nada de ruido"**. Se
avisa en la TRANSICIÓN a mal estado, no en cada pasada; se repite sólo pasado
un intervalo largo; y una sonda que no puede medir se registra como
desconocida y **NO** avisa (no saber no es una emergencia).
"""

from __future__ import annotations

from pathlib import Path

from atlas.runtime.watchdog import (
    Check,
    WatchdogState,
    decide_alerts,
    format_alert,
)

HOUR = 3600.0


def _bad(name: str = "atlas-core") -> Check:
    return Check(name=name, ok=False, detail="inactivo desde hace 23h")


def _ok(name: str = "atlas-core") -> Check:
    return Check(name=name, ok=True, detail="activo")


def _unknown(name: str = "atlas-core") -> Check:
    return Check(name=name, ok=None, detail="systemctl no disponible")


class TestAlertsOnTransition:
    def test_first_failure_alerts(self) -> None:
        alerts, _ = decide_alerts([_bad()], WatchdogState(), now=1000.0)

        assert [a.name for a in alerts] == ["atlas-core"]

    def test_everything_healthy_says_nothing(self) -> None:
        alerts, _ = decide_alerts([_ok()], WatchdogState(), now=1000.0)

        assert alerts == []


class TestNoNoise:
    """La regla del operador: 'sólo lo grave, nada de ruido'."""

    def test_still_failing_stays_silent_within_the_window(self) -> None:
        _, state = decide_alerts([_bad()], WatchdogState(), now=1000.0)

        alerts, _ = decide_alerts([_bad()], state, now=1000.0 + HOUR)

        assert alerts == []

    def test_still_failing_realerts_after_the_window(self) -> None:
        _, state = decide_alerts([_bad()], WatchdogState(), now=1000.0)

        alerts, _ = decide_alerts([_bad()], state, now=1000.0 + 13 * HOUR)

        assert [a.name for a in alerts] == ["atlas-core"]

    def test_a_flapping_check_does_not_alert_twice_per_cycle(self) -> None:
        # bad -> ok -> bad dentro de la ventana: la recuperación limpia el
        # estado, así que la segunda caída SÍ es una transición nueva y avisa.
        # Se fija por test para que el comportamiento sea deliberado, no casual.
        _, s1 = decide_alerts([_bad()], WatchdogState(), now=1000.0)
        _, s2 = decide_alerts([_ok()], s1, now=2000.0)

        alerts, _ = decide_alerts([_bad()], s2, now=3000.0)

        assert [a.name for a in alerts] == ["atlas-core"]


class TestRecovery:
    def test_recovery_is_reported_once(self) -> None:
        _, state = decide_alerts([_bad()], WatchdogState(), now=1000.0)

        alerts, state2 = decide_alerts([_ok()], state, now=2000.0)

        assert [a.name for a in alerts] == ["atlas-core"]
        assert alerts[0].recovered is True

    def test_recovery_is_not_repeated(self) -> None:
        _, s1 = decide_alerts([_bad()], WatchdogState(), now=1000.0)
        _, s2 = decide_alerts([_ok()], s1, now=2000.0)

        alerts, _ = decide_alerts([_ok()], s2, now=3000.0)

        assert alerts == []


class TestUnknownIsNotAnEmergency:
    def test_an_unmeasurable_probe_never_alerts(self) -> None:
        # No poder medir no es una emergencia: avisar de ello sería justo el
        # ruido que el operador pidió evitar.
        alerts, _ = decide_alerts([_unknown()], WatchdogState(), now=1000.0)

        assert alerts == []

    def test_unknown_does_not_count_as_recovery(self) -> None:
        _, state = decide_alerts([_bad()], WatchdogState(), now=1000.0)

        alerts, _ = decide_alerts([_unknown()], state, now=2000.0)

        assert alerts == []


class TestMessage:
    def test_the_message_names_what_broke_and_why(self) -> None:
        alerts, _ = decide_alerts([_bad()], WatchdogState(), now=1000.0)

        text = format_alert(alerts)

        assert "atlas-core" in text
        assert "23h" in text

    def test_recovery_message_is_distinguishable(self) -> None:
        _, state = decide_alerts([_bad()], WatchdogState(), now=1000.0)
        alerts, _ = decide_alerts([_ok()], state, now=2000.0)

        assert "atlas-core" in format_alert(alerts)


class TestRunOnce:
    """El ensamblado: sondas inyectadas, envío inyectado, estado en disco.
    Nada de systemd ni de red en los tests."""

    def test_sends_nothing_when_everything_is_healthy(self, tmp_path: Path) -> None:
        from atlas.runtime.watchdog import run_once

        sent: list[str] = []
        n = run_once(
            probes=[lambda: _ok()],
            send=sent.append,
            state_path=tmp_path / "s.json",
            now=1000.0,
        )

        assert n == 0
        assert sent == []

    def test_sends_one_message_with_everything_that_broke(self, tmp_path: Path) -> None:
        from atlas.runtime.watchdog import run_once

        sent: list[str] = []
        n = run_once(
            probes=[lambda: _bad("atlas-core"), lambda: _bad("disco")],
            send=sent.append,
            state_path=tmp_path / "s.json",
            now=1000.0,
        )

        assert n == 1  # UN mensaje, no uno por señal
        assert "atlas-core" in sent[0] and "disco" in sent[0]

    def test_a_probe_that_raises_never_takes_down_the_watchdog(
        self, tmp_path: Path
    ) -> None:
        from atlas.runtime.watchdog import run_once

        def boom() -> Check:
            raise OSError("systemctl desaparecido")

        sent: list[str] = []
        run_once(
            probes=[boom, lambda: _bad("disco")],
            send=sent.append,
            state_path=tmp_path / "s.json",
            now=1000.0,
        )

        assert "disco" in sent[0]

    def test_a_failing_sender_does_not_lose_the_state(self, tmp_path: Path) -> None:
        # Si el envío falla, NO se debe marcar como avisado: si no, la caída
        # quedaría silenciada durante toda la ventana de repetición.
        from atlas.runtime.watchdog import WatchdogState, run_once

        def broken(_text: str) -> None:
            raise OSError("sin red")

        state_path = tmp_path / "s.json"
        run_once(
            probes=[lambda: _bad()], send=broken, state_path=state_path, now=1000.0
        )

        assert WatchdogState.load(state_path).failing == {}


class TestStatePersistence:
    def test_state_survives_a_round_trip(self, tmp_path: Path) -> None:
        # El vigilante corre como timer: cada pasada es un proceso nuevo, así
        # que sin persistencia no habría transiciones que detectar.
        _, state = decide_alerts([_bad()], WatchdogState(), now=1000.0)
        path = tmp_path / "state.json"

        state.save(path)
        alerts, _ = decide_alerts([_bad()], WatchdogState.load(path), now=1000.0 + HOUR)

        assert alerts == []

    def test_missing_state_file_starts_clean(self, tmp_path: Path) -> None:
        assert WatchdogState.load(tmp_path / "no-existe.json").failing == {}
