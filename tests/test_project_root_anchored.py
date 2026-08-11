"""t16: la raíz del proyecto en producción cuelga de un hilo que no está aquí.

`MaintenanceFacade._project_root()` es `ATLAS_CORE_ROOT` **o `Path.cwd()`**, y
de esa ruta salen 47 usos: `workspace/self_build/*.json`,
`workspace/research/state.json`, `workspace/mcp/*`, `workspace/lessons`,
`docs/design/mcp_catalog_*.yaml`, los informes de investigación… Casi todo el
estado que el daemon escribe.

Medido el 2026-08-11, y es la parte incómoda: la unidad systemd **no** define
`ATLAS_CORE_ROOT`. Define `WorkingDirectory=/home/ronin/proyectos/atlas-core`,
y por eso funciona. O sea, en producción la raíz se resuelve por el respaldo
del cwd, y lo que la mantiene correcta es una directiva de systemd que vive
FUERA del repositorio y que nada comprueba.

Funciona hoy. Lo que no había es nada que se enterase si dejara de funcionar:
borra esa línea de la unidad y el daemon empieza a escribir su estado en
`$HOME` sin un solo error — el mismo perfil que t15, donde un informe se
escribió en el repo y su auditoría fue a parar a otro sitio.

Este fichero no cambia el comportamiento (hacerlo lanzar rompería los tests
que usan raíces temporales, que es legítimo). Fija lo que hay y avisa cuando
el anclaje desaparece.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from atlas.core.orchestrator_parts.maintenance_facade import MaintenanceFacade

REPO = Path(__file__).resolve().parent.parent
UNIDAD = Path.home() / ".config" / "systemd" / "user" / "atlas-core.service"


# ---------------------------------------------------------------------------
# El comportamiento, fijado
# ---------------------------------------------------------------------------


def test_ATLAS_CORE_ROOT_gana_al_directorio_actual(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))
    assert MaintenanceFacade._project_root() == tmp_path.resolve()


def test_sin_la_variable_la_raiz_ES_el_directorio_actual(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Esto es el respaldo del que depende producción. Se fija para que quede
    escrito que es una decisión y no un accidente."""
    monkeypatch.delenv("ATLAS_CORE_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    assert MaintenanceFacade._project_root() == tmp_path.resolve()


def test_la_raiz_se_resuelve_y_expande(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`~` y los enlaces se normalizan: dos rutas equivalentes no pueden
    producir dos árboles de estado distintos."""
    monkeypatch.setenv("ATLAS_CORE_ROOT", f"{tmp_path}/./")
    assert MaintenanceFacade._project_root() == tmp_path.resolve()


# ---------------------------------------------------------------------------
# El anclaje de producción
# ---------------------------------------------------------------------------


def _ancla(texto: str) -> bool:
    """¿Este texto de unidad fija la raíz de alguna de las dos formas?

    Aislado del fichero real para poder verificarlo por mutación: la unidad
    del operador es configuración de SU sistema y no se toca ni para probar.
    """
    return "ATLAS_CORE_ROOT=" in texto or "WorkingDirectory=" in texto


def test_el_detector_de_anclaje_distingue_los_tres_casos() -> None:
    """Sin esto, un detector que devolviera siempre True pasaría el test de
    abajo en cualquier máquina."""
    assert _ancla("Environment=ATLAS_CORE_ROOT=/x")
    assert _ancla("WorkingDirectory=/x")
    assert not _ancla("ExecStart=/x/bin/atlas serve\nEnvironment=ATLAS_RESEARCH=1")


@pytest.mark.skipif(
    not UNIDAD.is_file(),
    reason="no hay unidad systemd en esta máquina: nada que anclar aquí",
)
def test_la_unidad_del_daemon_ancla_la_raiz_de_alguna_forma() -> None:
    """El daemon escribe su estado bajo la raíz resuelta. Si la unidad no
    define `ATLAS_CORE_ROOT` **ni** `WorkingDirectory`, ese estado se va a
    donde systemd deje el cwd (`$HOME` por defecto) sin un solo error.

    Se aceptan las dos formas a propósito: pedir sólo `ATLAS_CORE_ROOT` sería
    inventar un requisito que la instalación actual no cumple y que funciona.
    Lo que no se acepta es ninguna de las dos.
    """
    texto = UNIDAD.read_text(encoding="utf-8")
    extra = UNIDAD.parent / "atlas-core.service.d"
    if extra.is_dir():
        for conf in sorted(extra.glob("*.conf")):
            texto += "\n" + conf.read_text(encoding="utf-8")

    assert _ancla(texto), (
        "la unidad del daemon no fija ATLAS_CORE_ROOT ni WorkingDirectory: el "
        "estado del daemon (workspace/self_build, workspace/research, "
        "workspace/lessons, los informes de investigación) acabaría fuera del "
        "repositorio sin que nada avise"
    )


@pytest.mark.skipif(
    not UNIDAD.is_file(),
    reason="no hay unidad systemd en esta máquina",
)
def test_si_ancla_por_cwd_ese_cwd_es_un_repositorio_atlas() -> None:
    """Anclar por `WorkingDirectory` sólo vale si ese directorio ES el repo.
    Apuntarlo a otro sitio pasaría el test de arriba y seguiría estando mal."""
    texto = UNIDAD.read_text(encoding="utf-8")
    linea = next(
        (l for l in texto.splitlines() if l.strip().startswith("WorkingDirectory=")),
        None,
    )
    if linea is None:
        pytest.skip("ancla por ATLAS_CORE_ROOT, no por cwd")
    destino = Path(os.path.expanduser(linea.split("=", 1)[1].strip()))
    assert (destino / "pyproject.toml").is_file(), (
        f"WorkingDirectory={destino} no parece un repositorio Atlas"
    )
    assert (destino / "src" / "atlas").is_dir()
