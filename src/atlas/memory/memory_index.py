"""
Atlas Core — SqliteMemoryIndex: índice persistente genérico (MOTOR, agnóstico).

Vista materializada en SQLite (stdlib) que persiste los embeddings de cualquier
`MemoryRecord` para no re-embeber en cada arranque, y enlaza cada fila a su hoja
Merkle (`merkle_leaf_*`) — cimiento de la capa-moat 1 (procedencia verificable).

Este es el motor de dominio neutro. La memoria inmune de ciberseguridad
(`SqliteLessonIndex`) lo COMPONE adaptando `Lesson` → `MemoryRecord`. El motor no
conoce lecciones, stances ni Garak.

Decisión (regla 6, stdlib > deps): NO `sqlite-vec`. Coseno en Python con la misma
matemática que `LessonRecaller` (se reutiliza `_cosine_similarity`) → scores
idénticos. El valor es persistencia + enlace Merkle, no velocidad.
"""

from __future__ import annotations

import sqlite3
import struct
from collections.abc import Iterable
from pathlib import Path

from atlas.immunity.lesson_recaller import RecallResult, _cosine_similarity
from atlas.memory.embeddings import Embedder, StubEmbedder
from atlas.memory.record import MemoryRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    ordinal           INTEGER PRIMARY KEY AUTOINCREMENT,
    id                TEXT UNIQUE NOT NULL,
    text              TEXT NOT NULL,
    vector            BLOB NOT NULL,
    merkle_leaf_hash  TEXT,
    merkle_leaf_index INTEGER,
    created_at        TEXT
);
"""


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}d", *vec)


def _unpack(blob: bytes) -> list[float]:
    n = len(blob) // 8
    return list(struct.unpack(f"<{n}d", blob))


class SqliteMemoryIndex:
    """Índice SQLite persistente genérico para recall de near-duplicates.

    El orden de iteración (relevante para empates y query vacía) preserva el
    orden de inserción de `rebuild_from` para que las desempates sean
    deterministas.
    """

    def __init__(
        self,
        db_path: Path,
        *,
        embedder: Embedder | None = None,
        threshold: float = 0.8,
    ) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._embedder: Embedder = embedder if embedder is not None else StubEmbedder(dim=64)
        self._threshold = threshold
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------

    def upsert(
        self,
        record: MemoryRecord,
        *,
        merkle_leaf_hash: str | None = None,
        merkle_leaf_index: int | None = None,
    ) -> None:
        """Inserta o actualiza un registro. Idempotente por `record_id`."""
        vec = self._embedder.embed(record.text)
        self._conn.execute(
            """
            INSERT INTO records (id, text, vector, merkle_leaf_hash, merkle_leaf_index, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                text=excluded.text,
                vector=excluded.vector,
                merkle_leaf_hash=COALESCE(excluded.merkle_leaf_hash, records.merkle_leaf_hash),
                merkle_leaf_index=COALESCE(excluded.merkle_leaf_index, records.merkle_leaf_index),
                created_at=excluded.created_at
            """,
            (record.record_id, record.text, _pack(vec), merkle_leaf_hash,
             merkle_leaf_index, record.created_at),
        )
        self._conn.commit()

    def rebuild_from(self, records: Iterable[MemoryRecord]) -> None:
        """Reconstruye el índice desde cero a partir de los registros (la fuente
        de verdad es el CORE; esto es una vista derivada)."""
        self._conn.execute("DELETE FROM records")
        self._conn.execute("DELETE FROM sqlite_sequence WHERE name='records'")
        for record in records:
            vec = self._embedder.embed(record.text)
            self._conn.execute(
                """
                INSERT INTO records (id, text, vector, merkle_leaf_hash,
                                     merkle_leaf_index, created_at)
                VALUES (?, ?, ?, NULL, NULL, ?)
                """,
                (record.record_id, record.text, _pack(vec), record.created_at),
            )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Lectura interna
    # ------------------------------------------------------------------

    def _rows(self) -> list[tuple[str, list[float]]]:
        cur = self._conn.execute("SELECT id, vector FROM records ORDER BY ordinal")
        return [(rid, _unpack(blob)) for rid, blob in cur.fetchall()]

    # ------------------------------------------------------------------
    # Recall
    # ------------------------------------------------------------------

    def recall(self, query_text: str) -> RecallResult | None:
        rows = self._rows()
        if not rows:
            return None
        if not query_text.strip():
            return RecallResult(lesson_id=rows[0][0], score=0.0, matched=False)
        query_vec = self._embedder.embed(query_text)
        best_id: str | None = None
        best_score = -1.0
        for rid, vec in rows:
            score = _cosine_similarity(query_vec, vec)
            if score > best_score:
                best_score = score
                best_id = rid
        assert best_id is not None
        return RecallResult(
            lesson_id=best_id, score=best_score, matched=best_score >= self._threshold
        )

    def recall_all(self, query_text: str, k: int = 5) -> list[RecallResult]:
        rows = self._rows()
        if not rows:
            return []
        if not query_text.strip():
            return [RecallResult(lesson_id=rid, score=0.0, matched=False) for rid, _ in rows][:k]
        query_vec = self._embedder.embed(query_text)
        results = [
            RecallResult(
                lesson_id=rid,
                score=_cosine_similarity(query_vec, vec),
                matched=_cosine_similarity(query_vec, vec) >= self._threshold,
            )
            for rid, vec in rows
        ]
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]

    # ------------------------------------------------------------------
    # Procedencia / utilidades
    # ------------------------------------------------------------------

    def merkle_leaf_hash(self, record_id: str) -> str | None:
        cur = self._conn.execute(
            "SELECT merkle_leaf_hash FROM records WHERE id=?", (record_id,)
        )
        row = cur.fetchone()
        return row[0] if row else None

    def merkle_leaf_index(self, record_id: str) -> int | None:
        cur = self._conn.execute(
            "SELECT merkle_leaf_index FROM records WHERE id=?", (record_id,)
        )
        row = cur.fetchone()
        return row[0] if row else None

    def count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM records")
        return int(cur.fetchone()[0])

    def close(self) -> None:
        self._conn.close()
