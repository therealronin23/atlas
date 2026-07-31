"""Atlas no podía ni LEER ni DIAGNOSTICAR el tablero de Hermes (2026-08-01).

Petición del operador: *"haz que Hermes corrija y se autocorrija"*. Al medirlo,
el hallazgo fue que **Hermes ya trae las dos mitades y Atlas nunca las llama**:

* ``hermes kanban diagnostics --json`` detecta problemas y emite acciones
  sugeridas estructuradas;
* ``hermes kanban repair --json`` corre ``PRAGMA integrity_check`` y auto-repara
  **sólo** corrupción de índices (REINDEX tras poner una copia en cuarentena),
  dejando intacto y reportado cualquier otro tipo — fail-closed de fábrica.

Ninguna de las dos estaba en ``ALLOWED_KANBAN_ACTIONS``, así que el puente las
rechazaba. Y ``list_tasks()`` no pasaba ``--json``, con lo que
``KanbanResult.parsed`` quedaba ``None`` y Atlas sólo recibía una tabla de texto
imposible de razonar.

Medido en el tablero real el 2026-08-01 (19 tareas): 1 ``critical``
(``stranded_in_ready``, 564 h sin worker), 2 ``error`` (``repeated_failures``) y
2 ``warning`` (``stuck_in_blocked``, 198 h). **Hermes llevaba 23 días
reportándolo y nadie escuchaba.**
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from atlas.hermes.kanban_bridge import ALLOWED_KANBAN_ACTIONS, KanbanBridge


class _SpyRunner:
    """Captura el argv en vez de invocar Hermes de verdad."""

    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.calls: list[list[str]] = []

    def __call__(self, argv: Any, timeout_s: float) -> tuple[int, str, str]:
        self.calls.append(list(argv))
        return self.returncode, self.stdout, ""

    @property
    def last_command(self) -> str:
        """El argv aplanado.

        Por SSH los argumentos de kanban viajan unidos en UNA cadena
        (``shlex.join`` dentro de ``runuser ... --``), así que buscar un flag
        como elemento de la lista da falso negativo. Se busca en el texto.
        """
        return " ".join(self.calls[-1]) if self.calls else ""


def _bridge(runner: _SpyRunner, **kw: Any) -> KanbanBridge:
    return KanbanBridge(
        transport="ssh",
        ssh_host="hermes@100.64.0.1",
        runner=runner,
        **kw,
    )


class TestAtlasCanDiagnose:
    """Lo que faltaba para que Atlas se entere de que Hermes está atascado."""

    def test_diagnostics_is_an_allowed_action(self) -> None:
        assert "diagnostics" in ALLOWED_KANBAN_ACTIONS

    def test_repair_is_an_allowed_action(self) -> None:
        # Fail-closed de fábrica: sólo repara índices, cuarentena el resto.
        assert "repair" in ALLOWED_KANBAN_ACTIONS

    def test_diagnostics_asks_for_json_so_atlas_can_reason_about_it(self) -> None:
        runner = _SpyRunner(stdout="[]")

        _bridge(runner).diagnostics()

        assert runner.calls, "no se invocó a Hermes"
        assert "--json" in runner.last_command, "sin --json sólo llega una tabla de texto"

    def test_diagnostics_returns_parsed_findings(self) -> None:
        payload = [
            {
                "task_id": "t_faf3ba40",
                "title": "Clarify task requirements",
                "diagnostics": [
                    {"kind": "stranded_in_ready", "severity": "critical"}
                ],
            }
        ]
        runner = _SpyRunner(stdout=json.dumps(payload))

        result = _bridge(runner).diagnostics()

        assert result.parsed == payload

    def test_diagnostics_can_filter_by_severity(self) -> None:
        """La orden en pie del operador es "sólo lo grave, nada de ruido"."""
        runner = _SpyRunner(stdout="[]")

        _bridge(runner).diagnostics(severity="error")

        assert "--severity" in runner.last_command
        assert "error" in runner.last_command


class TestAtlasCanReadTasks:
    def test_list_tasks_asks_for_json(self) -> None:
        """`parsed` quedaba None: el CLI emite una tabla, no JSON, salvo que se
        le pida. Cualquiera que consumiera `.parsed` recibía None en silencio."""
        runner = _SpyRunner(stdout="[]")

        _bridge(runner).list_tasks()

        assert "--json" in runner.last_command

    def test_list_tasks_still_filters_by_status(self) -> None:
        runner = _SpyRunner(stdout="[]")

        _bridge(runner).list_tasks(status="blocked")

        assert "--status" in runner.last_command
        assert "blocked" in runner.last_command


class TestTheAllowlistStillGuards:
    """Ampliar la lista no puede convertirla en un colador."""

    def test_an_unknown_action_is_still_rejected(self) -> None:
        with pytest.raises(ValueError, match="unsupported kanban action"):
            _bridge(_SpyRunner()).run("rm-rf")

    def test_destructive_actions_stay_out(self) -> None:
        # `gc` borra de verdad; no entra sin decisión explícita.
        assert "gc" not in ALLOWED_KANBAN_ACTIONS


class TestTheInjectedRunnerIsHonoured:
    def test_the_local_path_uses_the_injected_runner(self, monkeypatch) -> None:
        """`_run_local` llamaba a `_default_runner` en vez de a `self._runner`,
        así que un test que inyectaba runner acababa invocando el Hermes REAL
        de la máquina — o silenciosamente cayendo al tablero JSON de respaldo."""
        import atlas.hermes.kanban_bridge as kb

        monkeypatch.setattr(kb.shutil, "which", lambda _: "/usr/bin/hermes")
        runner = _SpyRunner(stdout="[]")
        bridge = KanbanBridge(transport="local", runner=runner)

        bridge.diagnostics()

        assert runner.calls, "el runner inyectado se ignoró: se llamó al Hermes real"


class TestTheWatchdogNoticesHermes:
    """Detectar sin avisar no sirve de nada.

    No se escribe un tick nuevo: el watchdog YA corre cada 15 min, ya tiene el
    canal de Telegram verificado extremo a extremo, y ya trae la anti-repetición
    de 12 h y la distinción "no medible" vs "roto". Sólo le faltaba una sonda.
    """

    def test_a_healthy_board_does_not_alert(self) -> None:
        from atlas.runtime.watchdog import hermes_probe

        check = hermes_probe(diagnose=lambda: [])

        assert check.ok is True

    def test_critical_and_error_findings_are_grave(self) -> None:
        from atlas.runtime.watchdog import hermes_probe

        findings = [
            {"title": "Clarify task", "diagnostics": [{"severity": "critical",
                                                       "kind": "stranded_in_ready"}]},
        ]

        check = hermes_probe(diagnose=lambda: findings)

        assert check.ok is False
        assert "stranded_in_ready" in check.detail

    def test_warnings_alone_are_not_grave(self) -> None:
        """La orden del operador fue "sólo lo grave, nada de ruido". Dos tareas
        llevan 198 h bloqueadas: es real, pero no es una emergencia."""
        findings = [
            {"title": "monitoriza servidor A",
             "diagnostics": [{"severity": "warning", "kind": "stuck_in_blocked"}]},
        ]
        from atlas.runtime.watchdog import hermes_probe

        check = hermes_probe(diagnose=lambda: findings)

        assert check.ok is True

    def test_an_unreachable_hermes_is_unknown_not_broken(self) -> None:
        from atlas.runtime.watchdog import hermes_probe

        def _boom() -> list[dict[str, Any]]:
            raise OSError("hermes no está")

        check = hermes_probe(diagnose=_boom)

        assert check.ok is None

    def test_the_probe_is_registered_in_the_watchdog(self) -> None:
        """wire-before-claim: una sonda que nadie corre no vigila nada."""
        from atlas.runtime.watchdog import default_probes, hermes_probe

        names = [getattr(p, "__name__", "") for p in default_probes()]

        assert hermes_probe.__name__ in names or any(
            "hermes" in n for n in names
        ), "la sonda existe pero el watchdog no la corre"


class TestTheBridgeLoadsDotenvLikeItsSiblings:
    """Tercera vez de este bug de clase: `inference_hub` lo perdió en 5da5f5f,
    `reality` nunca lo tuvo, y `kanban_bridge` dependía del llamador.

    Medido 2026-08-01: desde un proceso limpio `KanbanBridge()` resolvía
    transporte `ssh` y lanzaba "HERMES_SSH_HOST is required", cuando la
    configuración real del operador dice `local`.
    """

    def test_it_loads_dotenv_at_import_time(self) -> None:
        import atlas.hermes.kanban_bridge as kb

        src = __import__("inspect").getsource(kb)
        head = src.split("Runner = Callable")[0]

        assert "load_dotenv" in head, (
            "el puente no carga .env en tiempo de import: vuelve a depender "
            "de que el llamador lo haya hecho"
        )
