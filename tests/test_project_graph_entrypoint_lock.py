"""El entrypoint del grafo cede el turno de VERDAD, no sólo nombra el lock.

`tests/test_authority_memory_owners.py` comprueba que todo módulo que llama a
una función escritora del grafo **menciona** `ProjectGraphWriterLock`. Eso caza
al que se olvide de tomarlo, y es barato. Pero mencionar no es tomar: una
aproximación de la puerta no es la puerta, que es exactamente el defecto que
este arreglo corrigió (el lock existía... en el otro llamante).

Aquí se ejecuta el entrypoint real como proceso aparte con el lock ya tomado
por otro, y se comprueba que **sale sin escribir nada**.

Es rápido a propósito y no por suerte: con el lock ocupado, el entrypoint sale
ANTES de construir el grafo. Si algún día alguien mueve la toma del lock
detrás de la construcción, este test pasará de milisegundos a minutos — y esa
lentitud sería la señal, además del riesgo.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from atlas.security.writer_lock import ProjectGraphWriterLock

REPO = Path(__file__).resolve().parent.parent


def _entrypoint(db: Path, repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable, "-m", "atlas.memory.project_graph",
            str(repo), "--db", str(db), "--commits", "1",
        ],
        cwd=REPO,
        env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin", "HOME": str(repo)},
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_con_el_lock_tomado_el_entrypoint_se_niega(tmp_path: Path) -> None:
    db = tmp_path / "grafo.kuzu"
    otro = ProjectGraphWriterLock(db)
    otro.acquire()
    try:
        resultado = _entrypoint(db, tmp_path)
    finally:
        otro.release()

    assert resultado.returncode != 0, resultado.stdout[:400]
    salida = resultado.stdout + resultado.stderr
    assert "grafo ocupado" in salida
    # El mensaje tiene que decir QUIÉN lo tiene: sin el PID, el operador no
    # sabe a qué proceso mirar.
    assert "PID" in salida
    # Y no ha escrito nada: cede el turno antes de tocar la BD.
    assert not db.exists(), "creó la BD pese a no tener el turno"


def test_el_lock_se_libera_y_el_siguiente_ya_no_se_niega(tmp_path: Path) -> None:
    """Solaparse es un turno, no una avería: en cuanto el otro suelta, este
    entra. Sin esto, un lock que nunca liberase pasaría el test de arriba."""
    db = tmp_path / "grafo.kuzu"
    otro = ProjectGraphWriterLock(db)
    otro.acquire()
    otro.release()

    lock = ProjectGraphWriterLock(db)
    lock.acquire()  # no lanza
    lock.release()


@pytest.mark.parametrize("veces", [2])
def test_tomar_el_lock_es_idempotente_para_el_mismo_dueno(
    tmp_path: Path, veces: int
) -> None:
    """`acquire()` dos veces sobre la MISMA instancia no puede bloquearse a sí
    misma; es lo que permite envolver sin llevar la cuenta."""
    lock = ProjectGraphWriterLock(tmp_path / "grafo.kuzu")
    for _ in range(veces):
        lock.acquire()
    lock.release()
