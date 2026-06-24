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
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from cryptography.fernet import Fernet

from atlas.immunity.lesson_recaller import RecallResult, _cosine_similarity
from atlas.memory.embeddings import Embedder, StubEmbedder
from atlas.memory.record import MemoryRecord

if TYPE_CHECKING:
    from atlas.logging.merkle_logger import MerkleLogger


class WriteRejected(Exception):
    """El WriteGate rechazó la escritura (provenance inválida u otra política)."""


@runtime_checkable
class WriteGate(Protocol):
    """Protocolo de gating de escritura.

    Implementaciones inspeccionan el registro y su hash de procedencia antes
    de permitir la inserción en el índice. Lanzar `WriteRejected` para bloquear;
    no retornar nada si la escritura es admisible.
    """

    def check(self, record: MemoryRecord, *, provenance: str | None) -> None: ...


class AllowAllWriteGate:
    """Política nula: nunca rechaza ninguna escritura."""

    def check(self, record: MemoryRecord, *, provenance: str | None) -> None:
        pass


class ProvenanceWriteGate:
    """Política recomendada: exige un hash de procedencia no vacío.

    Rechaza la escritura si `provenance` es None o sólo whitespace, lo que
    previene el envenenamiento de memoria con registros sin trazabilidad Merkle.
    """

    def check(self, record: MemoryRecord, *, provenance: str | None) -> None:
        if not provenance or not provenance.strip():
            raise WriteRejected(
                f"WriteGate rechazó la escritura de {record.record_id!r}: "
                f"provenance es None o vacía (merkle_leaf_hash requerido)."
            )


class ShreddedContentError(Exception):
    """El contenido de esta memoria ha sido destruido irrecuperablemente (crypto-shred)."""

    def __init__(self, record_id: str) -> None:
        super().__init__(f"El contenido de la memoria {record_id!r} ha sido destruido (shred).")
        self.record_id = record_id


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
CREATE TABLE IF NOT EXISTS content_keys (
    id         TEXT PRIMARY KEY,
    fernet_key BLOB NOT NULL
);
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

# Columnas añadidas por crypto-shredding (migración idempotente independiente).
_SHRED_COLUMNS = {
    "shredded": "INTEGER NOT NULL DEFAULT 0",
}

# Columnas añadidas por multi-tenancy (migración idempotente independiente).
_TENANT_COLUMNS = {
    "tenant": "TEXT NOT NULL DEFAULT 'default'",
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
        tenant: str = "default",
        embedder: Embedder | None = None,
        threshold: float = 0.8,
        merkle: "MerkleLogger | None" = None,
        auto_touch: bool = False,
        write_gate: WriteGate | None = None,
    ) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._tenant = tenant
        self._embedder: Embedder = embedder if embedder is not None else StubEmbedder(dim=64)
        self._threshold = threshold
        self._merkle = merkle
        # auto_touch: registrar el acceso (promover a hot + contar) en cada recall que
        # devuelve un match → la democión refleja el uso REAL sin llamadas manuales.
        self._auto_touch = auto_touch
        self._write_gate = write_gate
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute("PRAGMA secure_delete=ON")  # crypto-shred: sobrescribe páginas borradas
        self._conn.executescript(_SCHEMA)
        # Keystore separado: fichero hermano <db>.keys con su propia conexión.
        # Separar las claves de los datos garantiza que el shred es irrecuperable
        # incluso si alguien obtiene la DB de records (no encontrará las claves).
        keys_path = self._path.with_name(self._path.name + ".keys")
        self._keys_conn = sqlite3.connect(str(keys_path))
        self._keys_conn.execute("PRAGMA secure_delete=ON")  # sobrescribe páginas al borrar claves
        self._keys_conn.execute(
            "CREATE TABLE IF NOT EXISTS content_keys "
            "(id TEXT PRIMARY KEY, fernet_key BLOB NOT NULL)"
        )
        self._keys_conn.commit()
        self._migrate_temporal()
        self._migrate_shred()
        self._migrate_tenant()
        self._migrate_keystore()
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

    def _migrate_shred(self) -> None:
        """Añade columna shredded (crypto-shredding) y crea content_keys si no existen
        (idempotente — igual que _migrate_temporal)."""
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(records)")}
        for col, decl in _SHRED_COLUMNS.items():
            if col not in existing:
                try:
                    self._conn.execute(f"ALTER TABLE records ADD COLUMN {col} {decl}")
                except Exception:
                    pass  # ya existe en una carrera de inicio concurrente, seguro ignorar

    def _migrate_tenant(self) -> None:
        """Añade columna tenant (multi-tenancy) a un índice de esquema previo (idempotente).
        Las filas existentes quedan en 'default' (el DEFAULT del ALTER ya lo garantiza;
        el UPDATE adicional cubre drivers que no aplican DEFAULT en ALTER TABLE)."""
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(records)")}
        for col, decl in _TENANT_COLUMNS.items():
            if col not in existing:
                try:
                    self._conn.execute(f"ALTER TABLE records ADD COLUMN {col} {decl}")
                    # Backfill explícito por si el driver dejó NULLs en vez del DEFAULT.
                    self._conn.execute(
                        "UPDATE records SET tenant='default' WHERE tenant IS NULL"
                    )
                except Exception:
                    pass  # ya existe en una carrera de inicio concurrente, seguro ignorar

    def _migrate_keystore(self) -> None:
        """Migración idempotente: mueve claves de records.content_keys → keystore separado.

        En versiones anteriores a f2-9 las claves Fernet se guardaban en la misma DB
        que los records (tabla content_keys). Esta migración copia todas las filas
        existentes al keystore externo y vacía la tabla en la DB de records.
        Si ya está vacía, no hace nada (idempotente).
        """
        try:
            rows = self._conn.execute(
                "SELECT id, fernet_key FROM content_keys"
            ).fetchall()
        except sqlite3.OperationalError:
            # La tabla no existe en la DB de records (DB nueva); nada que migrar.
            return
        if not rows:
            return
        for row_id, fernet_key in rows:
            self._keys_conn.execute(
                "INSERT OR REPLACE INTO content_keys (id, fernet_key) VALUES (?, ?)",
                (row_id, fernet_key),
            )
        self._keys_conn.commit()
        self._conn.execute("DELETE FROM content_keys")
        self._conn.commit()

    # ------------------------------------------------------------------
    # Helpers privados: lectura/escritura/borrado de claves en el keystore externo
    # ------------------------------------------------------------------

    def _put_key(self, record_id: str, key: bytes) -> None:
        """Guarda o reemplaza la clave Fernet de un record en el keystore separado."""
        self._keys_conn.execute(
            "INSERT OR REPLACE INTO content_keys (id, fernet_key) VALUES (?, ?)",
            (record_id, key),
        )
        self._keys_conn.commit()

    def _get_key(self, record_id: str) -> bytes | None:
        """Devuelve la clave Fernet del record, o None si no existe."""
        row = self._keys_conn.execute(
            "SELECT fernet_key FROM content_keys WHERE id=?", (record_id,)
        ).fetchone()
        return row[0] if row else None

    def _del_key(self, record_id: str) -> None:
        """Borra la clave Fernet del keystore (operación de shred irrecuperable)."""
        self._keys_conn.execute(
            "DELETE FROM content_keys WHERE id=?", (record_id,)
        )
        self._keys_conn.commit()

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
        Idempotente por `record_id`. El texto se cifra con Fernet y la clave se guarda
        en content_keys — el embedding se calcula del texto EN CLARO antes de cifrar."""
        if self._write_gate is not None:
            self._write_gate.check(record, provenance=merkle_leaf_hash)
        vec = self._embedder.embed(record.text)
        vfrom = valid_from_ns if valid_from_ns is not None else time.time_ns()
        # Guard anti-fuga: si ya existe una fila con este id pero en otro tenant, rechaza.
        existing_tenant_row = self._conn.execute(
            "SELECT tenant FROM records WHERE id=?", (record.record_id,)
        ).fetchone()
        if existing_tenant_row is not None and existing_tenant_row[0] != self._tenant:
            raise ValueError(
                f"upsert: el id {record.record_id!r} ya pertenece al tenant "
                f"{existing_tenant_row[0]!r}; el tenant {self._tenant!r} no puede "
                f"sobrescribirlo (anti-fuga de tenant)."
            )
        # Cifrado Fernet: genera clave nueva en cada upsert (re-cifra si ya existe).
        key = Fernet.generate_key()
        token: str = Fernet(key).encrypt(record.text.encode()).decode()
        self._conn.execute(
            """
            INSERT INTO records (id, text, vector, merkle_leaf_hash, merkle_leaf_index,
                                 created_at, valid_from_ns, valid_until_ns, supersedes,
                                 tier, last_access_ns, access_count, shredded, tenant)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, 'hot', ?, 0, 0, ?)
            ON CONFLICT(id) DO UPDATE SET
                text=excluded.text,
                vector=excluded.vector,
                merkle_leaf_hash=COALESCE(excluded.merkle_leaf_hash, records.merkle_leaf_hash),
                merkle_leaf_index=COALESCE(excluded.merkle_leaf_index, records.merkle_leaf_index),
                created_at=excluded.created_at,
                shredded=0
            """,
            (record.record_id, token, _pack(vec), merkle_leaf_hash,
             merkle_leaf_index, record.created_at, vfrom, supersedes, vfrom, self._tenant),
        )
        # Upsert de la clave en el keystore separado.
        self._put_key(record.record_id, key)
        self._conn.commit()

    def rebuild_from(self, records: Iterable[MemoryRecord]) -> None:
        """Reconstruye el índice desde cero a partir de los registros (la fuente
        de verdad es el CORE; esto es una vista derivada).

        El texto se cifra por-ítem igual que en upsert — rebuild_from NO deja
        plaintext en la columna text (gap cerrado en f2-9).

        GC keystore (f2-10): tras borrar las filas del tenant del índice, las
        claves Fernet de ids que ya no aparecerán en los nuevos records quedan
        huérfanas. Se calculan los ids que van a entrar, se determinan los ids
        del keystore que pertenecen al tenant pero que NO están en el nuevo
        conjunto, y se borran antes de insertar."""
        # Recopilar ids pre-rebuild del tenant para GC posterior.
        old_ids: set[str] = {
            row[0]
            for row in self._conn.execute(
                "SELECT id FROM records WHERE tenant=?", (self._tenant,)
            ).fetchall()
        }
        self._conn.execute("DELETE FROM records WHERE tenant=?", (self._tenant,))
        # No borramos sqlite_sequence globalmente (afectaría otros tenants);
        # el ordinal autoincrement global sigue siendo válido para orden de inserción.
        now = time.time_ns()
        new_ids: set[str] = set()
        for record in records:
            vec = self._embedder.embed(record.text)
            # Cifrado Fernet: genera clave nueva por record, igual que upsert.
            key = Fernet.generate_key()
            token: str = Fernet(key).encrypt(record.text.encode()).decode()
            self._conn.execute(
                """
                INSERT INTO records (id, text, vector, merkle_leaf_hash, merkle_leaf_index,
                                     created_at, valid_from_ns, valid_until_ns, supersedes,
                                     tier, last_access_ns, access_count, shredded, tenant)
                VALUES (?, ?, ?, NULL, NULL, ?, ?, NULL, NULL, 'hot', ?, 0, 0, ?)
                """,
                (record.record_id, token, _pack(vec), record.created_at, now, now,
                 self._tenant),
            )
            self._put_key(record.record_id, key)
            new_ids.add(record.record_id)
        self._conn.commit()
        # GC (f2-10): borrar claves huérfanas (ids que estaban antes pero no ahora).
        orphan_ids = old_ids - new_ids
        for orphan_id in orphan_ids:
            self._del_key(orphan_id)

    # ------------------------------------------------------------------
    # Validez temporal / supersesión / olvido (1d-a) — el índice nunca BORRA;
    # "olvidar" = caducar (valid_until_ns) y dejar de surfacear. La fila persiste.
    # ------------------------------------------------------------------

    def supersede(
        self,
        old_id: str,
        new_record: MemoryRecord,
        *,
        merkle_leaf_hash: str | None = None,
        now_ns: int | None = None,
        reason: str = "",
    ) -> None:
        """La memoria `new_record` reemplaza a `old_id`: la vieja caduca (sigue en la
        tabla, auditable) y la nueva entra vigente con lineage `supersedes=old_id`."""
        old = self._conn.execute(
            "SELECT valid_until_ns FROM records WHERE id=? AND tenant=?",
            (old_id, self._tenant),
        ).fetchone()
        if old is None:
            raise KeyError(f"supersede: la memoria a reemplazar {old_id!r} no existe")
        if self._conn.execute(
            "SELECT 1 FROM records WHERE id=? AND tenant=?", (new_record.record_id, self._tenant)
        ).fetchone() is not None:
            raise ValueError(
                f"supersede: el nuevo id {new_record.record_id!r} ya existe; usa un id "
                f"distinto para preservar el lineage"
            )
        ts = now_ns if now_ns is not None else time.time_ns()
        self.upsert(new_record, merkle_leaf_hash=merkle_leaf_hash, valid_from_ns=ts, supersedes=old_id)
        self._conn.execute(
            "UPDATE records SET valid_until_ns=? WHERE id=? AND valid_until_ns IS NULL "
            "AND tenant=?",
            (ts, old_id, self._tenant),
        )
        self._conn.commit()
        self._audit("memory.superseded", {"old": old_id, "new": new_record.record_id,
                                          "at_ns": ts, "reason": reason})

    def retire(self, record_id: str, *, now_ns: int | None = None, reason: str = "") -> None:
        """Olvido sin reemplazo: la memoria caduca y deja de surfacearse. No se borra."""
        ts = now_ns if now_ns is not None else time.time_ns()
        self._conn.execute(
            "UPDATE records SET valid_until_ns=? WHERE id=? AND valid_until_ns IS NULL "
            "AND tenant=?",
            (ts, record_id, self._tenant),
        )
        self._conn.commit()
        self._audit("memory.retired", {"id": record_id, "at_ns": ts, "reason": reason})

    def _audit(self, action: str, payload: dict[str, object]) -> None:
        if self._merkle is not None:
            self._merkle.log(action=action, agent="memory_index",
                             result="success", payload=payload)

    def valid_until(self, record_id: str) -> int | None:
        row = self._conn.execute(
            "SELECT valid_until_ns FROM records WHERE id=? AND tenant=?",
            (record_id, self._tenant),
        ).fetchone()
        return row[0] if row else None

    def supersedes_of(self, record_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT supersedes FROM records WHERE id=? AND tenant=?",
            (record_id, self._tenant),
        ).fetchone()
        return row[0] if row else None

    def active_count(self) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM records WHERE valid_until_ns IS NULL AND tenant=?",
            (self._tenant,),
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
            "access_count=COALESCE(access_count,0)+1 WHERE id=? AND tenant=?",
            (ts, record_id, self._tenant),
        )
        self._conn.commit()

    def apply_decay(
        self,
        *,
        now_ns: int,
        warm_after_ns: int,
        cold_after_ns: int,
        pending_after_ns: int,
        retire_after_ns: int | None = None,
    ) -> dict[str, int]:
        """Demota memorias VIGENTES por ocio (now - último acceso) en buckets
        ascendentes. `pending` es el SUELO/grace. Si se da `retire_after_ns`
        (> pending_after_ns), las que llevan MÁS ocio que el grace se RETIRAN
        (caducan, auditado) — así el ciclo pending→retire es una política explícita,
        no un borrado implícito. La cadena nunca borra. Devuelve cuentas por tier."""
        rows = self._conn.execute(
            "SELECT id, COALESCE(last_access_ns, valid_from_ns, 0) "
            "FROM records WHERE valid_until_ns IS NULL AND tenant=?",
            (self._tenant,),
        ).fetchall()
        for rid, last in rows:
            idle = now_ns - last
            if retire_after_ns is not None and idle >= retire_after_ns:
                self.retire(rid, now_ns=now_ns, reason="decayed past grace")
                continue
            if idle >= pending_after_ns:
                new_tier = "pending"
            elif idle >= cold_after_ns:
                new_tier = "cold"
            elif idle >= warm_after_ns:
                new_tier = "warm"
            else:
                new_tier = "hot"
            self._conn.execute(
                "UPDATE records SET tier=? WHERE id=? AND tenant=?",
                (new_tier, rid, self._tenant),
            )
        self._conn.commit()
        counts = self.tier_counts()
        self._audit("memory.decay", {"at_ns": now_ns, "counts": counts})
        return counts

    def tier(self, record_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT tier FROM records WHERE id=? AND tenant=?", (record_id, self._tenant)
        ).fetchone()
        return row[0] if row else None

    def access_count(self, record_id: str) -> int | None:
        row = self._conn.execute(
            "SELECT access_count FROM records WHERE id=? AND tenant=?",
            (record_id, self._tenant),
        ).fetchone()
        return row[0] if row else None

    def tier_counts(self) -> dict[str, int]:
        """Cuenta por tier de las memorias VIGENTES."""
        rows = self._conn.execute(
            "SELECT tier, COUNT(*) FROM records "
            "WHERE valid_until_ns IS NULL AND tenant=? GROUP BY tier",
            (self._tenant,),
        ).fetchall()
        return {tier: int(n) for tier, n in rows if tier is not None}

    # ------------------------------------------------------------------
    # Lectura interna
    # ------------------------------------------------------------------

    def _rows(self, include_superseded: bool = False) -> list[tuple[str, list[float]]]:
        if not include_superseded:
            sql = "SELECT id, vector FROM records WHERE valid_until_ns IS NULL AND tenant=?"
        else:
            sql = "SELECT id, vector FROM records WHERE tenant=?"
        sql += " ORDER BY ordinal"
        cur = self._conn.execute(sql, (self._tenant,))
        return [(rid, _unpack(blob)) for rid, blob in cur.fetchall()]

    # ------------------------------------------------------------------
    # Recall (por defecto solo memorias VIGENTES)
    # ------------------------------------------------------------------

    def recall(
        self, query_text: str, *, include_superseded: bool = False, now_ns: int | None = None
    ) -> RecallResult | None:
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
        result = RecallResult(
            lesson_id=best_id, score=best_score, matched=best_score >= self._threshold
        )
        if self._auto_touch and result.matched:
            self.touch(result.lesson_id, now_ns=now_ns)
        return result

    def recall_all(
        self, query_text: str, k: int = 5, *, include_superseded: bool = False,
        now_ns: int | None = None,
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
        top = results[:k]
        if self._auto_touch:
            for r in top:
                if r.matched:
                    self.touch(r.lesson_id, now_ns=now_ns)
        return top

    # ------------------------------------------------------------------
    # Procedencia / utilidades
    # ------------------------------------------------------------------

    def merkle_leaf_hash(self, record_id: str) -> str | None:
        cur = self._conn.execute(
            "SELECT merkle_leaf_hash FROM records WHERE id=? AND tenant=?",
            (record_id, self._tenant),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def merkle_leaf_index(self, record_id: str) -> int | None:
        cur = self._conn.execute(
            "SELECT merkle_leaf_index FROM records WHERE id=? AND tenant=?",
            (record_id, self._tenant),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def text_of(self, record_id: str) -> str | None:
        """Texto descifrado de un id.

        Tri-estado:
        - id inexistente → None.
        - id con shredded=1 → ShreddedContentError.
        - id vigente cifrado → descifra con su clave y devuelve plaintext.
        - id legacy (sin entrada en content_keys y shredded=0) → devuelve text tal cual.
        """
        row = self._conn.execute(
            "SELECT text, shredded FROM records WHERE id=? AND tenant=?",
            (record_id, self._tenant),
        ).fetchone()
        if row is None:
            return None
        stored_text, shredded = row[0], row[1]
        if shredded:
            raise ShreddedContentError(record_id)
        key = self._get_key(record_id)
        if key is None:
            # Compat legacy: datos insertados en claro antes del cifrado.
            return str(stored_text)
        return Fernet(key).decrypt(stored_text.encode()).decode()

    def shred(self, record_id: str) -> None:
        """Destrucción irrecuperable del contenido: borra la clave Fernet y marca la
        fila como shredded. El slot (ordinal, vector, Merkle) se preserva íntegramente."""
        exists = self._conn.execute(
            "SELECT 1 FROM records WHERE id=? AND tenant=?", (record_id, self._tenant)
        ).fetchone()
        if exists is None:
            raise KeyError(f"shred: la memoria {record_id!r} no existe")
        self._del_key(record_id)
        self._conn.execute(
            "UPDATE records SET text='', shredded=1 WHERE id=? AND tenant=?",
            (record_id, self._tenant),
        )
        self._conn.commit()
        self._audit("memory.shredded", {"id": record_id, "at_ns": time.time_ns()})

    def count(self) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM records WHERE tenant=?", (self._tenant,)
        )
        return int(cur.fetchone()[0])

    def recall_multihop(
        self,
        query_text: str,
        *,
        hops: int = 2,
        include_superseded: bool = False,
        now_ns: int | None = None,
    ) -> list[RecallResult]:
        """Encadena recalls: cada hop usa el texto del resultado anterior como query.

        Hop 0: recall(query_text). Si no hay match, devuelve [].
        Hop i+1: recall sobre el texto del hop anterior, excluyendo ids ya visitados.
        Para cuando: se alcanza `hops` saltos o no hay siguiente con matched=True.

        Args:
            query_text: texto inicial de la cadena.
            hops: número máximo de saltos (0 o negativo → []).
            include_superseded: si True, incluye memorias caducadas en cada hop.
            now_ns: timestamp en nanosegundos para auto_touch (opcional).

        Returns:
            Lista ordenada (cadena) de RecallResult, longitud entre 0 y hops.
        """
        if hops <= 0 or not query_text.strip():
            return []

        chain: list[RecallResult] = []
        visited: set[str] = set()
        current_query = query_text

        for _ in range(hops):
            candidates = self.recall_all(
                current_query,
                k=len(self._rows(include_superseded)) + 1,
                include_superseded=include_superseded,
                now_ns=now_ns,
            )
            # Selecciona el mejor candidato no visitado que supere el umbral.
            next_result: RecallResult | None = None
            for candidate in candidates:
                if candidate.matched and candidate.lesson_id not in visited:
                    next_result = candidate
                    break

            if next_result is None:
                break

            chain.append(next_result)
            visited.add(next_result.lesson_id)

            # El texto de este resultado es la query del siguiente hop.
            next_text = self.text_of(next_result.lesson_id)
            if next_text is None:
                break
            current_query = next_text

        return chain

    # ------------------------------------------------------------------
    # Mantenimiento del keystore (f2-13)
    # ------------------------------------------------------------------

    def gc_keystore(self) -> int:
        """Barre TODAS las claves huérfanas del keystore.

        Una clave es huérfana si su id no existe en la tabla ``records``
        (independientemente del tenant o del motivo por el que desapareció:
        rebuild interrumpido, borrado manual, procesos fallidos, etc.).

        Returns:
            Número de claves borradas. Idempotente: 2ª llamada devuelve 0.
        """
        # Obtener todos los ids presentes en records (todos los tenants).
        live_ids: set[str] = {
            row[0]
            for row in self._conn.execute("SELECT id FROM records").fetchall()
        }
        # Obtener todos los ids presentes en el keystore.
        keystore_ids: list[str] = [
            row[0]
            for row in self._keys_conn.execute(
                "SELECT id FROM content_keys"
            ).fetchall()
        ]
        deleted = 0
        for kid in keystore_ids:
            if kid not in live_ids:
                self._del_key(kid)
                deleted += 1
        return deleted

    def close(self) -> None:
        self._conn.close()
        self._keys_conn.close()
