"""La puerta cara deja de pagarse entera para decir que no.

Medido en esta máquina (2026-08-06):

    mypy src/atlas/ ............    1,24 s
    pytest tests/ ..............  396,00 s      -> 320x

`ValidationRunner.run()` corría pytest PRIMERO y mypy SIEMPRE después, aunque
pytest ya hubiera fallado. Sobre los 80 fallos de validación del ledger:

  - 14 eran mypy-solo (`pytest_exit=0, mypy_exit=1`): pagaron los ~396 s de la
    suite completa para llegar a un veredicto que costaba 1,24 s;
  - 66 eran pytest: pagaron además un mypy completo cuyo resultado ya no podía
    cambiar la decisión.

La corrección NO es estadística. PACE (arXiv:2606.08106) diagnostica bien que
una puerta binaria de un solo disparo es una regla de aceptación débil, pero su
método —e-values sobre ensayos muestreados— necesita varianza, y una suite
determinista no la tiene: pytest pasa o no pasa. Lo que sí se traslada es la
idea de acumular evidencia barata y parar pronto cuando es decisivamente
adversa.

INVARIANTE que fija este módulo, y es la que hace segura la optimización:

    las etapas baratas sólo pueden RECHAZAR; sólo la suite completa ACEPTA.

Es sólido en las dos direcciones. Si los tests impactados fallan, la suite
completa también fallaría (son un subconjunto), así que rechazar pronto no
pierde nada. Si pasan, no se concluye nada: se sigue hasta la suite entera.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atlas.core.validation_runner import ValidationReport, ValidationRunner


class _FakeResult:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _SpyJail:
    """Registra los comandos que se le piden, en orden, y responde según una
    tabla por herramienta ('mypy' | 'pytest')."""

    CPU_TIME_LIMIT_S = 0
    RAM_LIMIT_BYTES = 0

    def __init__(self, exits: dict[str, int] | None = None) -> None:
        self.exits = exits or {}
        self.commands: list[list[str]] = []

    def run_command(self, cmd: list[str], **_: Any) -> _FakeResult:
        self.commands.append(list(cmd))
        tool = "mypy" if "mypy" in cmd else "pytest"
        return _FakeResult(self.exits.get(tool, 0), stdout=f"salida de {tool}")

    # --- ayudas de lectura para los tests ---
    @property
    def tools(self) -> list[str]:
        return ["mypy" if "mypy" in c else "pytest" for c in self.commands]

    def pytest_targets(self) -> list[list[str]]:
        out = []
        for c in self.commands:
            if "mypy" in c:
                continue
            out.append([a for a in c if a.startswith("tests")])
        return out


class _EntornoSinMarcaDePytest(dict):  # type: ignore[type-arg]
    """`os.environ` que declara ausente `PYTEST_CURRENT_TEST` pase lo que pase.

    Copiarlo y borrar la clave no sirve: pytest la reinyecta en la fase de
    llamada, DESPUÉS de los fixtures, así que reaparecería dentro de la copia.
    """

    def __contains__(self, key: object) -> bool:
        if key == "PYTEST_CURRENT_TEST":
            return False
        return super().__contains__(key)


@pytest.fixture(autouse=True)
def _sin_guard_de_pytest(monkeypatch: pytest.MonkeyPatch) -> None:
    """`run()` se niega a correr dentro de pytest (guard anti-recursión). Aquí
    la jaula es falsa y no ejecuta nada, así que se oculta la marca en vez de
    debilitar el guard en producción para poder testearlo. El último test del
    módulo deshace esto y comprueba que el guard sigue vivo."""
    import os

    class _OsSinMarca:
        """Proxy del módulo `os` visto SÓLO por validation_runner: cambia
        `environ` y delega todo lo demás. Patchear `os.environ` en el módulo
        real lo cambiaría para todo el proceso."""

        environ = _EntornoSinMarcaDePytest(os.environ)

        def __getattr__(self, name: str) -> Any:
            return getattr(os, name)

    monkeypatch.setattr("atlas.core.validation_runner.os", _OsSinMarca())


def _runner(tmp_path: Path, jail: _SpyJail, **kw: Any) -> ValidationRunner:
    (tmp_path / "tests").mkdir(exist_ok=True)
    return ValidationRunner(tmp_path, jail_factory=lambda: jail, **kw)


# --------------------------------------------------------------------------
# Orden y cortocircuito
# --------------------------------------------------------------------------


def test_mypy_va_primero() -> None:
    """320x más barato: decide antes quien puede decidir antes."""
    jail = _SpyJail()
    report = ValidationRunner(Path.cwd(), jail_factory=lambda: jail).run()

    assert jail.tools[0] == "mypy"
    assert report.passed is True


def test_mypy_falla_y_pytest_no_se_ejecuta() -> None:
    """Los 14 fallos mypy-solo: ~396 s -> ~1 s."""
    jail = _SpyJail({"mypy": 1})

    report = ValidationRunner(Path.cwd(), jail_factory=lambda: jail).run()

    assert jail.tools == ["mypy"]
    assert report.passed is False
    assert report.mypy_exit == 1
    assert report.stage == "types"


def test_el_informe_dice_en_que_etapa_murio() -> None:
    """El ledger registraba `pytest_exit=1` y nada más: imposible aprender de
    ahí. Ahora la etapa viaja en el informe."""
    jail = _SpyJail({"mypy": 1})
    assert ValidationRunner(Path.cwd(), jail_factory=lambda: jail).run().stage == "types"

    jail_ok = _SpyJail()
    assert ValidationRunner(Path.cwd(), jail_factory=lambda: jail_ok).run().stage == "full"


def test_pytest_no_marcado_no_altera_mypy_exit() -> None:
    """Cortocircuitar no puede inventar un `mypy_exit` que nadie midió."""
    jail = _SpyJail({"pytest": 1})

    report = ValidationRunner(Path.cwd(), jail_factory=lambda: jail).run()

    assert report.passed is False
    assert report.mypy_exit == 0


# --------------------------------------------------------------------------
# Etapa de tests impactados
# --------------------------------------------------------------------------


def test_sin_changed_files_va_directo_a_la_suite_completa() -> None:
    """Compatibilidad: los llamadores existentes no pasan nada."""
    jail = _SpyJail()

    ValidationRunner(Path.cwd(), jail_factory=lambda: jail).run()

    assert jail.tools == ["mypy", "pytest"]
    assert jail.pytest_targets() == [["tests/"]]


def test_con_changed_files_corre_primero_los_impactados() -> None:
    jail = _SpyJail()

    ValidationRunner(
        Path.cwd(),
        jail_factory=lambda: jail,
        changed_files=["src/atlas/monitoring/prometheus_exporter.py"],
    ).run()

    assert jail.tools == ["mypy", "pytest", "pytest"]
    primero, segundo = jail.pytest_targets()
    assert primero != ["tests/"]  # subconjunto impactado
    assert segundo == ["tests/"]  # la suite completa sigue siendo la autoridad


def test_los_impactados_fallan_y_la_suite_completa_no_se_paga() -> None:
    """Si un subconjunto falla, el superconjunto también: rechazar aquí no
    pierde información y ahorra la suite entera."""
    jail = _SpyJail({"pytest": 1})

    report = ValidationRunner(
        Path.cwd(),
        jail_factory=lambda: jail,
        changed_files=["src/atlas/monitoring/prometheus_exporter.py"],
    ).run()

    assert jail.tools == ["mypy", "pytest"]
    assert report.passed is False
    assert report.stage == "impacted"


def test_los_impactados_pasan_y_NO_aceptan_por_si_solos() -> None:
    """La invariante central. Un subconjunto verde no es un veredicto."""
    jail = _SpyJail()

    report = ValidationRunner(
        Path.cwd(),
        jail_factory=lambda: jail,
        changed_files=["src/atlas/monitoring/prometheus_exporter.py"],
    ).run()

    assert jail.pytest_targets()[-1] == ["tests/"]
    assert report.stage == "full"
    assert report.passed is True


def test_cambio_sin_tests_impactados_no_cuenta_como_etapa_pasada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cero tests impactados es NO MEDIBLE, no 'todo verde'. Saltarse la suite
    completa por un mapeo vacío sería aceptar sin evidencia.

    El mapeo se inyecta vacío a propósito: `impacted_tests` es conservador y
    devuelve tests hasta para rutas no-Python (`docs/*.md` -> 15,
    `pyproject.toml` -> 19), así que no hay ruta real que produzca el caso.
    """
    monkeypatch.setattr(
        "atlas.core.validation_runner.impacted_tests", lambda *_, **__: []
    )
    jail = _SpyJail()

    ValidationRunner(
        Path.cwd(), jail_factory=lambda: jail, changed_files=["src/atlas/x.py"],
    ).run()

    assert jail.tools == ["mypy", "pytest"]
    assert jail.pytest_targets() == [["tests/"]]


def test_impacted_tests_roto_no_tumba_la_validacion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La etapa barata es señal, no puerta: si el mapeo revienta se cae con
    elegancia a la suite completa."""

    def _revienta(*_: Any, **__: Any) -> list[str]:
        raise OSError("mapeo roto")

    monkeypatch.setattr("atlas.core.validation_runner.impacted_tests", _revienta)
    jail = _SpyJail()

    report = ValidationRunner(
        Path.cwd(),
        jail_factory=lambda: jail,
        changed_files=["src/atlas/monitoring/prometheus_exporter.py"],
    ).run()

    assert jail.tools == ["mypy", "pytest"]
    assert report.passed is True


# --------------------------------------------------------------------------
# Contrato del informe
# --------------------------------------------------------------------------


def test_to_dict_incluye_la_etapa() -> None:
    jail = _SpyJail({"mypy": 1})
    d = ValidationRunner(Path.cwd(), jail_factory=lambda: jail).run().to_dict()

    assert d["stage"] == "types"
    # los campos que ya consumían el clasificador de causa raíz y el ledger
    assert {"passed", "pytest_exit", "mypy_exit", "duration_s"} <= set(d)


def test_stage_por_defecto_es_full() -> None:
    """Los ~23 sitios de los tests que construyen ValidationReport a mano no
    pueden romperse por un campo nuevo."""
    assert ValidationReport(passed=True, pytest_exit=0, mypy_exit=0).stage == "full"


def test_el_guard_antirecursion_sigue_vivo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Escalonar no puede haberse llevado por delante la protección que evita
    lanzar la suite dentro de la suite. Se deshace el ocultamiento del fixture
    para observar el entorno REAL, que es el caso que debe abortar."""
    import os

    monkeypatch.setattr("atlas.core.validation_runner.os", os)
    assert "PYTEST_CURRENT_TEST" in os.environ

    with pytest.raises(RuntimeError, match="recursiva"):
        ValidationRunner(Path.cwd(), jail_factory=lambda: _SpyJail()).run()
