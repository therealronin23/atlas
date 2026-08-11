"""`atlas reality` sabía si el daemon está VIVO; no si ejecuta lo que hay.

`daemon_state` nació para cerrar el agujero de las 23 h: un daemon muerto con
el informe en verde. Queda el agujero de al lado, que este repositorio ha
pisado varias veces con otro nombre — *committed is not running*.

Medido el 2026-08-11: el daemon llevaba **10 h 50 min** en pie, arrancado a
las 08:17, y los arreglos de esa tarde (13:59 en adelante) NO estaban en él —
entre ellos el lock del tick de investigación y el rastro de sobrescritura de
t15. El tick de la madrugada siguiente habría corrido la versión vieja, sin
lock y sin rastro, y `atlas reality` habría dicho `active: True` con toda la
razón y ninguna utilidad.

Un proceso vivo no es un proceso al día. Ahora se distingue.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from atlas.core import reality_live


class _Resultado:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.returncode = 0


def _runner(respuestas: dict[str, str]):
    """Runner falso que responde por el primer argumento reconocido."""
    def run(cmd, **_kw: Any) -> _Resultado:
        for clave, valor in respuestas.items():
            if clave in cmd:
                return _Resultado(valor)
        return _Resultado("")
    return run


@pytest.fixture
def fuentes(tmp_path: Path) -> Path:
    raiz = tmp_path / "atlas"
    (raiz / "core").mkdir(parents=True)
    (raiz / "core" / "algo.py").write_text("x = 1\n", encoding="utf-8")
    return raiz


def _monotonico_de(epoch: float) -> str:
    """El valor que systemd daría para un proceso arrancado en ese epoch."""
    with open("/proc/uptime", encoding="utf-8") as fh:
        uptime = float(fh.read().split()[0])
    arranque_maquina = time.time() - uptime
    return str(int(max(1.0, epoch - arranque_maquina) * 1_000_000))


# ---------------------------------------------------------------------------
# La distinción
# ---------------------------------------------------------------------------


def test_codigo_mas_nuevo_que_el_proceso_es_CODIGO_VIEJO(fuentes: Path) -> None:
    """El caso real del 2026-08-11: proceso de hace horas, fuentes de hace
    minutos."""
    hace_dos_horas = time.time() - 7200
    stale, motivo = reality_live._code_is_stale(
        "atlas-core.service",
        runner=_runner({"show": _monotonico_de(hace_dos_horas)}),
        src_root=fuentes,
    )

    assert stale is True
    assert "código VIEJO" in motivo
    # El motivo tiene que decir QUÉ HACER, no sólo que pasa algo.
    assert "systemctl --user restart" in motivo
    # Y cuánto: sin la magnitud no se distingue "recién commiteado" de "lleva
    # días desactualizado".
    assert "min más nuevas" in motivo


def test_proceso_mas_nuevo_que_el_codigo_esta_al_dia(fuentes: Path) -> None:
    reciente = time.time() + 5  # arrancado después de tocar las fuentes
    stale, motivo = reality_live._code_is_stale(
        "atlas-core.service",
        runner=_runner({"show": _monotonico_de(reciente)}),
        src_root=fuentes,
    )

    assert stale is False
    assert "código de disco" in motivo


# ---------------------------------------------------------------------------
# Fail-honest: lo que no se puede medir es None, nunca False
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("salida", ["", "   ", "no-es-un-numero", "0", "-1"])
def test_sin_marca_de_arranque_legible_la_respuesta_es_DESCONOCIDA(
    fuentes: Path, salida: str
) -> None:
    stale, motivo = reality_live._code_is_stale(
        "atlas-core.service", runner=_runner({"show": salida}), src_root=fuentes,
    )

    assert stale is None, "«no lo sé» no puede leerse como «está al día»"
    assert "DESCONOCIDA" in motivo


def test_sin_arbol_de_fuentes_la_respuesta_es_DESCONOCIDA(tmp_path: Path) -> None:
    """El daemon puede correr desde otro checkout; mirar el nuestro y decir
    «al día» sería inventarse la respuesta."""
    stale, _ = reality_live._code_is_stale(
        "atlas-core.service",
        runner=_runner({"show": _monotonico_de(time.time() - 60)}),
        src_root=tmp_path / "no-existe",
    )

    assert stale is None


def test_el_mtime_ignora_los_pycache(fuentes: Path) -> None:
    """`__pycache__` se reescribe al importar, así que contarlo haría que un
    daemon recién arrancado se declarase a sí mismo desactualizado."""
    cache = fuentes / "core" / "__pycache__"
    cache.mkdir()
    trampa = cache / "algo.cpython-312.py"
    trampa.write_text("x", encoding="utf-8")
    import os

    futuro = time.time() + 10_000
    os.utime(trampa, (futuro, futuro))

    reciente = reality_live._newest_source_mtime(fuentes)
    assert reciente is not None and reciente < futuro


# ---------------------------------------------------------------------------
# Integración con daemon_state
# ---------------------------------------------------------------------------


def test_daemon_state_expone_code_stale_cuando_esta_activo() -> None:
    estado = reality_live.daemon_state(
        runner=_runner({"is-active": "active\n", "show": "1"}),
    )

    assert estado["active"] is True
    assert "code_stale" in estado, (
        "sin esta clave, un daemon vivo con código de ayer sigue reportándose "
        "como sano"
    )


def test_un_daemon_caido_no_afirma_nada_sobre_su_codigo() -> None:
    estado = reality_live.daemon_state(runner=_runner({"is-active": "failed\n"}))

    assert estado["active"] is False
    assert estado["code_stale"] is None


def test_sin_systemctl_sigue_siendo_desconocido_y_no_falso() -> None:
    def revienta(*_a: Any, **_k: Any):
        raise OSError("no hay systemctl")

    estado = reality_live.daemon_state(runner=revienta)

    assert estado["active"] is None
    assert "DESCONOCIDO" in estado["reason"]


# ---------------------------------------------------------------------------
# t20: la consecuencia — `behind_head` degrada el informe, `code_stale` no
# ---------------------------------------------------------------------------


def test_behind_head_se_enciende_con_un_commit_mas_nuevo_que_el_proceso(
    tmp_path: Path,
) -> None:
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    for cmd in (["init"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, capture_output=True)
    (repo / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "x"], check=True, capture_output=True
    )

    atrasado, motivo = reality_live._behind_head(
        "atlas-core.service",
        runner=_runner({"show": _monotonico_de(time.time() - 3600)}),
        repo_root=repo,
    )
    assert atrasado is True
    assert "NO se está ejecutando" in motivo


def test_behind_head_es_None_si_no_hay_repo_git(tmp_path: Path) -> None:
    atrasado, motivo = reality_live._behind_head(
        "atlas-core.service",
        runner=_runner({"show": _monotonico_de(time.time() - 60)}),
        repo_root=tmp_path / "no-es-repo",
    )
    assert atrasado is None
    assert motivo == ""


def test_el_informe_se_DEGRADA_con_el_daemon_atrasado() -> None:
    """La consecuencia que pedía t20: la cabecera deja de decir OK sin que
    nadie tenga que leer el JSON entero."""
    from atlas.core.reality import _overall_status

    assert _overall_status({"daemon": {"active": True, "behind_head": True}}) == "degraded"


def test_editar_un_fichero_NO_degrada_el_informe() -> None:
    """`code_stale` es información, no alarma. Si degradase, sonaría durante
    todo el desarrollo y acabaría ignorada — que es como se pierde una alarma
    útil."""
    from atlas.core.reality import _overall_status

    estado = {"daemon": {"active": True, "code_stale": True, "behind_head": False}}
    assert _overall_status(estado) == "ok"


def test_un_daemon_al_dia_no_degrada_nada() -> None:
    from atlas.core.reality import _overall_status

    estado = {"daemon": {"active": True, "code_stale": False, "behind_head": False}}
    assert _overall_status(estado) == "ok"


def test_no_saber_no_degrada() -> None:
    """Fail-honest hasta en la consecuencia: `None` no es una avería."""
    from atlas.core.reality import _overall_status

    estado = {"daemon": {"active": True, "code_stale": None, "behind_head": None}}
    assert _overall_status(estado) == "ok"
