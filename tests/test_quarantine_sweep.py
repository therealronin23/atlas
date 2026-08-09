"""La cuarentena MCP deja de crecer sin política.

`workspace/mcp/quarantine/` son 583 MB de código de terceros descargado por el
pipeline de vetting (ADR-075/076): 207 candidatos, uno solo de 393 MB. Medido
el 2026-08-09, **todos** tienen mtime entre 14 y 30 días y ninguno se ha tocado
desde: es la campaña de julio, terminada.

No tenía dueño en el código. El `quarantine` de `mcp/registry.py` es un set en
memoria con nombres de servidor; el directorio de disco no lo gestionaba nadie
y no tenía retención.

Se reusa el idioma exacto de `SelfBuildRunner.sweep_stale_worktrees`: TTL por
mtime, y un candidato EN VUELO tiene mtime fresco y queda protegido. Sin
`atime`: con `relatime` esa señal miente — los 207 aparecían "accedidos hace
horas" sólo porque un `du` los recorrió.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from atlas.mcp.quarantine_sweep import QuarantineSweep, sweep_quarantine


@pytest.fixture
def quarantine(tmp_path: Path) -> Path:
    q = tmp_path / "quarantine"
    q.mkdir()
    for name, edad_dias in (("viejo-a", 40), ("viejo-b", 31), ("reciente", 1)):
        d = q / name
        d.mkdir()
        (d / "server.py").write_text("x" * 100)
        antiguo = time.time() - edad_dias * 86400
        os.utime(d / "server.py", (antiguo, antiguo))
        os.utime(d, (antiguo, antiguo))
    return q


# --------------------------------------------------------------------------
# El criterio
# --------------------------------------------------------------------------


def test_barre_lo_viejo_y_respeta_lo_reciente(quarantine: Path) -> None:
    result = sweep_quarantine(quarantine, ttl_days=30)

    assert sorted(result.removed) == ["viejo-a", "viejo-b"]
    assert (quarantine / "reciente").exists()
    assert not (quarantine / "viejo-a").exists()


def test_un_candidato_en_vuelo_queda_protegido(quarantine: Path) -> None:
    """mtime de AHORA = alguien está escribiendo en él. Mismo seguro que
    `sweep_stale_worktrees`. Se prueba con un TTL agresivo: ni así se toca."""
    en_vuelo = quarantine / "descargando-ahora"
    en_vuelo.mkdir()
    (en_vuelo / "parcial.tar").write_text("...")

    result = sweep_quarantine(quarantine, ttl_days=0.001)

    assert "descargando-ahora" not in result.removed
    assert en_vuelo.exists()
    # y el resto sí se barre: el TTL agresivo estaba activo de verdad
    assert "viejo-a" in result.removed


def test_dry_run_no_borra_nada(quarantine: Path) -> None:
    """Sobre 583 MB de terceros, poder ver qué se llevaría ANTES de llevárselo
    no es un lujo."""
    result = sweep_quarantine(quarantine, ttl_days=30, dry_run=True)

    assert sorted(result.removed) == ["viejo-a", "viejo-b"]
    assert (quarantine / "viejo-a").exists()
    assert result.dry_run is True


def test_declara_cuanto_libera(quarantine: Path) -> None:
    result = sweep_quarantine(quarantine, ttl_days=30, dry_run=True)

    assert result.freed_bytes > 0
    assert result.inspected == 3


def test_ttl_alto_no_barre_nada(quarantine: Path) -> None:
    assert sweep_quarantine(quarantine, ttl_days=999).removed == []


# --------------------------------------------------------------------------
# Seguridad: es material de TERCEROS y un borrado mal apuntado duele
# --------------------------------------------------------------------------


def test_solo_toca_directorios_hijos_directos(quarantine: Path) -> None:
    """Un fichero suelto en la raíz de la cuarentena no es un candidato."""
    suelto = quarantine / "notas.json"
    suelto.write_text("{}")
    antiguo = time.time() - 99 * 86400
    os.utime(suelto, (antiguo, antiguo))

    result = sweep_quarantine(quarantine, ttl_days=30)

    assert suelto.exists()
    assert "notas.json" not in result.removed


def test_no_sigue_symlinks_fuera(tmp_path: Path) -> None:
    """Un symlink viejo apuntando fuera no puede arrastrar a su destino."""
    q = tmp_path / "quarantine"
    q.mkdir()
    fuera = tmp_path / "importante"
    fuera.mkdir()
    (fuera / "dato.txt").write_text("no me borres")
    enlace = q / "enlace"
    enlace.symlink_to(fuera, target_is_directory=True)
    antiguo = time.time() - 99 * 86400
    os.utime(enlace, (antiguo, antiguo), follow_symlinks=False)

    sweep_quarantine(q, ttl_days=30)

    assert (fuera / "dato.txt").exists()


def test_directorio_inexistente_no_lanza(tmp_path: Path) -> None:
    result = sweep_quarantine(tmp_path / "no-existe", ttl_days=30)

    assert result.removed == []
    assert result.reason


def test_es_serializable(quarantine: Path) -> None:
    import json

    d = json.loads(json.dumps(sweep_quarantine(quarantine, ttl_days=30, dry_run=True).to_dict()))

    assert {"removed", "freed_bytes", "inspected", "dry_run", "reason"} <= set(d)


def test_dataclass_por_defecto() -> None:
    assert QuarantineSweep().removed == []


def test_esta_cableado_al_tick_que_de_verdad_corre() -> None:
    """Un barrido que existe y nadie invoca no libera nada — el fallo que esta
    auditoría lleva encontrando por todas partes.

    Cuelga del tick de TRIAL y no del de vetting, que sería su sitio natural:
    el de vetting es opt-in y hoy está apagado en el daemon, así que ahí no
    correría nunca. La higiene no puede depender de que esté encendido lo que
    ensucia.
    """
    from atlas.core.orchestrator_parts import maintenance_facade as mf

    source = Path(str(mf.__file__)).read_text(encoding="utf-8")
    trial = source.split("def maintenance_mcp_trial_tick")[1].split("def maintenance_")[0]
    assert "sweep_quarantine" in trial
    assert "mcp.quarantine_swept" in trial
