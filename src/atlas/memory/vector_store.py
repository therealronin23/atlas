"""
Atlas Core — Vector + Graph Memory con KuzuDB (ADR-008, Gate D/D4).

Wrapper que expone una API sencilla sobre KuzuDB:

  - Nodos: Pattern, Failure, Evidence (con embedding fijo de `dim`).
  - Aristas: DERIVED_FROM (Pattern -> Failure), SUPPORTS (Evidence -> Pattern),
             SIMILAR_TO (Pattern <-> Pattern).
  - Busqueda semantica: cosine similarity calculada en Python sobre los
    vectores almacenados. Suficiente hasta ~10k filas. Para escala mayor
    se usara el HNSW extension de Kuzu en un follow-up (esta diferido).

La verdad bruta sigue viviendo en JSON files (memory_system.py) — Kuzu
es el indice semantico y el grafo de relaciones. Insertar en Kuzu falla
de forma silenciosa si Kuzu no esta disponible (degradacion grace).
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import kuzu

from atlas.memory.embeddings import (
    Embedder,
    StubEmbedder,
    embedding_identity_fingerprint,
)


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Resultados tipados
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PatternHit:
    id: str
    text: str
    tags: list[str]
    created_at: str
    score: float


@dataclass(frozen=True)
class FailureHit:
    id: str
    error_type: str
    description: str
    solution: str
    occurred_at: str
    score: float


@dataclass(frozen=True)
class EvidenceHit:
    id: str
    text: str
    source: str
    created_at: str
    score: float


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------


class VectorStoreError(Exception):
    """Fallo del store (esquema, dim mismatch, IO de Kuzu)."""


# ---------------------------------------------------------------------------
# Store principal
# ---------------------------------------------------------------------------


META_KEY_DIM = "embedding_dim"
META_KEY_IDENTITY = "embedding_identity"
META_KEY_FINGERPRINT = "embedding_fingerprint"
META_KEY_VERSION = "schema_version"
SCHEMA_VERSION = "1"


class KuzuVectorStore:
    """
    Indice semantico + grafo sobre KuzuDB embedded.

    Uso tipico:

        store = KuzuVectorStore(db_path=..., embedder=StubEmbedder())
        pid = store.add_pattern("usar pytest -k para filtrar", tags=["pytest", "cli"])
        hits = store.find_similar_patterns("filtrar tests pytest", top_k=3)
        store.close()

    El esquema se crea idempotente al abrir; si la dim del embedder cambia
    respecto a una DB existente, se eleva VectorStoreError (recrear DB con
    recreate=True o cambiar embedder).
    """

    def __init__(
        self,
        db_path: Path,
        embedder: Embedder | None = None,
        *,
        recreate: bool = False,
        max_db_size: int = 1 << 30,
    ) -> None:
        self._db_path = db_path
        self._embedder: Embedder = embedder or StubEmbedder()
        if recreate and db_path.exists():
            # KuzuDB usa archivos + un directorio aux: eliminar todo lo que matchee
            import shutil
            if db_path.is_dir():
                shutil.rmtree(db_path)
            else:
                db_path.unlink()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._db = kuzu.Database(str(db_path), max_db_size=max_db_size)
        self._conn = kuzu.Connection(self._db)
        self._init_schema()
        self._verify_dim()
        self._verify_identity()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        # Kuzu 0.11 cierra al GC; explicit close por simetria.
        try:
            del self._conn
            del self._db
        except Exception:  # pragma: no cover
            pass

    @property
    def embedder(self) -> Embedder:
        return self._embedder

    @property
    def dim(self) -> int:
        return self._embedder.dim

    # ------------------------------------------------------------------
    # Inserciones
    # ------------------------------------------------------------------

    def add_pattern(
        self,
        text: str,
        *,
        tags: list[str] | None = None,
        pattern_id: str | None = None,
    ) -> str:
        pid = pattern_id or str(uuid.uuid4())
        vec = self._embedder.embed(text)
        self._conn.execute(
            "CREATE (:Pattern {id: $id, text: $text, tags: $tags, "
            "embedding: $vec, created_at: $ts})",
            {
                "id": pid,
                "text": text,
                "tags": json.dumps(tags or []),
                "vec": vec,
                "ts": _now_iso(),
            },
        )
        return pid

    def add_failure(
        self,
        *,
        error_type: str,
        description: str,
        solution: str,
        failure_id: str | None = None,
    ) -> str:
        fid = failure_id or str(uuid.uuid4())
        vec = self._embedder.embed(f"{error_type}\n{description}\n{solution}")
        self._conn.execute(
            "CREATE (:Failure {id: $id, error_type: $et, description: $d, "
            "solution: $s, embedding: $vec, occurred_at: $ts})",
            {
                "id": fid,
                "et": error_type,
                "d": description,
                "s": solution,
                "vec": vec,
                "ts": _now_iso(),
            },
        )
        return fid

    def add_evidence(
        self,
        text: str,
        *,
        source: str,
        evidence_id: str | None = None,
    ) -> str:
        eid = evidence_id or str(uuid.uuid4())
        vec = self._embedder.embed(text)
        self._conn.execute(
            "CREATE (:Evidence {id: $id, text: $text, source: $source, "
            "embedding: $vec, created_at: $ts})",
            {
                "id": eid,
                "text": text,
                "source": source,
                "vec": vec,
                "ts": _now_iso(),
            },
        )
        return eid

    # ------------------------------------------------------------------
    # Aristas
    # ------------------------------------------------------------------

    def link_derived_from(self, pattern_id: str, failure_id: str) -> None:
        self._conn.execute(
            "MATCH (p:Pattern {id: $pid}), (f:Failure {id: $fid}) "
            "CREATE (p)-[:DERIVED_FROM]->(f)",
            {"pid": pattern_id, "fid": failure_id},
        )

    def link_supports(self, evidence_id: str, pattern_id: str) -> None:
        self._conn.execute(
            "MATCH (e:Evidence {id: $eid}), (p:Pattern {id: $pid}) "
            "CREATE (e)-[:SUPPORTS]->(p)",
            {"eid": evidence_id, "pid": pattern_id},
        )

    def link_similar(self, pattern_a: str, pattern_b: str, similarity: float) -> None:
        self._conn.execute(
            "MATCH (a:Pattern {id: $a}), (b:Pattern {id: $b}) "
            "CREATE (a)-[:SIMILAR_TO {similarity: $sim}]->(b)",
            {"a": pattern_a, "b": pattern_b, "sim": float(similarity)},
        )

    # ------------------------------------------------------------------
    # Busqueda semantica (cosine sim en Python)
    # ------------------------------------------------------------------

    def find_similar_patterns(self, query: str, *, top_k: int = 5) -> list[PatternHit]:
        qvec = self._embedder.embed(query)
        result = self._conn.execute(
            "MATCH (p:Pattern) RETURN p.id, p.text, p.tags, p.embedding, p.created_at"
        )
        return _rank_patterns(result, qvec, top_k)

    def find_similar_failures(self, query: str, *, top_k: int = 5) -> list[FailureHit]:
        qvec = self._embedder.embed(query)
        result = self._conn.execute(
            "MATCH (f:Failure) RETURN f.id, f.error_type, f.description, "
            "f.solution, f.embedding, f.occurred_at"
        )
        return _rank_failures(result, qvec, top_k)

    def find_similar_evidence(self, query: str, *, top_k: int = 5) -> list[EvidenceHit]:
        qvec = self._embedder.embed(query)
        result = self._conn.execute(
            "MATCH (e:Evidence) RETURN e.id, e.text, e.source, e.embedding, e.created_at"
        )
        return _rank_evidence(result, qvec, top_k)

    # ------------------------------------------------------------------
    # Conteos / utilidades
    # ------------------------------------------------------------------

    def count(self, node_type: str) -> int:
        if node_type not in ("Pattern", "Failure", "Evidence"):
            raise VectorStoreError(f"node_type invalido: {node_type}")
        result = self._conn.execute(f"MATCH (n:{node_type}) RETURN count(n)")
        rows: list[Any] = list(result)
        return int(rows[0][0]) if rows else 0

    def get_pattern(self, pattern_id: str) -> dict[str, Any] | None:
        result = self._conn.execute(
            "MATCH (p:Pattern {id: $id}) RETURN p.id, p.text, p.tags, p.created_at",
            {"id": pattern_id},
        )
        rows: list[Any] = list(result)
        if not rows:
            return None
        pid, text, tags, ts = rows[0]
        return {
            "id": pid,
            "text": text,
            "tags": json.loads(tags) if tags else [],
            "created_at": ts,
        }

    # ------------------------------------------------------------------
    # Schema + verificacion
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        dim = self._embedder.dim
        # AtlasMeta primero — para registrar la dim
        self._exec_ignore_exists(
            "CREATE NODE TABLE AtlasMeta (key STRING, value STRING, PRIMARY KEY (key))"
        )
        self._exec_ignore_exists(
            f"CREATE NODE TABLE Pattern ("
            f"  id STRING, text STRING, tags STRING,"
            f"  embedding DOUBLE[{dim}], created_at STRING,"
            f"  PRIMARY KEY (id))"
        )
        self._exec_ignore_exists(
            f"CREATE NODE TABLE Failure ("
            f"  id STRING, error_type STRING, description STRING, solution STRING,"
            f"  embedding DOUBLE[{dim}], occurred_at STRING,"
            f"  PRIMARY KEY (id))"
        )
        self._exec_ignore_exists(
            f"CREATE NODE TABLE Evidence ("
            f"  id STRING, text STRING, source STRING,"
            f"  embedding DOUBLE[{dim}], created_at STRING,"
            f"  PRIMARY KEY (id))"
        )
        self._exec_ignore_exists(
            "CREATE REL TABLE DERIVED_FROM (FROM Pattern TO Failure)"
        )
        self._exec_ignore_exists(
            "CREATE REL TABLE SUPPORTS (FROM Evidence TO Pattern)"
        )
        self._exec_ignore_exists(
            "CREATE REL TABLE SIMILAR_TO (FROM Pattern TO Pattern, similarity DOUBLE)"
        )

        # Insertar metadata si la DB es nueva (no falla si ya esta)
        self._upsert_meta(META_KEY_DIM, str(dim))
        self._upsert_meta(META_KEY_VERSION, SCHEMA_VERSION)

    def _verify_dim(self) -> None:
        stored = self._read_meta(META_KEY_DIM)
        if stored is None:
            return
        if int(stored) != self._embedder.dim:
            raise VectorStoreError(
                f"Dim mismatch: DB tiene embedding_dim={stored} pero el embedder "
                f"actual usa dim={self._embedder.dim}. Recrea con recreate=True "
                f"o usa el embedder original."
            )

    def _verify_identity(self) -> None:
        """Verify the exact embedding space, not merely its vector length."""
        try:
            current_identity = self._embedder.identity
            declared_fingerprint = self._embedder.fingerprint
        except AttributeError as exc:
            raise VectorStoreError(
                "Embedder lacks a stable identity; persistent vector storage "
                "requires Embedder.identity and Embedder.fingerprint."
            ) from exc
        current_fingerprint = embedding_identity_fingerprint(current_identity)
        if declared_fingerprint != current_fingerprint:
            raise VectorStoreError(
                "Embedder fingerprint is inconsistent with Embedder.identity; "
                "refusing persistent vector storage."
            )
        stored_identity = self._read_meta(META_KEY_IDENTITY)
        stored_fingerprint = self._read_meta(META_KEY_FINGERPRINT)

        if stored_identity is None and stored_fingerprint is None:
            vector_count = sum(
                self.count(node_type)
                for node_type in ("Pattern", "Failure", "Evidence")
            )
            if vector_count:
                raise VectorStoreError(
                    f"Store {self._db_path.name} contains vectors but lacks embedder "
                    "identity metadata. Recreate it with the intended embedder; "
                    "dimension alone cannot prove the vector space."
                )
            self._upsert_meta(META_KEY_IDENTITY, current_identity)
            self._upsert_meta(META_KEY_FINGERPRINT, current_fingerprint)
            return

        if stored_identity is not None:
            expected_stored_fingerprint = embedding_identity_fingerprint(stored_identity)
            if (
                stored_fingerprint is not None
                and stored_fingerprint != expected_stored_fingerprint
            ):
                raise VectorStoreError(
                    f"Embedder identity metadata is inconsistent in "
                    f"{self._db_path.name}; recreate the store."
                )
            if stored_identity != current_identity:
                raise VectorStoreError(
                    f"Embedder identity mismatch: store {self._db_path.name} uses "
                    f"{stored_identity!r}, current embedder uses {current_identity!r}. "
                    "Use the original embedder or recreate the store."
                )
            if stored_fingerprint is None:
                self._upsert_meta(META_KEY_FINGERPRINT, expected_stored_fingerprint)
            return

        if stored_fingerprint != current_fingerprint:
            raise VectorStoreError(
                f"Embedder identity mismatch: store {self._db_path.name} has "
                f"fingerprint {stored_fingerprint!r}, current embedder has "
                f"{current_fingerprint!r}. Use the original embedder or recreate "
                "the store."
            )
        self._upsert_meta(META_KEY_IDENTITY, current_identity)

    def _upsert_meta(self, key: str, value: str) -> None:
        existing = self._read_meta(key)
        if existing is None:
            self._conn.execute(
                "CREATE (:AtlasMeta {key: $k, value: $v})",
                {"k": key, "v": value},
            )

    def _read_meta(self, key: str) -> str | None:
        result = self._conn.execute(
            "MATCH (m:AtlasMeta {key: $k}) RETURN m.value",
            {"k": key},
        )
        rows: list[Any] = list(result)
        return str(rows[0][0]) if rows else None

    def _exec_ignore_exists(self, cypher: str) -> None:
        try:
            self._conn.execute(cypher)
        except RuntimeError as e:
            # Kuzu lanza RuntimeError con 'already exists' si la tabla existe
            if "already exists" in str(e).lower() or "exist" in str(e).lower():
                return
            raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rank_patterns(
    result: Any, qvec: list[float], top_k: int
) -> list[PatternHit]:
    scored: list[PatternHit] = []
    for row in result:
        pid, text, tags, emb, ts = row
        score = cosine_similarity(qvec, list(emb))
        scored.append(
            PatternHit(
                id=str(pid),
                text=str(text),
                tags=json.loads(tags) if tags else [],
                created_at=str(ts),
                score=score,
            )
        )
    scored.sort(key=lambda h: h.score, reverse=True)
    return scored[:top_k]


def _rank_failures(
    result: Any, qvec: list[float], top_k: int
) -> list[FailureHit]:
    scored: list[FailureHit] = []
    for row in result:
        fid, et, desc, sol, emb, ts = row
        score = cosine_similarity(qvec, list(emb))
        scored.append(
            FailureHit(
                id=str(fid),
                error_type=str(et),
                description=str(desc),
                solution=str(sol),
                occurred_at=str(ts),
                score=score,
            )
        )
    scored.sort(key=lambda h: h.score, reverse=True)
    return scored[:top_k]


def _rank_evidence(
    result: Any, qvec: list[float], top_k: int
) -> list[EvidenceHit]:
    scored: list[EvidenceHit] = []
    for row in result:
        eid, text, source, emb, ts = row
        score = cosine_similarity(qvec, list(emb))
        scored.append(
            EvidenceHit(
                id=str(eid),
                text=str(text),
                source=str(source),
                created_at=str(ts),
                score=score,
            )
        )
    scored.sort(key=lambda h: h.score, reverse=True)
    return scored[:top_k]
