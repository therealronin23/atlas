"""Single-writer guard de la cadena Merkle (ROADMAP §7).

Origen: 2026-06-12 — un self-audit de 24h sin aislar corrió 15 ciclos contra
la cadena viva junto a ``atlas serve``. El guard convierte ese error
operacional en un fallo de arranque explícito.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from atlas.security.writer_lock import MerkleWriterLock, WriterLockHeld


class TestMerkleWriterLock:
    def test_acquire_writes_holder_diagnostics(self, tmp_path: Path) -> None:
        lock = MerkleWriterLock(tmp_path)
        with lock:
            data = json.loads(lock.path.read_text(encoding="utf-8"))
            assert data["pid"] == os.getpid()
            assert "since" in data

    def test_second_writer_same_workspace_refused(self, tmp_path: Path) -> None:
        first = MerkleWriterLock(tmp_path)
        second = MerkleWriterLock(tmp_path)
        with first:
            with pytest.raises(WriterLockHeld, match=f"PID {os.getpid()}"):
                second.acquire()

    def test_release_allows_next_writer(self, tmp_path: Path) -> None:
        first = MerkleWriterLock(tmp_path)
        first.acquire()
        first.release()
        with MerkleWriterLock(tmp_path):
            pass  # no levanta

    def test_acquire_is_idempotent_for_same_instance(self, tmp_path: Path) -> None:
        lock = MerkleWriterLock(tmp_path)
        with lock:
            lock.acquire()  # no se bloquea a sí mismo
        lock.release()  # release tras release implícito tampoco rompe

    def test_isolated_workspaces_do_not_collide(self, tmp_path: Path) -> None:
        with MerkleWriterLock(tmp_path / "live"), MerkleWriterLock(tmp_path / "audit-home"):
            pass

    def test_deleting_lock_file_does_not_release(self, tmp_path: Path) -> None:
        # El lock vive en el fd, no en el path: borrar el archivo no permite
        # un segundo escritor sobre el mismo inode... pero un open() nuevo crea
        # OTRO inode y sí adquiriría. Documentamos el comportamiento real: el
        # guard protege contra arranques accidentales, no contra sabotaje.
        first = MerkleWriterLock(tmp_path)
        first.acquire()
        first.path.unlink()
        second = MerkleWriterLock(tmp_path)
        second.acquire()  # nuevo inode → adquiere
        second.release()
        first.release()

    def test_lock_released_when_process_dies(self, tmp_path: Path) -> None:
        # Un proceso hijo toma el lock y muere sin release explícito: el
        # kernel lo libera y el padre puede adquirir inmediatamente.
        code = (
            "import sys; sys.path.insert(0, sys.argv[2])\n"
            "from pathlib import Path\n"
            "from atlas.security.writer_lock import MerkleWriterLock\n"
            "MerkleWriterLock(Path(sys.argv[1])).acquire()\n"
        )
        src = str(Path(__file__).resolve().parent.parent / "src")
        subprocess.run(
            [sys.executable, "-c", code, str(tmp_path), src],
            check=True,
            timeout=30,
        )
        with MerkleWriterLock(tmp_path):
            pass  # el hijo murió → lock libre
