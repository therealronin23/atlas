"""Los dos solvers del banco, y por qué son dos.

`AtlasSolver` usa el motor real de Atlas (`ToolCoder`: infer -> edit -> test, con
sus lecciones, su contexto institucional y sus reintentos).
`DirectModelSolver` da el mismo problema a un modelo desnudo vía `InferenceHub`,
sin ninguna de esas capas.

La comparación es el resultado. **La diferencia entre ambos mide lo que aporta
el harness de Atlas**, y es una pregunta abierta con un indicio incómodo: el
lazo lleva un 7,8% de aceptación end-to-end frente al 35-50% del campo. Si el
modelo desnudo puntúa igual o más, el andamio no está sumando.

Estos tests no gastan un token: el hub y el coder se inyectan. Lo que fijan es
el CONTRATO — qué se le entrega al solver, qué no, y que un fallo de un
proveedor no se confunda con un defecto sin resolver.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atlas.core.self_maintenance.fitness_solvers import AtlasSolver, DirectModelSolver
from atlas.core.self_maintenance.frozen_defects import FrozenDefect


def _defect(**kw: Any) -> FrozenDefect:
    base: dict[str, Any] = {
        "id": "abc123",
        # Redactados por el scorer antes de llegar aquí; se fijan vacíos a
        # propósito para que un solver que los use falle en test, no en producción.
        "fix_sha": "",
        "base_sha": "deadbeef",
        "subject": "",
        "subsystem": "watchdog",
        "test_files": ("tests/test_watchdog.py",),
        "test_patch": "",
        "verified": True,
    }
    base.update(kw)
    return FrozenDefect(**base)


class _FakeCoder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def code(self, task: str, context_files: list[str], test_cmd: list[str], **kw: Any) -> Any:
        self.calls.append({"task": task, "context_files": context_files,
                           "test_cmd": test_cmd, **kw})

        class _R:
            success = True
            error = ""
        return _R()


class _FakeHub:
    def __init__(self, text: str = "", success: bool = True) -> None:
        self.text = text
        self.success = success
        self.requests: list[Any] = []

    def infer(self, request: Any) -> Any:
        self.requests.append(request)

        class _R:
            pass
        r = _R()
        r.text = self.text
        r.success = self.success
        r.error = "" if self.success else "proveedor caído"
        return r


# --------------------------------------------------------------------------
# AtlasSolver — el motor real
# --------------------------------------------------------------------------


def test_atlas_pide_poner_en_verde_los_tests_del_defecto(tmp_path: Path) -> None:
    coder = _FakeCoder()
    AtlasSolver(coder_factory=lambda _: coder)(tmp_path, _defect())

    call = coder.calls[0]
    assert "tests/test_watchdog.py" in " ".join(call["test_cmd"])
    assert "tests/test_watchdog.py" in call["task"]


def test_atlas_no_filtra_nada_del_arreglo(tmp_path: Path) -> None:
    """Aunque el defecto llegara con `subject` (no debería: el scorer lo
    redacta), el solver no puede incorporarlo al prompt."""
    coder = _FakeCoder()
    fuga = _defect(subject="fix(watchdog): usar NRestarts en vez de is-active")

    AtlasSolver(coder_factory=lambda _: coder)(tmp_path, fuga)

    texto = coder.calls[0]["task"] + " ".join(coder.calls[0]["context_files"])
    assert "NRestarts" not in texto
    assert "is-active" not in texto


def test_atlas_trabaja_sobre_el_worktree_no_sobre_el_repo(tmp_path: Path) -> None:
    """Un solver que edite el checkout vivo del operador sería catastrófico."""
    visto: list[Path] = []
    AtlasSolver(coder_factory=lambda root: visto.append(root) or _FakeCoder())(
        tmp_path, _defect()
    )

    assert visto == [tmp_path]


def test_atlas_no_lanza_si_el_coder_revienta(tmp_path: Path) -> None:
    """Puntuar 19 defectos no puede caerse por uno."""

    class _Roto:
        def code(self, *a: Any, **k: Any) -> Any:
            raise RuntimeError("proveedor sin crédito")

    AtlasSolver(coder_factory=lambda _: _Roto())(tmp_path, _defect())  # no lanza


# --------------------------------------------------------------------------
# DirectModelSolver — el modelo desnudo
# --------------------------------------------------------------------------


def test_directo_escribe_el_fichero_que_devuelve_el_modelo(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "w.py").write_text("def f():\n    return 1\n")
    respuesta = (
        "Voy a arreglarlo.\n"
        "```python:src/w.py\n"
        "def f():\n    return 2\n"
        "```\n"
    )

    DirectModelSolver(hub=_FakeHub(respuesta))(tmp_path, _defect())

    assert (tmp_path / "src" / "w.py").read_text() == "def f():\n    return 2\n"


def test_directo_no_escribe_fuera_del_worktree(tmp_path: Path) -> None:
    """Un path traversal en la respuesta del modelo no puede salir del jaulón."""
    (tmp_path / "src").mkdir()
    fuera = tmp_path.parent / "VICTIMA.txt"
    respuesta = f"```python:../{fuera.name}\nborrado\n```\n"

    DirectModelSolver(hub=_FakeHub(respuesta))(tmp_path, _defect())

    assert not fuera.exists()


def test_directo_solo_toca_ficheros_de_codigo(tmp_path: Path) -> None:
    """Escribir en `tests/` sería resolver el defecto cambiando el examen."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_watchdog.py").write_text("original\n")
    respuesta = "```python:tests/test_watchdog.py\nassert True\n```\n"

    DirectModelSolver(hub=_FakeHub(respuesta))(tmp_path, _defect())

    assert (tmp_path / "tests" / "test_watchdog.py").read_text() == "original\n"


def test_directo_sin_bloque_de_codigo_no_hace_nada(tmp_path: Path) -> None:
    DirectModelSolver(hub=_FakeHub("No sé cómo arreglarlo."))(tmp_path, _defect())
    # no lanza y no crea nada
    assert list(tmp_path.iterdir()) == []


def test_directo_no_lanza_si_el_proveedor_falla(tmp_path: Path) -> None:
    DirectModelSolver(hub=_FakeHub("", success=False))(tmp_path, _defect())


def test_directo_acota_el_gasto(tmp_path: Path) -> None:
    """19 defectos x 2 solvers con tokens reales: el tope va en el código, no
    en la buena voluntad."""
    hub = _FakeHub("")
    DirectModelSolver(hub=hub, max_tokens=333)(tmp_path, _defect())

    assert hub.requests[0].max_tokens == 333


def test_el_presupuesto_no_ahoga_a_un_modelo_de_razonamiento(tmp_path: Path) -> None:
    """Medido el 2026-08-09: con 2048, `groq_qwen3` devolvió 6.929 caracteres
    TODOS dentro de un `<think>` sin cerrar y cero bloques de código. El
    resultado `0/3` no medía al modelo, medía este fichero. Es el mismo bug que
    el Cónclave ya había pagado (`_REVIEW_MAX_TOKENS = 4096`)."""
    from atlas.core.self_maintenance.fitness_solvers import DEFAULT_MAX_TOKENS

    hub = _FakeHub("")
    DirectModelSolver(hub=hub)(tmp_path, _defect())

    assert DEFAULT_MAX_TOKENS >= 4096
    assert hub.requests[0].max_tokens >= 4096


def test_el_razonamiento_no_tapa_el_codigo(tmp_path: Path) -> None:
    """Un modelo que piensa en voz alta y LUEGO responde debe funcionar: el
    bloque va detrás del `<think>`."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "w.py").write_text("viejo\n")
    respuesta = (
        "<think>Veamos, el test espera 2 y devuelve 1, hay que cambiarlo.</think>\n"
        "```python:src/w.py\nnuevo\n```\n"
    )

    DirectModelSolver(hub=_FakeHub(respuesta))(tmp_path, _defect())

    assert (tmp_path / "src" / "w.py").read_text() == "nuevo\n"


def test_un_think_sin_cerrar_no_vacia_la_respuesta(tmp_path: Path) -> None:
    """Si el modelo se quedó sin presupuesto a mitad, mejor texto ruidoso que
    nada — mismo criterio que `deliberation_council._strip_thinking`."""
    from atlas.core.self_maintenance.fitness_solvers import _strip_thinking

    assert _strip_thinking("<think>me quedé a mitad").startswith("<think>")


def test_directo_recibe_el_test_que_debe_pasar(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_watchdog.py").write_text("def test_x():\n    assert 0\n")
    hub = _FakeHub("")

    DirectModelSolver(hub=hub)(tmp_path, _defect())

    assert "test_watchdog.py" in hub.requests[0].prompt


def test_ambos_cumplen_el_tipo_Solver() -> None:
    """Deben ser intercambiables en `FitnessScorer.score(solve=...)`."""
    for solver in (AtlasSolver(), DirectModelSolver(hub=_FakeHub())):
        assert callable(solver)
