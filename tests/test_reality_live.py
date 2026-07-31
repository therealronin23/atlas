"""`atlas reality` medía CONFIGURACIÓN e HISTORIA, no el sistema vivo (2026-07-31).

Lo dijo el operador: *"atlas reality verdaderamente no hace nada"*. La medida
que lo confirma es brutal en su simplicidad: las **7** menciones a `daemon` en
``reality.py`` están todas en docstrings que describen *leer ficheros que el
daemon escribió*. Ninguna comprueba si el daemon está VIVO.

El informe leía el humo del motor y nunca miraba el motor. Es el mismo agujero
por el que ``atlas-core.service`` estuvo **23 h muerto** sin que nadie se
enterara (ver ``daemon-died-silently-23h-watchdog``): durante todo ese tiempo
``atlas reality`` habría seguido diciendo que el sistema estaba bien, porque
todo lo que mira son ficheros del pasado y variables de entorno.

Dos invariantes se fijan aquí:

1. **El daemon se mide, no se supone.** Y la sonda es *fail-honest*: si no se
   puede medir, ``active=None`` (desconocido), nunca ``False``. Un vigilante
   que grita cuando no sabe es ruido, y la orden fue "sólo lo grave".
2. **Cada sección declara de qué CLASE es su evidencia** (``live`` /
   ``config`` / ``history``). Sin esto, ``hermes.configured=True`` se lee como
   "Hermes funciona" cuando sólo significa "hay variables puestas". La
   condición no negociable del operador — *nunca afirmar LIVE_VERIFIED sin una
   sonda real* — deja de depender de que quien lea el informe sea cuidadoso y
   pasa a ser estructural.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from atlas.core.reality import _overall_status, collect_reality, strict_failures
from atlas.core.reality_live import (
    EVIDENCE_CONFIG,
    EVIDENCE_HISTORY,
    EVIDENCE_LIVE,
    daemon_state,
    hermes_probe,
    security_state,
    evidence_summary,
)


def _repo(tmp_path: Path) -> Path:
    """Un checkout mínimo: `collect_reality` interroga git de verdad."""
    root = tmp_path / "repo"
    (root / "src" / "atlas").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text(
        "[project]\nversion='0.0.1'\nname='atlas-test'\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "i"],
        cwd=root,
        check=True,
    )
    return root


class _FakeRun:
    """Sustituye a `systemctl` sin tocar el systemd de la máquina real."""

    def __init__(self, stdout: str, *, raises: bool = False) -> None:
        self.stdout = stdout
        self.raises = raises

    def __call__(self, *args: object, **kwargs: object) -> object:
        if self.raises:
            raise OSError("systemctl no está aquí")
        return type("R", (), {"stdout": self.stdout, "returncode": 0})()


class TestDaemonIsMeasuredNotAssumed:
    """El agujero de las 23 h."""

    def test_the_report_has_a_daemon_section_at_all(self) -> None:
        state = daemon_state(runner=_FakeRun("active\n"))

        assert state["unit"], "la sección no identifica qué unidad mide"

    def test_an_active_daemon_is_reported_alive(self) -> None:
        state = daemon_state(runner=_FakeRun("active\n"))

        assert state["active"] is True

    def test_a_dead_daemon_is_reported_dead(self) -> None:
        # El caso real: `enabled` pero sin arrancar tras un reinicio.
        state = daemon_state(runner=_FakeRun("inactive\n"))

        assert state["active"] is False
        assert "inactive" in state["reason"]

    def test_an_unmeasurable_daemon_is_unknown_not_dead(self) -> None:
        """Fail-honest: no poder medir NO es una avería."""
        state = daemon_state(runner=_FakeRun("", raises=True))

        assert state["active"] is None
        assert state["active"] is not False

    def test_the_daemon_probe_declares_itself_live_evidence(self) -> None:
        state = daemon_state(runner=_FakeRun("active\n"))

        assert state["evidence"] == EVIDENCE_LIVE


class TestEvidenceClassIsStructural:
    """`configured=True` no puede seguir leyéndose como `funciona`."""

    def test_it_counts_each_class_separately(self) -> None:
        report = {
            "daemon": {"evidence": EVIDENCE_LIVE},
            "hermes": {"evidence": EVIDENCE_CONFIG},
            "provider_smoke": {"evidence": EVIDENCE_HISTORY},
            "engineering_review": {"evidence": EVIDENCE_HISTORY},
        }

        summary = evidence_summary(report)

        assert summary["live"] == 1
        assert summary["config"] == 1
        assert summary["history"] == 2

    def test_sections_without_a_declared_class_are_surfaced_not_hidden(self) -> None:
        """Una sección sin clase es deuda VISIBLE, no un aprobado por defecto."""
        report = {"misterio": {"status": "ok"}}

        summary = evidence_summary(report)

        assert summary["unclassified"] == 1
        assert "misterio" in summary["unclassified_sections"]

    def test_it_reports_what_fraction_actually_measures_the_live_system(self) -> None:
        report = {
            "daemon": {"evidence": EVIDENCE_LIVE},
            "hermes": {"evidence": EVIDENCE_CONFIG},
            "provider_smoke": {"evidence": EVIDENCE_HISTORY},
        }

        summary = evidence_summary(report)

        # La respuesta a "reality no hace nada" es un número, no una opinión.
        assert summary["live"] == 1
        assert summary["total_classified"] == 3


class TestHermesIsProbedNotAssumed:
    """`live_verified` estaba clavado a False: nunca podía ser otra cosa.

    Con Hermes VIVO en local (kanban, 19 tareas en cola) el informe seguía
    diciendo "configurado, corre una delegación para tener evidencia". La
    evidencia estaba a una lectura local de distancia y costaba cero.
    """

    def test_a_reachable_local_board_is_verified_live(self) -> None:
        state = hermes_probe(
            {"mode": "kanban_local", "configured": True, "live_verified": False},
            reachable=lambda: True,
        )

        assert state["live_verified"] is True
        assert state["reachable"] is True
        assert state["evidence"] == EVIDENCE_LIVE

    def test_an_unreachable_local_board_is_measured_as_down(self) -> None:
        state = hermes_probe(
            {"mode": "kanban_local", "configured": True, "live_verified": False},
            reachable=lambda: False,
        )

        assert state["live_verified"] is False
        assert state["reachable"] is False
        assert state["evidence"] == EVIDENCE_LIVE  # se midió; salió mal

    def test_an_unmeasurable_board_is_unknown_not_down(self) -> None:
        def _boom() -> bool:
            raise OSError("tablero ilegible")

        state = hermes_probe(
            {"mode": "kanban_local", "configured": True, "live_verified": False},
            reachable=_boom,
        )

        assert state["reachable"] is None
        assert state["live_verified"] is False  # no verificado != verificado como roto

    def test_a_remote_transport_is_not_probed_from_a_status_command(self) -> None:
        """`atlas reality` no sale a la red por su cuenta: sondear SSH sería
        una llamada remota escondida detrás de un comando de estado."""
        called = False

        def _tracker() -> bool:
            nonlocal called
            called = True
            return True

        state = hermes_probe(
            {"mode": "kanban_ssh", "configured": True, "live_verified": False},
            reachable=_tracker,
        )

        assert called is False
        assert state["live_verified"] is False
        assert state["evidence"] == EVIDENCE_CONFIG

    def test_a_probed_section_keeps_its_live_class_when_the_report_stamps(self) -> None:
        """Una sección que SÍ se midió no puede ser degradada a `config` por la
        tabla estática."""
        from atlas.core.reality import _stamp_evidence

        report = {"hermes": hermes_probe(
            {"mode": "kanban_local", "configured": True, "live_verified": False},
            reachable=lambda: True,
        )}

        _stamp_evidence(report)

        assert report["hermes"]["evidence"] == EVIDENCE_LIVE


class TestSecurityIsMeasuredOnDisk:
    """El operador pidió que reality mirara *también a la seguridad*.

    Nadie en el repo comprobaba la higiene del fichero de secretos: ni sus
    permisos ni —lo grave— si git lo está siguiendo. Son dos preguntas que se
    contestan AHORA, con `stat` y `git ls-files`, sin coste ni red.
    """

    def test_a_locked_down_secrets_file_passes(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        env = root / ".env"
        env.write_text("SECRETO=1\n", encoding="utf-8")
        env.chmod(0o600)

        state = security_state(root)

        assert state["secrets_world_readable"] is False
        assert state["status"] == "ok"

    def test_a_world_readable_secrets_file_is_flagged(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        env = root / ".env"
        env.write_text("SECRETO=1\n", encoding="utf-8")
        env.chmod(0o644)

        state = security_state(root)

        assert state["secrets_world_readable"] is True
        assert state["status"] == "degraded"
        assert "644" in state["reason"]

    def test_a_tracked_secrets_file_is_the_loud_case(self, tmp_path: Path) -> None:
        """Secretos versionados: lo peor que puede pasar aquí."""
        root = _repo(tmp_path)
        env = root / ".env"
        env.write_text("SECRETO=1\n", encoding="utf-8")
        env.chmod(0o600)
        subprocess.run(["git", "add", "-f", ".env"], cwd=root, check=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "ups"],
            cwd=root,
            check=True,
        )

        state = security_state(root)

        assert state["secrets_tracked_by_git"] is True
        assert state["status"] == "degraded"

    def test_no_secrets_file_is_unknown_not_a_failure(self, tmp_path: Path) -> None:
        """Fail-honest: no hay `.env` que juzgar, no es que esté mal."""
        state = security_state(_repo(tmp_path))

        assert state["secrets_world_readable"] is None
        assert state["status"] != "degraded"

    def test_it_declares_itself_live_evidence(self, tmp_path: Path) -> None:
        state = security_state(_repo(tmp_path))

        assert state["evidence"] == EVIDENCE_LIVE


class TestTheHeadlineReflectsTheProbes:
    """De poco sirve medir el daemon si la cabecera sigue diciendo OK.

    Sería el pecado original repetido una línea más arriba: `atlas reality`
    imprime `Atlas reality — OK` en grande, y durante las 23 h de apagón lo
    habría seguido imprimiendo.
    """

    def _report(self, **overrides: object) -> dict:
        base = {
            "checks": {},
            "docs": {"status": "ok"},
            "workspace": {"merkle": {"status": "ok"}},
            "daemon": {"active": True},
            "security": {"status": "ok"},
        }
        base.update(overrides)
        return base

    def test_a_healthy_system_is_ok(self) -> None:
        assert _overall_status(self._report()) == "ok"

    def test_a_dead_daemon_degrades_the_headline(self) -> None:
        report = self._report(daemon={"active": False})

        assert _overall_status(report) == "degraded"

    def test_an_unknown_daemon_does_not_degrade(self) -> None:
        """Fail-honest hasta arriba: no poder medir no es una avería."""
        report = self._report(daemon={"active": None})

        assert _overall_status(report) == "ok"

    def test_leaked_secrets_degrade_the_headline(self) -> None:
        report = self._report(security={"status": "degraded"})

        assert _overall_status(report) == "degraded"

    def test_a_dead_daemon_fails_a_strict_readiness_gate(self) -> None:
        """`--strict` es una puerta de preparación: sin daemon no hay lazo."""
        report = self._report(daemon={"active": False}, browser={"status": "ready"})

        assert any("daemon" in f for f in strict_failures(report))


class TestTheRealReportCarriesIt:
    """De nada sirve el módulo si `collect_reality` no lo usa (wire-before-claim)."""

    def test_the_report_now_looks_at_the_daemon(self, tmp_path: Path) -> None:
        report = collect_reality(repo_root=_repo(tmp_path), workspace=tmp_path / "ws")

        assert "daemon" in report, "el informe sigue sin mirar si el daemon vive"
        assert report["daemon"]["evidence"] == EVIDENCE_LIVE

    def test_every_section_declares_its_evidence_class(self, tmp_path: Path) -> None:
        """Sin excepciones: una sección sin clase es una que puede volver a
        leerse como 'funciona' cuando sólo significa 'está declarada'."""
        report = collect_reality(repo_root=_repo(tmp_path), workspace=tmp_path / "ws")

        summary = report["evidence_summary"]

        assert summary["unclassified_sections"] == []

    def test_the_summary_is_published_in_the_report(self, tmp_path: Path) -> None:
        report = collect_reality(repo_root=_repo(tmp_path), workspace=tmp_path / "ws")

        summary = report["evidence_summary"]

        assert summary["live"] >= 1, "ninguna sección mide el sistema vivo"
        assert summary["history"] >= 1, "las sondas que leen el pasado deben admitirlo"

    def test_the_checks_container_is_not_polluted_with_an_evidence_key(
        self, tmp_path: Path
    ) -> None:
        """`checks` es un CONTENEDOR de resultados, no una sección-sonda.

        Sellarlo le metía una clave `evidence` dentro, con lo que `checks`
        pasaba a ser no-vacío y el renderizador del CLI la recorría como si
        fuera un check más: `check["exit_code"]` sobre la cadena `"live"`.
        `atlas reality` reventaba con TypeError — el comando que AGENTS.md
        manda correr antes de afirmar cualquier estado.
        """
        report = collect_reality(repo_root=_repo(tmp_path), workspace=tmp_path / "ws")

        assert report["checks"] == {}, "sin --run-checks no hay checks que mostrar"

    def test_the_suite_never_probes_the_operators_real_board(self) -> None:
        """Sondear Hermes en vivo convirtió cualquier `collect_reality()` sin
        inyección en un test que ejecuta el kanban de VERDAD. El scrubbing de
        env no basta: `_reset_provider_status` importa `inference_hub`, que
        hace `load_dotenv()` y repuebla `HERMES_KANBAN_TRANSPORT` DESPUÉS de
        que el fixture de aislamiento lo borrara."""
        from atlas.core import reality_live

        assert reality_live._default_hermes_reachable() is False, (
            "el guardia de conftest no está puesto: la suite puede tocar el "
            "tablero real del operador"
        )

    def test_the_human_readable_command_actually_renders(self) -> None:
        """El hueco por el que se coló el TypeError: en el CLI sólo se probaba
        `reality --json`, así que el renderizador para humanos —el que usa el
        operador— podía romperse sin que nadie se enterara."""
        from click.testing import CliRunner

        from atlas.interfaces.cli import cli

        result = CliRunner().invoke(cli, ["reality"])

        assert result.exit_code == 0, result.output
        assert "Evidencia:" in result.output

    def test_hermes_configuration_is_not_dressed_up_as_liveness(
        self, tmp_path: Path
    ) -> None:
        """La condición no negociable del operador, hecha estructura."""
        report = collect_reality(repo_root=_repo(tmp_path), workspace=tmp_path / "ws")

        hermes = report["hermes"]

        if not hermes.get("live_verified"):
            assert hermes["evidence"] == EVIDENCE_CONFIG
