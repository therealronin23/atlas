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

Límite conocido (auditoría 2026-06-21): la conexión sqlite usa el default
`check_same_thread=True` → este índice NO es seguro para uso concurrente entre
hilos (igual que el `LessonRecaller` in-memory al que sustituye). Single-thread por
ahora; cuando el loop inmune se ensamble en vivo habrá que dar a cada hilo su
conexión o serializar con un lock.
"""

from __future__ import annotations

import sqlite3
import struct
import time
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from atlas.immunity.lesson_recaller import RecallResult, _cosine_similarity
from atlas.memory.embeddings import Embedder, StubEmbedder
from atlas.memory.record import MemoryRecord

if TYPE_CHECKING:
    from atlas.logging.merkle_logger import MerkleLogger

_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    ordinal           INTEGER PRIMARY KEY AUTOINCREMENT,
    id                TEXT UNIQUE NOT NULL,
    text              TEXT NOT NULL,
    vector            BLOB NOT NULL,
    merkle_leaf_hash  TEXT,
    merkle_leaf_index INTEGER,
    created_at        TEXT,
    valid_from_ns     INTEGER,
    valid_until_ns    INTEGER,   -- NULL = vigente AHORA (1d-a: validez temporal)
    supersedes        TEXT,      -- id de la memoria que esta reemplaza (lineage)
    tier              TEXT,      -- hot|warm|cold|pending (1d-b: niveles)
    last_access_ns    INTEGER,   -- para democión medible por ocio
    access_count      INTEGER
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

_META_EMBEDDER_DIM = "embedder_dim"

# Columnas a añadir si el índice viene de un esquema previo (migración suave).
_TEMPORAL_COLUMNS = {
    "valid_from_ns": "INTEGER",
    "valid_until_ns": "INTEGER",
    "supersedes": "TEXT",
    "tier": "TEXT",
    "last_access_ns": "INTEGER",
    "access_count": "INTEGER",
}


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
        merkle: "MerkleLogger | None" = None,
    ) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._embedder: Embedder = embedder if embedder is not None else StubEmbedder(dim=64)
        self._threshold = threshold
        self._merkle = merkle
        self._conn = sqlite3.connect(str(self._path))
        self._conn.executescript(_SCHEMA)
        self._migrate_temporal()
        self._guard_embedder_dim()
        self._conn.commit()

    def _migrate_temporal(self) -> None:
        """Añade las columnas de 1d-a/b a un índice de esquema previo (idempotente)
        y rellena las nuevas en filas viejas para no dejarlas invisibles a tiers."""
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(records)")}
        added = False
        for col, decl in _TEMPORAL_COLUMNS.items():
            if col not in existing:
                self._conn.execute(f"ALTER TABLE records ADD COLUMN {col} {decl}")
                added = True
        if added:
            # Backfill: filas pre-1d quedan vigentes (valid_until NULL) y en tier hot,
            # con su ocio anclado a valid_from si lo tienen.
            self._conn.execute(
                "UPDATE records SET tier='hot' WHERE tier IS NULL"
            )
            self._conn.execute(
                "UPDATE records SET access_count=0 WHERE access_count IS NULL"
            )
            self._conn.execute(
                "UPDATE records SET last_access_ns=valid_from_ns "
                "WHERE last_access_ns IS NULL AND valid_from_ns IS NOT NULL"
            )

    def _guard_embedder_dim(self) -> None:
        """Persiste/verifica la dim del embedder: reabrir un índice con un embedder
        de otra dimensión daría scores SILENCIOSAMENTE basura (el coseno truncaría
        vectores de distinta longitud). Falla ruidoso en su lugar."""
        dim = self._embedder.dim
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key=?", (_META_EMBEDDER_DIM,)
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?)",
                (_META_EMBEDDER_DIM, str(dim)),
            )
        elif int(row[0]) != dim:
            raise ValueError(
                f"Embedder dim mismatch: el índice {self._path.name} se creó con "
                f"dim={row[0]} pero el embedder actual usa dim={dim}. Usa el embedder "
                f"original o reconstruye el índice."
            )

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------

    def upsert(
        self,
        record: MemoryRecord,
        *,
        merkle_leaf_hash: str | None = None,
        merkle_leaf_index: int | None = None,
        valid_from_ns: int | None = None,
        supersedes: str | None = None,
    ) -> None:
        """Inserta o actualiza un registro VIGENTE (valid_until_ns NULL).
        Idempotente por `record_id`."""
        vec = self._embedder.embed(record.text)
        vfrom = valid_from_ns if valid_from_ns is not None else time.time_ns()
        self._conn.execute(
            """
            INSERT INTO records (id, text, vector, merkle_leaf_hash, merkle_leaf_index,
                                 created_at, valid_from_ns, valid_until_ns, supersedes,
                                 tier, last_access_ns, access_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, 'hot', ?, 0)
            ON CONFLICT(id) DO UPDATE SET
                text=excluded.text,
                vector=excluded.vector,
                merkle_leaf_hash=COALESCE(excluded.merkle_leaf_hash, records.merkle_leaf_hash),
                merkle_leaf_index=COALESCE(excluded.merkle_leaf_index, records.merkle_leaf_index),
                created_at=excluded.created_at
            """,
            (record.record_id, record.text, _pack(vec), merkle_leaf_hash,
             merkle_leaf_index, record.created_at, vfrom, supersedes, vfrom),
        )
        self._conn.commit()

    def rebuild_from(self, records: Iterable[MemoryRecord]) -> None:
        """Reconstruye el índice desde cero a partir de los registros (la fuente
        de verdad es el CORE; esto es una vista derivada)."""
        self._conn.execute("DELETE FROM records")
        self._conn.execute("DELETE FROM sqlite_sequence WHERE name='records'")
        now = time.time_ns()
        for record in records:
            vec = self._embedder.embed(record.text)
            self._conn.execute(
                """
                INSERT INTO records (id, text, vector, merkle_leaf_hash, merkle_leaf_index,
                                     created_at, valid_from_ns, valid_until_ns, supersedes,
                                     tier, last_access_ns, access_count)
                VALUES (?, ?, ?, NULL, NULL, ?, ?, NULL, NULL, 'hot', ?, 0)
                """,
                (record.record_id, record.text, _pack(vec), record.created_at, now, now),
            )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Validez temporal / supersesión / olvido (1d-a) — el índice nunca BORRA;
    # "olvidar" = caducar (valid_until_ns) y dejar de surfacear. La fila persiste.
    # ------------------------------------------------------------------

    def supersede(
        self,
        old_id: str,
        new_record: MemoryRecord,
        *,
        now_ns: int | None = None,
        reason: str = "",
    ) -> None:
        """La memoria `new_record` reemplaza a `old_id`: la vieja caduca (sigue en la
        tabla, auditable) y la nueva entra vigente con lineage `supersedes=old_id`."""
        old = self._conn.execute(
            "SELECT valid_until_ns FROM records WHERE id=?", (old_id,)
        ).fetchone()
        if old is None:
            raise KeyError(f"supersede: la memoria a reemplazar {old_id!r} no existe")
        if self._conn.execute(
            "SELECT 1 FROM records WHERE id=?", (new_record.record_id,)
        ).fetchone() is not None:
            raise ValueError(
                f"supersede: el nuevo id {new_record.record_id!r} ya existe; usa un id "
                f"distinto para preservar el lineage"
            )
        ts = now_ns if now_ns is not None else time.time_ns()
        self.upsert(new_record, valid_from_ns=ts, supersedes=old_id)
        self._conn.execute(
            "UPDATE records SET valid_until_ns=? WHERE id=? AND valid_until_ns IS NULL",
            (ts, old_id),
        )
        self._conn.commit()
        self._audit("memory.superseded", {"old": old_id, "new": new_record.record_id,
                                          "at_ns": ts, "reason": reason})

    def retire(self, record_id: str, *, now_ns: int | None = None, reason: str = "") -> None:
        """Olvido sin reemplazo: la memoria caduca y deja de surfacearse. No se borra."""
        ts = now_ns if now_ns is not None else time.time_ns()
        self._conn.execute(
            "UPDATE records SET valid_until_ns=? WHERE id=? AND valid_until_ns IS NULL",
            (ts, record_id),
        )
        self._conn.commit()
        self._audit("memory.retired", {"id": record_id, "at_ns": ts, "reason": reason})

    def _audit(self, action: str, payload: dict[str, object]) -> None:
        if self._merkle is not None:
            self._merkle.log(action=action, agent="memory_index",
                             result="success", payload=payload)

    def valid_until(self, record_id: str) -> int | None:
        row = self._conn.execute(
            "SELECT valid_until_ns FROM records WHERE id=?", (record_id,)
        ).fetchone()
        return row[0] if row else None

    def supersedes_of(self, record_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT supersedes FROM records WHERE id=?", (record_id,)
        ).fetchone()
        return row[0] if row else None

    def active_count(self) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM records WHERE valid_until_ns IS NULL"
        )
        return int(cur.fetchone()[0])

    # ------------------------------------------------------------------
    # Niveles (1d-b): democión MEDIBLE por ocio; recuperable; pending = grace.
    # No borra: la cadena Merkle es la fuente; el tier solo gobierna el surfacing.
    # ------------------------------------------------------------------

    def touch(self, record_id: str, *, now_ns: int | None = None) -> None:
        """Registra un acceso: promociona a hot (recuperable) y cuenta el uso."""
        ts = now_ns if now_ns is not None else time.time_ns()
        self._conn.execute(
            "UPDATE records SET tier='hot', last_access_ns=?, "
            "access_count=COALESCE(access_count,0)+1 WHERE id=?",
            (ts, record_id),
        )
        self._conn.commit()

    def apply_decay(
        self,
        *,
        now_ns: int,
        warm_after_ns: int,
        cold_after_ns: int,
        pending_after_ns: int,
    ) -> dict[str, int]:
        """Demota memorias VIGENTES por ocio (now - último acceso) en buckets
        ascendentes. Medible y reproducible; pending es el SUELO (no retira: el
        retiro es decisión aparte, honra el grace). Devuelve cuentas por tier."""
        rows = self._conn.execute(
            "SELECT id, COALESCE(last_access_ns, valid_from_ns, 0) "
            "FROM records WHERE valid_until_ns IS NULL"
        ).fetchall()
        for rid, last in rows:
            idle = now_ns - last
            if idle >= pending_after_ns:
                new_tier = "pending"
            elif idle >= cold_after_ns:
                new_tier = "cold"
            elif idle >= warm_after_ns:
                new_tier = "warm"
            else:
                new_tier = "hot"
            self._conn.execute("UPDATE records SET tier=? WHERE id=?", (new_tier, rid))
        self._conn.commit()
        counts = self.tier_counts()
        self._audit("memory.decay", {"at_ns": now_ns, "counts": counts})
        return counts

    def tier(self, record_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT tier FROM records WHERE id=?", (record_id,)
        ).fetchone()
        return row[0] if row else None

    def access_count(self, record_id: str) -> int | None:
        row = self._conn.execute(
            "SELECT access_count FROM records WHERE id=?", (record_id,)
        ).fetchone()
        return row[0] if row else None

    def tier_counts(self) -> dict[str, int]:
        """Cuenta por tier de las memorias VIGENTES."""
        rows = self._conn.execute(
            "SELECT tier, COUNT(*) FROM records WHERE valid_until_ns IS NULL GROUP BY tier"
        ).fetchall()
        return {tier: int(n) for tier, n in rows if tier is not None}

    # ------------------------------------------------------------------
    # Lectura interna
    # ------------------------------------------------------------------

    def _rows(self, include_superseded: bool = False) -> list[tuple[str, list[float]]]:
        sql = "SELECT id, vector FROM records"
        if not include_superseded:
            sql += " WHERE valid_until_ns IS NULL"
        sql += " ORDER BY ordinal"
        cur = self._conn.execute(sql)
        return [(rid, _unpack(blob)) for rid, blob in cur.fetchall()]

    # ------------------------------------------------------------------
    # Recall (por defecto solo memorias VIGENTES)
    # ------------------------------------------------------------------

    def recall(self, query_text: str, *, include_superseded: bool = False) -> RecallResult | None:
        rows = self._rows(include_superseded)
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

    def recall_all(
        self, query_text: str, k: int = 5, *, include_superseded: bool = False
    ) -> list[RecallResult]:
        rows = self._rows(include_superseded)
        if not rows:
            return []
        if not query_text.strip():
            return [RecallResult(lesson_id=rid, score=0.0, matched=False) for rid, _ in rows][:k]
        query_vec = self._embedder.embed(query_text)
        results = []
        for rid, vec in rows:
            score = _cosine_similarity(query_vec, vec)
            results.append(
                RecallResult(lesson_id=rid, score=score, matched=score >= self._threshold)
            )
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
