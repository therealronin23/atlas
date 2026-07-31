"""`reproduction.py` no podía reproducir NADA en un venv (F1.3, 2026-07-31).

Medido con una ejecución real contra `BwrapJail`, no deducido: reproducir un
test que pasa devolvía `FAILED`, `exit=1`, en 64 ms, con
``/usr/bin/python3.12: No module named pytest`` en stderr.

Causa exacta:

- `sys.executable` es ``<repo>/.venv/bin/python``; el código le aplicaba
  ``Path(...).resolve()``, que sigue el symlink hasta ``/usr/bin/python3.12``
  y **se sale del virtualenv**.
- `_runtime_paths()` monta `sys.prefix` (el venv, donde SÍ está pytest) pero
  descarta `sys.base_prefix` cuando es ``/usr``. El intérprete resuelto ya no
  mira el venv, así que no encuentra pytest aunque esté montado.

El resultado es la peor clase de fallo para un reproductor: no dice "no puedo",
dice **FAILED con confianza**. Cableado tal cual, habría marcado como
"reproducido fallando" absolutamente todo.

Por qué los 1.868 loc de tests del paquete no lo cazaron: `EngineeringReproductionRunner`
acepta ``jail=`` inyectable y los tests le pasan un jail falso, así que la ruta
real con `BwrapJail` nunca se ejecutó. Misma lección que ADC-WO-108 — tests en
verde no son evidencia de que algo funcione.
"""

from __future__ import annotations

import sys
from pathlib import Path

from atlas.engineering.reproduction import EngineeringReproductionRunner


class _Worktrees:
    def session(self, name: str, *, base_ref: str = "HEAD"):  # pragma: no cover
        raise AssertionError("no debe usarse en este test")


class _Audit:
    def log(self, *args: object, **kwargs: object):  # pragma: no cover
        raise AssertionError("no debe usarse en este test")


def _runner(tmp_path: Path) -> EngineeringReproductionRunner:
    return EngineeringReproductionRunner(
        repo_root=tmp_path, worktrees=_Worktrees(), audit=_Audit()
    )


class TestInterpreterStaysInsideTheVirtualenv:
    def test_the_command_interpreter_is_not_resolved_out_of_the_venv(
        self, tmp_path: Path
    ) -> None:
        """`.resolve()` sobre `sys.executable` rompe el venv: en un venv
        estándar `bin/python` es un symlink al intérprete del sistema, y
        seguirlo pierde el `site-packages` donde vive pytest."""
        from atlas.engineering.reproduction import EngineeringReproductionRequest

        runner = _runner(tmp_path)
        request = EngineeringReproductionRequest(
            run_id="run-1", task_id=None, mission_id=None, repository="atlas-core",
            base_revision="a" * 40, candidate_revision="b" * 40,
            correlation_id="corr-1", test_targets=("tests/test_x.py",),
            at="2026-07-31T00:00:00+00:00",
        )

        command = runner._validate_and_build_command(request)

        assert command[0] == sys.executable

    def test_the_venv_prefix_is_mounted_so_the_interpreter_finds_its_packages(
        self,
    ) -> None:
        # Complemento del anterior: de nada sirve no resolver el intérprete si
        # su prefix no está montado dentro del jail.
        paths = EngineeringReproductionRunner._runtime_paths()

        assert Path(sys.prefix).resolve() in paths
