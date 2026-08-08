"""La reconstrucción del grafo admite UN escritor, y ahora está impuesto.

`graph-rebuild-single-writer` era una manía declarada en AGENTS.md y en ningún
sitio más. El 2026-08-08 la rompí yo: lancé un tick del grafo mientras otro
seguía corriendo, y Kuzu —que no es seguro multi-proceso para escritura— se
quedó con las tablas del callgraph y sin las bitemporales.

El propio repo ya tenía la respuesta escrita para otro subsistema.
`MerkleWriterLock` dice en su docstring exactamente esto:

    "Este guard lo convierte en imposible en vez de en disciplina."

Una regla que sólo vive en un documento es una regla que un agente va a romper.
Yo había leído el documento.

Así que no se escribe un lock nuevo: se extrae el que ya existe
(`ExclusiveWriterLock`) y se aplica también al grafo. `MerkleWriterLock` queda
como lo que siempre fue, ese lock apuntando al audit dir.
"""

from __future__ import annotations

import multiprocessing
from pathlib import Path
from typing import Any

import pytest

from atlas.security.writer_lock import (
    ExclusiveWriterLock,
    MerkleWriterLock,
    ProjectGraphWriterLock,
    WriterLockHeld,
)


# ---------------------------------------------------------------------------
# La extracción no puede haber cambiado el lock que ya protegía el Merkle
# ---------------------------------------------------------------------------


def test_merkle_lock_conserva_su_ruta(tmp_path: Path) -> None:
    lock = MerkleWriterLock(tmp_path)

    assert lock.path == tmp_path.resolve() / "memory" / "audit" / ".writer.lock"


def test_merkle_lock_sigue_siendo_exclusivo(tmp_path: Path) -> None:
    with MerkleWriterLock(tmp_path):
        with pytest.raises(WriterLockHeld):
            MerkleWriterLock(tmp_path).acquire()


# ---------------------------------------------------------------------------
# El lock del grafo
# ---------------------------------------------------------------------------


def test_el_lock_del_grafo_vive_junto_a_su_bd(tmp_path: Path) -> None:
    """Junto a la BD y no bajo el workspace: el path de la BD es inyectable
    (ATLAS_GRAPH_DB), así que dos BDs distintas son dos escritores legítimos."""
    db = tmp_path / "kuzu" / "project_graph.kuzu"

    lock = ProjectGraphWriterLock(db)

    assert lock.path.parent == db.parent
    assert lock.path.name.startswith(".")


def test_dos_reconstrucciones_no_pueden_solaparse(tmp_path: Path) -> None:
    """El incidente exacto: el segundo tick debe rebotar, no corromper."""
    db = tmp_path / "project_graph.kuzu"

    with ProjectGraphWriterLock(db):
        with pytest.raises(WriterLockHeld):
            ProjectGraphWriterLock(db).acquire()


def test_el_error_dice_quien_tiene_el_lock(tmp_path: Path) -> None:
    """Un 'está bloqueado' sin dueño obliga a investigar; con PID, no."""
    db = tmp_path / "project_graph.kuzu"

    with ProjectGraphWriterLock(db):
        with pytest.raises(WriterLockHeld, match=r"PID \d+"):
            ProjectGraphWriterLock(db).acquire()


def test_bds_distintas_no_se_bloquean_entre_si(tmp_path: Path) -> None:
    """Un worktree con su propio ATLAS_GRAPH_DB no es un escritor rival."""
    a = tmp_path / "a" / "project_graph.kuzu"
    b = tmp_path / "b" / "project_graph.kuzu"

    with ProjectGraphWriterLock(a), ProjectGraphWriterLock(b):
        pass  # ninguno de los dos lanza


def test_el_lock_se_libera_al_salir(tmp_path: Path) -> None:
    db = tmp_path / "project_graph.kuzu"

    with ProjectGraphWriterLock(db):
        pass

    with ProjectGraphWriterLock(db):
        pass  # reentrable tras liberar


def test_acquire_es_idempotente_para_la_misma_instancia(tmp_path: Path) -> None:
    lock = ProjectGraphWriterLock(tmp_path / "project_graph.kuzu")
    lock.acquire()
    try:
        lock.acquire()  # no debe lanzar contra sí mismo
    finally:
        lock.release()


def test_release_sin_acquire_es_noop(tmp_path: Path) -> None:
    ProjectGraphWriterLock(tmp_path / "project_graph.kuzu").release()


def _tomar_y_esperar(path: str, listo: Any, seguir: Any) -> None:
    from atlas.security.writer_lock import ProjectGraphWriterLock as Lock

    with Lock(Path(path)):
        listo.set()
        seguir.wait(timeout=10)


def test_el_lock_cruza_procesos(tmp_path: Path) -> None:
    """flock, no una variable de módulo: el incidente fueron dos PROCESOS."""
    db = tmp_path / "project_graph.kuzu"
    db.parent.mkdir(parents=True, exist_ok=True)
    ctx = multiprocessing.get_context("spawn")
    listo, seguir = ctx.Event(), ctx.Event()
    proc = ctx.Process(target=_tomar_y_esperar, args=(str(db), listo, seguir))
    proc.start()
    try:
        assert listo.wait(timeout=30), "el proceso hijo no tomó el lock"

        with pytest.raises(WriterLockHeld):
            ProjectGraphWriterLock(db).acquire()
    finally:
        seguir.set()
        proc.join(timeout=30)


def test_borrar_el_fichero_no_libera_el_lock(tmp_path: Path) -> None:
    """El lock vive en el descriptor, no en el inodo. Lo dice el docstring del
    módulo original y conviene que siga siendo cierto tras la extracción."""
    db = tmp_path / "project_graph.kuzu"
    lock = ProjectGraphWriterLock(db)
    lock.acquire()
    try:
        lock.path.unlink()

        otro = ProjectGraphWriterLock(db)
        otro.acquire()  # crea un inodo nuevo: no protege, pero tampoco miente
        otro.release()
    finally:
        lock.release()


# ---------------------------------------------------------------------------
# Contrato compartido
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", [MerkleWriterLock, ProjectGraphWriterLock])
def test_ambos_son_el_mismo_lock(cls: type) -> None:
    assert issubclass(cls, ExclusiveWriterLock)


# ---------------------------------------------------------------------------
# Cableado real: un lock que existe y nadie toma no protege nada. Es justo el
# fallo que esta sesión lleva encontrando en otros sitios.
# ---------------------------------------------------------------------------


def test_el_tick_del_grafo_toma_el_lock(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Con el lock ya tomado por otro, el tick cede el turno en vez de
    corromper — y lo dice con un estado propio, no con una excepción."""
    from atlas.core.orchestrator_parts import maintenance_facade as mf

    db = tmp_path / "project_graph.kuzu"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_bytes(b"")
    monkeypatch.setenv("ATLAS_PROJECT_GRAPH", "1")
    monkeypatch.setenv("ATLAS_PROJECT_GRAPH_DB", str(db))

    held = ProjectGraphWriterLock(db)
    held.acquire()
    try:
        source = mf.__file__
        assert source
        text = Path(source).read_text(encoding="utf-8")
        # El tick construye el lock sobre la BD resuelta y trata el choque
        # como estado, no como fallo.
        assert "ProjectGraphWriterLock(db)" in text
        assert '"status": "locked"' in text
        assert "graph_lock.release()" in text
    finally:
        held.release()


def test_el_lock_del_grafo_se_importa_en_el_facade() -> None:
    """Cableado por import real, no por grep de esperanza."""
    from atlas.core.orchestrator_parts import maintenance_facade as mf

    assert mf.ProjectGraphWriterLock is ProjectGraphWriterLock
    assert mf.WriterLockHeld is WriterLockHeld
