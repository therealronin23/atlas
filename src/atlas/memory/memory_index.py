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

import os
import sqlite3
import stat
import struct
import time
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from cryptography.fernet import Fernet

from atlas.immunity.lesson_recaller import RecallResult, _cosine_similarity
from atlas.memory.embeddings import (
    Embedder,
    StubEmbedder,
    embedding_identity_fingerprint,
)
from atlas.memory.record import MemoryRecord

if TYPE_CHECKING:
    from atlas.logging.merkle_logger import MerkleLogger


# ------------------------------------------------------------------
# rrf_fuse — función pura de Reciprocal Rank Fusion
# ------------------------------------------------------------------

def rrf_fuse(rankings: list[list[str]], *, k: int = 60) -> list[str]:
    """Reciprocal Rank Fusion (RRF) sobre múltiples listas ordenadas de record_ids.

    Para cada lista, contribuye 1/(k+rank) al score del id (rank empieza en 1).
    Devuelve los record_ids únicos ordenados por score RRF desc.

    Args:
        rankings: lista de listas de record_ids; cada lista está ordenada por
                  relevancia descendente.
        k:        constante de suavizado RRF; el valor canónico es 60.

    Returns:
        Lista de record_ids únicos ordenados por puntuación RRF (mayor primero).
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, rid in enumerate(ranking, start=1):
            scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda r: scores[r], reverse=True)


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
_META_EMBEDDER_IDENTITY = "embedder_identity"
_META_EMBEDDER_FINGERPRINT = "embedder_fingerprint"

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

PERSONAL_TTL_S = 90 * 24 * 3600  # 90 días; default de expiración para clase 'personal'

_CLASS_TTL_COLUMNS = {
    "memory_class": "TEXT NOT NULL DEFAULT 'factual'",
    "expires_at": "REAL",
}

# Columnas añadidas por mem-1 (tiempo del HECHO vs tiempo de SISTEMA), idempotente
# como las anteriores. NULL = sin distinguir del tiempo de sistema (valid_from_ns/
# valid_until_ns) — cero cambio de comportamiento para quien no los usa.
_FACT_TIME_COLUMNS = {
    "fact_valid_at_ns": "INTEGER",
    "fact_invalid_at_ns": "INTEGER",
}


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}d", *vec)


def _unpack(blob: bytes) -> list[float]:
    n = len(blob) // 8
    return list(struct.unpack(f"<{n}d", blob))


def _prepare_private_sqlite_file(path: Path) -> None:
    """Create or tighten a SQLite file without following a final symlink."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError(f"SQLite path is not a regular file: {path}")
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)


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
        lexical_index: bool = False,
    ) -> None:
        """Inicializa el índice SQLite.

        Args:
            lexical_index: si True, crea/mantiene un índice FTS5 (``records_fts``)
                que almacena el PLAINTEXT de cada record para búsqueda léxica BM25.
                **Trade-off de confidencialidad:** activar este parámetro almacena
                tokens en claro en el índice FTS; la confidencialidad at-rest se
                reduce respecto al modo cifrado por defecto. El crypto-shred SIGUE
                funcionando: al invocar ``shred()`` también se borra la fila FTS.
                Default False → comportamiento y esquema actuales INTACTOS.
        """
        self._path = Path(db_path)
        _prepare_private_sqlite_file(self._path)
        self._tenant = tenant
        self._embedder: Embedder = embedder if embedder is not None else StubEmbedder(dim=64)
        self._threshold = threshold
        self._merkle = merkle
        # auto_touch: registrar el acceso (promover a hot + contar) en cada recall que
        # devuelve un match → la democión refleja el uso REAL sin llamadas manuales.
        self._auto_touch = auto_touch
        self._write_gate = write_gate
        self._lexical_index = lexical_index
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute("PRAGMA secure_delete=ON")  # crypto-shred: sobrescribe páginas borradas
        self._conn.executescript(_SCHEMA)
        # Keystore separado: fichero hermano <db>.keys con su propia conexión.
        # Separar las claves de los datos garantiza que el shred es irrecuperable
        # incluso si alguien obtiene la DB de records (no encontrará las claves).
        keys_path = self._path.with_name(self._path.name + ".keys")
        _prepare_private_sqlite_file(keys_path)
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
        self._migrate_class_ttl()
        self._migrate_fact_time()
        self._migrate_keystore()
        self._guard_embedder_dim()
        self._guard_embedder_identity()
        if self._lexical_index:
            self._init_fts()
        self._conn.commit()

    # ------------------------------------------------------------------
    # FTS5 — índice léxico OPT-IN (lexical_index=True)
    # ------------------------------------------------------------------

    def _init_fts(self) -> None:
        """Crea la tabla virtual FTS5 (idempotente) y la tabla puente record_id↔rowid.

        Usamos una tabla FTS5 standalone (content='') para desacoplarla de la tabla
        ``records`` (cuya columna text contiene CIPHERTEXT). La tabla puente
        ``records_fts_map`` mapea record_id → rowid FTS para permitir borrado directo.
        """
        self._conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS records_fts
            USING fts5(text, content='')
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS records_fts_map (
                record_id TEXT PRIMARY KEY,
                fts_rowid INTEGER NOT NULL,
                plaintext TEXT NOT NULL DEFAULT ''
            )
            """
        )
        # Migración suave: añadir columna plaintext si existe de una versión previa.
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(records_fts_map)")}
        if "plaintext" not in existing:
            self._conn.execute(
                "ALTER TABLE records_fts_map ADD COLUMN plaintext TEXT NOT NULL DEFAULT ''"
            )
        self._conn.commit()

    def _fts_upsert(self, record_id: str, plaintext: str) -> None:
        """Inserta o reemplaza la entrada FTS de un record (plaintext en claro)."""
        # Borra entrada previa si existe (por-id).
        self._fts_delete(record_id)
        self._conn.execute("INSERT INTO records_fts(text) VALUES (?)", (plaintext,))
        rowid: int = self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        self._conn.execute(
            "INSERT OR REPLACE INTO records_fts_map (record_id, fts_rowid, plaintext) "
            "VALUES (?, ?, ?)",
            (record_id, rowid, plaintext),
        )

    def _fts_delete(self, record_id: str) -> None:
        """Borra la entrada FTS de un record (sincronización con shred/retire).

        FTS5 standalone (content='') requiere el texto original para el comando
        'delete'; lo tenemos guardado en records_fts_map.plaintext.
        """
        row = self._conn.execute(
            "SELECT fts_rowid, plaintext FROM records_fts_map WHERE record_id=?",
            (record_id,),
        ).fetchone()
        if row is not None:
            fts_rowid: int = row[0]
            stored_text: str = row[1]
            self._conn.execute(
                "INSERT INTO records_fts(records_fts, rowid, text) VALUES ('delete', ?, ?)",
                (fts_rowid, stored_text),
            )
            self._conn.execute(
                "DELETE FROM records_fts_map WHERE record_id=?", (record_id,)
            )

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

    def _migrate_class_ttl(self) -> None:
        """Añade memory_class (personal/factual) y expires_at (idempotente).
        Filas existentes → 'factual' sin expiración (lo seguro/objetivo)."""
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(records)")}
        for col, decl in _CLASS_TTL_COLUMNS.items():
            if col not in existing:
                try:
                    self._conn.execute(f"ALTER TABLE records ADD COLUMN {col} {decl}")
                    if col == "memory_class":
                        self._conn.execute(
                            "UPDATE records SET memory_class='factual' "
                            "WHERE memory_class IS NULL"
                        )
                except Exception:
                    pass  # carrera de init concurrente: seguro ignorar
        self._conn.commit()

    def _migrate_fact_time(self) -> None:
        """Añade fact_valid_at_ns/fact_invalid_at_ns (mem-1) a un índice de esquema
        previo (idempotente — mismo patrón que _migrate_class_ttl/_migrate_shred).
        Sin backfill: filas viejas quedan con NULL en ambas, que es exactamente
        "sin distinguir del tiempo de sistema" (comportamiento actual intacto)."""
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(records)")}
        for col, decl in _FACT_TIME_COLUMNS.items():
            if col not in existing:
                try:
                    self._conn.execute(f"ALTER TABLE records ADD COLUMN {col} {decl}")
                except Exception:
                    pass  # carrera de init concurrente: seguro ignorar

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

    def _guard_embedder_identity(self) -> None:
        """Persist and verify the exact vector space, failing closed on ambiguity.

        A legacy index without this metadata can only be adopted when it has no
        vectors. If records already exist, dimension equality cannot prove which
        model produced them, so a rebuild is required.
        """
        try:
            current_identity = self._embedder.identity
            declared_fingerprint = self._embedder.fingerprint
        except AttributeError as exc:
            raise ValueError(
                "Embedder lacks a stable identity; persistent vector storage "
                "requires Embedder.identity and Embedder.fingerprint."
            ) from exc
        current_fingerprint = embedding_identity_fingerprint(current_identity)
        if declared_fingerprint != current_fingerprint:
            raise ValueError(
                "Embedder fingerprint is inconsistent with Embedder.identity; "
                "refusing persistent vector storage."
            )
        identity_row = self._conn.execute(
            "SELECT value FROM meta WHERE key=?", (_META_EMBEDDER_IDENTITY,)
        ).fetchone()
        fingerprint_row = self._conn.execute(
            "SELECT value FROM meta WHERE key=?", (_META_EMBEDDER_FINGERPRINT,)
        ).fetchone()

        if identity_row is None and fingerprint_row is None:
            has_vectors = self._conn.execute(
                "SELECT EXISTS(SELECT 1 FROM records LIMIT 1)"
            ).fetchone()[0]
            if has_vectors:
                raise ValueError(
                    f"Index {self._path.name} contains vectors but lacks embedder "
                    "identity metadata. Rebuild it with the intended embedder; "
                    "dimension alone cannot prove the vector space."
                )
            self._conn.executemany(
                "INSERT INTO meta (key, value) VALUES (?, ?)",
                (
                    (_META_EMBEDDER_IDENTITY, current_identity),
                    (_META_EMBEDDER_FINGERPRINT, current_fingerprint),
                ),
            )
            return

        stored_identity = str(identity_row[0]) if identity_row is not None else None
        stored_fingerprint = (
            str(fingerprint_row[0]) if fingerprint_row is not None else None
        )
        if stored_identity is not None:
            expected_stored_fingerprint = embedding_identity_fingerprint(stored_identity)
            if (
                stored_fingerprint is not None
                and stored_fingerprint != expected_stored_fingerprint
            ):
                raise ValueError(
                    f"Embedder identity metadata is inconsistent in {self._path.name}; "
                    "rebuild the index."
                )
            if stored_identity != current_identity:
                raise ValueError(
                    f"Embedder identity mismatch: index {self._path.name} uses "
                    f"{stored_identity!r}, current embedder uses {current_identity!r}. "
                    "Use the original embedder or rebuild the index."
                )
            if stored_fingerprint is None:
                self._conn.execute(
                    "INSERT INTO meta (key, value) VALUES (?, ?)",
                    (_META_EMBEDDER_FINGERPRINT, expected_stored_fingerprint),
                )
            return

        # A fingerprint without the clear identity is still cryptographic proof
        # when it matches the current identity; restore the diagnostic metadata.
        if stored_fingerprint != current_fingerprint:
            raise ValueError(
                f"Embedder identity mismatch: index {self._path.name} has fingerprint "
                f"{stored_fingerprint!r}, current embedder has {current_fingerprint!r}. "
                "Use the original embedder or rebuild the index."
            )
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            (_META_EMBEDDER_IDENTITY, current_identity),
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
        memory_class: str = "factual",
        expires_at: float | None = None,
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
        eff_expires_at = expires_at
        if eff_expires_at is None and memory_class == "personal":
            eff_expires_at = time.time() + PERSONAL_TTL_S
        # mem-1: tiempo del HECHO, opcional — getattr defensivo (no todo MemoryRecord
        # duck-tipado tiene por qué llevarlo); default None = sin distinguir del
        # tiempo de sistema (vfrom/valid_until_ns), cero cambio de comportamiento.
        fact_valid_at_ns = getattr(record, "fact_valid_at_ns", None)
        fact_invalid_at_ns = getattr(record, "fact_invalid_at_ns", None)
        # Cifrado Fernet: genera clave nueva en cada upsert (re-cifra si ya existe).
        key = Fernet.generate_key()
        token: str = Fernet(key).encrypt(record.text.encode()).decode()
        self._conn.execute(
            """
            INSERT INTO records (id, text, vector, merkle_leaf_hash, merkle_leaf_index,
                                 created_at, valid_from_ns, valid_until_ns, supersedes,
                                 tier, last_access_ns, access_count, shredded, tenant,
                                 memory_class, expires_at, fact_valid_at_ns, fact_invalid_at_ns)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, 'hot', ?, 0, 0, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                text=excluded.text,
                vector=excluded.vector,
                merkle_leaf_hash=COALESCE(excluded.merkle_leaf_hash, records.merkle_leaf_hash),
                merkle_leaf_index=COALESCE(excluded.merkle_leaf_index, records.merkle_leaf_index),
                created_at=excluded.created_at,
                shredded=0,
                memory_class=excluded.memory_class,
                expires_at=excluded.expires_at,
                fact_valid_at_ns=excluded.fact_valid_at_ns,
                fact_invalid_at_ns=excluded.fact_invalid_at_ns
            """,
            (record.record_id, token, _pack(vec), merkle_leaf_hash,
             merkle_leaf_index, record.created_at, vfrom, supersedes, vfrom, self._tenant,
             memory_class, eff_expires_at, fact_valid_at_ns, fact_invalid_at_ns),
        )
        # Upsert de la clave en el keystore separado.
        self._put_key(record.record_id, key)
        # Índice léxico OPT-IN: indexar el plaintext en FTS si está activo.
        if self._lexical_index:
            self._fts_upsert(record.record_id, record.text)
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
            # mem-1: tiempo del HECHO, opcional (ver upsert()).
            fact_valid_at_ns = getattr(record, "fact_valid_at_ns", None)
            fact_invalid_at_ns = getattr(record, "fact_invalid_at_ns", None)
            self._conn.execute(
                """
                INSERT INTO records (id, text, vector, merkle_leaf_hash, merkle_leaf_index,
                                     created_at, valid_from_ns, valid_until_ns, supersedes,
                                     tier, last_access_ns, access_count, shredded, tenant,
                                     fact_valid_at_ns, fact_invalid_at_ns)
                VALUES (?, ?, ?, NULL, NULL, ?, ?, NULL, NULL, 'hot', ?, 0, 0, ?, ?, ?)
                """,
                (record.record_id, token, _pack(vec), record.created_at, now, now,
                 self._tenant, fact_valid_at_ns, fact_invalid_at_ns),
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
            "SELECT valid_until_ns, memory_class, expires_at FROM records WHERE id=? AND tenant=?",
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
        self.upsert(
            new_record,
            merkle_leaf_hash=merkle_leaf_hash,
            valid_from_ns=ts,
            supersedes=old_id,
            memory_class=str(old[1]),
            expires_at=old[2],
        )
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

    def expire_stale(self, *, now_ns: int | None = None) -> int:
        """Barrido perezoso (on-demand, sin daemon): soft-retira los ítems con
        expires_at <= now. Reusa la semántica de retire (valid_until_ns)."""
        now = time.time()
        ts = now_ns if now_ns is not None else time.time_ns()
        rows = self._conn.execute(
            "SELECT id FROM records WHERE tenant=? AND valid_until_ns IS NULL "
            "AND expires_at IS NOT NULL AND expires_at <= ?",
            (self._tenant, now),
        ).fetchall()
        for (rid,) in rows:
            self._conn.execute(
                "UPDATE records SET valid_until_ns=? WHERE id=? AND valid_until_ns IS NULL "
                "AND tenant=?",
                (ts, rid, self._tenant),
            )
        self._conn.commit()
        if rows:
            self._audit("memory.expired_swept", {"count": len(rows), "at_ns": ts})
        return len(rows)

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

    def _rows(
        self, include_superseded: bool = False, *,
        memory_class: str = "factual", now_epoch: float | None = None,
    ) -> list[tuple[str, list[float]]]:
        now = now_epoch if now_epoch is not None else time.time()
        sql = "SELECT id, vector FROM records WHERE tenant=?"
        params: list[object] = [self._tenant]
        if not include_superseded:
            sql += " AND valid_until_ns IS NULL"
        sql += " AND memory_class=?"
        params.append(memory_class)
        sql += " AND (expires_at IS NULL OR expires_at > ?)"
        params.append(now)
        sql += " ORDER BY ordinal"
        cur = self._conn.execute(sql, tuple(params))
        return [(rid, _unpack(blob)) for rid, blob in cur.fetchall()]

    # ------------------------------------------------------------------
    # Recall (por defecto solo memorias VIGENTES)
    # ------------------------------------------------------------------

    def recall(
        self, query_text: str, *, include_superseded: bool = False, now_ns: int | None = None,
        memory_class: str | None = None,
    ) -> RecallResult | None:
        cls = memory_class if memory_class is not None else "factual"
        rows = self._rows(include_superseded, memory_class=cls)
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
        now_ns: int | None = None, memory_class: str | None = None,
    ) -> list[RecallResult]:
        cls = memory_class if memory_class is not None else "factual"
        rows = self._rows(include_superseded, memory_class=cls)
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

    def recall_split(
        self, query_text: str, k: int = 5, *,
        include_superseded: bool = False, now_ns: int | None = None,
    ) -> tuple[list[RecallResult], list[RecallResult]]:
        """Recall en buckets SEPARADOS (factual, personal) — nunca mezclados en un
        ranking único. Para personalización + hechos sin contaminar el ranking factual."""
        factual = self.recall_all(
            query_text, k, include_superseded=include_superseded,
            now_ns=now_ns, memory_class="factual",
        )
        personal = self.recall_all(
            query_text, k, include_superseded=include_superseded,
            now_ns=now_ns, memory_class="personal",
        )
        return factual, personal

    def recall_temporal(
        self,
        query_text: str,
        *,
        k: int = 10,
        as_of_ns: int | None = None,
        half_life_ns: int | None = None,
        use_fact_time: bool = False,
    ) -> list[RecallResult]:
        """Recall consciente de validez temporal: reconstruye qué era vigente en as_of_ns.

        Señal de ranking determinista y auditable — NO borra nada, solo reordena/filtra.

        Semántica de validez (tiempo de SISTEMA, default): un record es válido en T si
            valid_from_ns <= T AND (valid_until_ns IS NULL OR T < valid_until_ns).
        Esto permite recuperar versiones que eran vigentes en el PASADO aunque hoy
        estén superseded, y excluir versiones que todavía no habían entrado (futuro).
        Respeta tenant y expires_at igual que recall_all.

        `use_fact_time` (mem-1, default False = CERO cambio de comportamiento): cuando
        es True, razona sobre cuándo el HECHO fue/dejó de ser cierto EN EL MUNDO en vez
        de cuándo el sistema lo ingirió/invalidó. Por fila, usa fact_valid_at_ns/
        fact_invalid_at_ns si están presentes y cae a valid_from_ns/valid_until_ns si no
        (NULL por fila = ese record no distingue tiempo-de-hecho de tiempo-de-sistema).
        Esto permite recuperar un hecho ingerido HOY que describe algo que fue cierto en
        el pasado, en una query as_of anclada a ESE pasado — algo que el tiempo de
        sistema por sí solo no puede hacer (valid_from_ns == instante de ingesta, no el
        instante en que el hecho era cierto).

        Ranking:
          - Con half_life_ns dado: score = coseno * 0.5^(age/half_life_ns)
            donde age = max(0, as_of_ns - efectivo_from). Favorece lo más reciente.
          - Con half_life_ns=None: coseno puro; desempate por efectivo_from desc
            (lo más reciente primero, determinista).
          (efectivo_from = fact_valid_at_ns si use_fact_time y presente, si no valid_from_ns.)

        Args:
            query_text:    texto de la query.
            k:             número máximo de resultados.
            as_of_ns:      instante de consulta en nanosegundos; None → ahora.
            half_life_ns:  vida media del decaimiento exponencial en ns; None → sin decay.
            use_fact_time: si True, razona sobre fact_valid_at_ns/fact_invalid_at_ns
                           en vez de valid_from_ns/valid_until_ns (ver arriba).

        Returns:
            Lista de RecallResult ordenada por score combinado, top-k.
        """
        t_ns = as_of_ns if as_of_ns is not None else time.time_ns()
        now_epoch = t_ns / 1e9  # para filtro expires_at

        raw_rows: list[tuple[str, list[float], int]]
        if use_fact_time:
            # Traemos también las columnas de tiempo-de-hecho y resolvemos el
            # "efectivo_from/until" por fila en Python: fact_* si está presente,
            # si no cae a valid_from_ns/valid_until_ns (system time), fila a fila.
            sql = (
                "SELECT id, vector, valid_from_ns, valid_until_ns, "
                "fact_valid_at_ns, fact_invalid_at_ns "
                "FROM records WHERE tenant=? "
                "AND (expires_at IS NULL OR expires_at > ?) "
                "ORDER BY ordinal"
            )
            cur = self._conn.execute(sql, (self._tenant, now_epoch))
            raw_rows = []
            for rid, blob, vfrom, vuntil, fact_from, fact_until in cur.fetchall():
                eff_from = fact_from if fact_from is not None else vfrom
                eff_until = fact_until if fact_until is not None else vuntil
                if eff_from is None or eff_from > t_ns:
                    continue
                if eff_until is not None and t_ns >= eff_until:
                    continue
                raw_rows.append((rid, _unpack(blob), eff_from))
        else:
            # Recuperamos TODAS las filas del tenant (include_superseded=True) y aplicamos
            # el filtro de validez en as_of_ns + expires_at manualmente.
            sql = (
                "SELECT id, vector, valid_from_ns "
                "FROM records WHERE tenant=? "
                "AND valid_from_ns IS NOT NULL "
                "AND valid_from_ns <= ? "
                "AND (valid_until_ns IS NULL OR ? < valid_until_ns) "
                "AND (expires_at IS NULL OR expires_at > ?) "
                "ORDER BY ordinal"
            )
            cur = self._conn.execute(sql, (self._tenant, t_ns, t_ns, now_epoch))
            raw_rows = [
                (rid, _unpack(blob), vfrom)
                for rid, blob, vfrom in cur.fetchall()
            ]

        if not raw_rows:
            return []

        if not query_text.strip():
            # Sin query: devolvemos los más recientes primero, sin score.
            raw_rows.sort(key=lambda r: r[2], reverse=True)
            return [
                RecallResult(lesson_id=rid, score=0.0, matched=False)
                for rid, _, _ in raw_rows
            ][:k]

        query_vec = self._embedder.embed(query_text)

        scored: list[tuple[float, int, str]] = []
        for rid, vec, vfrom in raw_rows:
            cosine = _cosine_similarity(query_vec, vec)
            age = max(0, t_ns - vfrom)
            if half_life_ns is not None and half_life_ns > 0:
                combined = cosine * (0.5 ** (age / half_life_ns))
            else:
                # Coseno puro; valid_from_ns desc como desempate determinista.
                combined = cosine
            # Guardamos (combined, vfrom, rid) para sort: combined desc, vfrom desc.
            scored.append((combined, vfrom, rid))

        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

        return [
            RecallResult(
                lesson_id=rid,
                score=combined,
                matched=combined >= self._threshold,
            )
            for combined, _vfrom, rid in scored[:k]
        ]

    def recall_lexical(
        self,
        query_text: str,
        *,
        k: int = 10,
        memory_class: str = "factual",
        now_epoch: float | None = None,
    ) -> list[RecallResult]:
        """Búsqueda léxica BM25 sobre el índice FTS5.

        Solo disponible cuando el índice se creó con ``lexical_index=True``.
        Respeta tenant, superseded y expiry igual que ``recall_all``.

        Los términos de la query se escapan envolviendo cada uno en comillas dobles
        para que caracteres especiales FTS (guiones, operadores, etc.) no rompan
        la sintaxis.

        Raises:
            RuntimeError: si el índice fue creado con ``lexical_index=False``.
        """
        if not self._lexical_index:
            raise RuntimeError(
                "recall_lexical requiere lexical_index=True en el constructor."
            )
        # Escapado: cada token entre comillas dobles → '"tok1" "tok2"'
        terms = query_text.split()
        escaped = " ".join(f'"{t}"' for t in terms) if terms else '""'

        # Obtener record_ids vigentes del tenant (para filtrar FTS).
        valid_ids: set[str] = {
            row[0]
            for row in self._rows(memory_class=memory_class, now_epoch=now_epoch)
        }

        try:
            rows = self._conn.execute(
                """
                SELECT m.record_id, bm25(records_fts)
                FROM records_fts
                JOIN records_fts_map m ON records_fts.rowid = m.fts_rowid
                WHERE records_fts MATCH ?
                ORDER BY bm25(records_fts)
                LIMIT ?
                """,
                (escaped, k * 10),  # sobresolicitamos para filtrar por tenant/valid
            ).fetchall()
        except Exception:
            # FTS fallback por si la query sigue siendo sintácticamente inválida.
            return []

        results: list[RecallResult] = []
        for record_id, bm25_score in rows:
            if record_id not in valid_ids:
                continue
            # bm25() en SQLite devuelve valores negativos (más negativo = más relevante).
            # Normalizamos a positivo para RecallResult.score.
            results.append(RecallResult(lesson_id=record_id, score=-bm25_score, matched=True))
            if len(results) >= k:
                break

        return results

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

    def ids_by_prefix(self, prefix: str) -> list[str]:
        """Ids VIGENTES (valid_until_ns IS NULL) del tenant actual cuyo id
        empieza por `prefix`, orden alfabético. Opera sobre la columna `id` en
        claro (no descifra texto) — para el contenido usar `text_of` por id.
        Usada por `atlas handoff` para enumerar memorias migradas del harness
        (`ids_by_prefix("harness:")`) sin depender de `record_type`, que no se
        persiste en el schema SQL."""
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = self._conn.execute(
            "SELECT id FROM records WHERE tenant=? AND valid_until_ns IS NULL "
            "AND id LIKE ? ESCAPE '\\' ORDER BY id",
            (self._tenant, escaped + "%"),
        ).fetchall()
        return [str(row[0]) for row in rows]

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
        # Sincronización FTS: borrar la fila del índice léxico si está activo.
        if self._lexical_index:
            self._fts_delete(record_id)
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
