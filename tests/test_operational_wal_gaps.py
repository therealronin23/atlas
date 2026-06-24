"""
Tests adicionales para OperationalWAL (ADR-024) — cobertura de los caminos
no cubiertos por test_operational_wal.py existente.

Caminos cubiertos aquí:
  (d) thread safety — escrituras concurrentes no pierden entradas ni corrompen el fichero
  (e) tipos de campo no-string se serializan (int, list, dict)
  (f) write sin kwargs extra produce fields={}
  (g) multiple rotaciones — tras más de una rotación todos los archivos son JSONL válido
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from atlas.logging.operational_wal import OperationalWAL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wal(tmp_path: Path) -> OperationalWAL:
    return OperationalWAL(tmp_path / "wal")


# ---------------------------------------------------------------------------
# (d) Thread safety — escrituras concurrentes
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_writes_no_data_loss(self, tmp_path: Path) -> None:
        """N hilos escriben en paralelo; el total de entradas legibles debe ser N."""
        wal = _wal(tmp_path)
        n_threads = 20
        errors: list[Exception] = []

        def _writer(idx: int) -> None:
            try:
                wal.write("thread", f"msg-{idx}", idx=idx)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=_writer, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Hilos lanzaron excepciones: {errors}"
        entries = wal.tail(n=n_threads * 2)
        assert len(entries) == n_threads, (
            f"Se esperaban {n_threads} entradas, se recuperaron {len(entries)}"
        )

    def test_concurrent_writes_all_valid_json(self, tmp_path: Path) -> None:
        """Las entradas producidas por escrituras concurrentes son JSON válido."""
        wal = _wal(tmp_path)
        n_threads = 15

        threads = [
            threading.Thread(target=wal.write, args=("c", f"t{i}"), kwargs={"v": i})
            for i in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        log_file = tmp_path / "wal" / "operational.jsonl"
        for raw_line in log_file.read_text(encoding="utf-8").splitlines():
            obj = json.loads(raw_line)  # no debe lanzar
            assert "ts" in obj
            assert "message" in obj


# ---------------------------------------------------------------------------
# (e) Tipos de campo no-string se serializan correctamente
# ---------------------------------------------------------------------------


class TestFieldTypeSerialization:
    def test_int_field_preserved(self, tmp_path: Path) -> None:
        wal = _wal(tmp_path)
        wal.write("c", "msg", count=42)
        entry = wal.tail()[0]
        # json.loads deserializa int como int
        assert entry["fields"]["count"] == 42

    def test_list_field_preserved(self, tmp_path: Path) -> None:
        wal = _wal(tmp_path)
        wal.write("c", "msg", items=["a", "b", "c"])
        entry = wal.tail()[0]
        assert entry["fields"]["items"] == ["a", "b", "c"]

    def test_dict_field_preserved(self, tmp_path: Path) -> None:
        wal = _wal(tmp_path)
        wal.write("c", "msg", meta={"k": 1})
        entry = wal.tail()[0]
        assert entry["fields"]["meta"] == {"k": 1}

    def test_none_field_preserved(self, tmp_path: Path) -> None:
        wal = _wal(tmp_path)
        wal.write("c", "msg", val=None)
        entry = wal.tail()[0]
        assert entry["fields"]["val"] is None

    def test_bool_field_preserved(self, tmp_path: Path) -> None:
        wal = _wal(tmp_path)
        wal.write("c", "msg", flag=True)
        entry = wal.tail()[0]
        assert entry["fields"]["flag"] is True


# ---------------------------------------------------------------------------
# (f) write sin kwargs extra produce fields={}
# ---------------------------------------------------------------------------


class TestEmptyFields:
    def test_write_no_extra_kwargs(self, tmp_path: Path) -> None:
        wal = _wal(tmp_path)
        wal.write("comp", "bare-message")
        entry = wal.tail()[0]
        assert entry["fields"] == {}
        assert entry["component"] == "comp"
        assert entry["message"] == "bare-message"


# ---------------------------------------------------------------------------
# (g) Múltiples rotaciones — todos los archivos son JSONL válido
# ---------------------------------------------------------------------------


class TestMultipleRotations:
    def test_two_rotations_produce_valid_archives(self, tmp_path: Path) -> None:
        """Forzar al menos 1 rotación y verificar que todos los archivos rotados
        contienen JSONL válido.

        Nota: la implementación actual usa strftime('%Y%m%d%H%M%S') como sufijo de
        archivo rotado. Si dos rotaciones ocurren dentro del mismo segundo, la segunda
        sobrescribe a la primera (timestamp collision). Por eso este test solo afirma
        que los archivos existentes son válidos, no que haya exactamente N archivos.
        El comportamiento de colisión es un bug conocido reportado separadamente.
        """
        wal = OperationalWAL(tmp_path / "wal")
        wal.MAX_BYTES = 150  # umbral muy pequeño → muchas rotaciones

        for i in range(50):
            wal.write("c", f"entry-{i:04d}-fill")

        wal_dir = tmp_path / "wal"
        archive_files = [
            f for f in wal_dir.iterdir()
            if f.name.startswith("operational.") and f.name != "operational.jsonl"
        ]
        assert len(archive_files) >= 1, (
            f"Se esperaba al menos 1 archivo rotado, se encontraron {len(archive_files)}"
        )
        for arc in archive_files:
            for raw in arc.read_text(encoding="utf-8").splitlines():
                if raw.strip():
                    obj = json.loads(raw)  # no debe lanzar
                    assert "component" in obj

    def test_entries_recoverable_after_multiple_rotations(self, tmp_path: Path) -> None:
        """tail() sobre el archivo activo funciona aunque haya habido rotaciones."""
        wal = OperationalWAL(tmp_path / "wal")
        wal.MAX_BYTES = 150

        for i in range(30):
            wal.write("c", f"m{i}")

        # tail() lee solo el archivo activo — debe haber al menos 1 entrada
        entries = wal.tail(n=100)
        assert len(entries) >= 1
