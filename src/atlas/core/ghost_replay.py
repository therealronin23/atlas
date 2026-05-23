"""
Atlas Core — Ghost Replay cache (ADR-022, Gate D/D5)

Cache topologica de resultados de inferencia. Cuando el agente se enfrenta
a una tarea semanticamente identica a una ya resuelta, devuelve el
resultado cacheado en lugar de invocar al InferenceHub. Ahorro de 100%
en coste y latencia para subtareas repetidas.

Cache key: hash de (intent, sensitivity, context_signature). El
"context_signature" es libre — quien usa el cache decide que campos
del contexto cuentan para identidad (intencionalmente: dos llamadas con
el mismo intent pero contexto diferente NO comparten cache).

Cache value: resultado final + payload arbitrario (decisiones
intermedias, traza, tokens). Cada entrada lleva TTL y last_accessed
para LRU + expiracion.

Storage: ficheros JSON en disco bajo
    <base>/<hash[:2]>/<hash>.json
Esto distribuye en sub-carpetas y evita directorios con miles de
archivos.

Politica de evicition v1:
  - TTL absoluto: por defecto 24h. Configurable por entrada en record().
  - LRU por tamano: si count > max_entries, se eliminan los mas viejos
    por last_accessed.
  - purge(reason): drop total. Pensado para OperationalMode.DEGRADED
    (presion de memoria) o invalidacion manual.

Consultar ANTES de InferenceHub. Si hit: devolver cached + log
'ghost.hit'. Si miss: invocar inferencia + record() del resultado.
La integracion automatica en el pipeline (Orchestrator.handle_intent)
queda como follow-up cuando el flujo de inferencia este consumido por
mas codigo del sistema.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_TTL_SECONDS = 24 * 60 * 60   # 24 horas
DEFAULT_MAX_ENTRIES = 10_000


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------


class GhostReplayError(Exception):
    """Fallo de IO sobre el cache."""


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------


@dataclass
class GhostEntry:
    """Entrada cacheada. created_at + last_accessed son epoch seconds."""

    key: str
    intent: str
    sensitivity: str
    context_signature: str
    result: dict[str, Any]
    created_at: float
    last_accessed: float
    ttl_seconds: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, now: float | None = None) -> bool:
        if self.ttl_seconds <= 0:
            return False
        ts = time.time() if now is None else now
        return ts - self.created_at > self.ttl_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "key":               self.key,
            "intent":            self.intent,
            "sensitivity":       self.sensitivity,
            "context_signature": self.context_signature,
            "result":            self.result,
            "created_at":        self.created_at,
            "last_accessed":     self.last_accessed,
            "ttl_seconds":       self.ttl_seconds,
            "metadata":          self.metadata,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def compute_cache_key(intent: str, sensitivity: str, context_signature: str) -> str:
    """SHA-256 sobre los tres campos en orden canonico."""
    blob = f"{intent}\x1f{sensitivity}\x1f{context_signature}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class GhostReplay:
    """
    Cache topologica con TTL + LRU. Thread-safe via lock de grano grueso.
    """

    def __init__(
        self,
        cache_path: Path,
        *,
        default_ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ) -> None:
        if default_ttl_seconds < 0:
            raise ValueError("default_ttl_seconds no puede ser negativo")
        if max_entries <= 0:
            raise ValueError("max_entries debe ser positivo")
        self._base = cache_path
        self._base.mkdir(parents=True, exist_ok=True)
        self._default_ttl = default_ttl_seconds
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0, "expired": 0}

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def lookup(
        self,
        intent: str,
        sensitivity: str,
        context_signature: str,
    ) -> GhostEntry | None:
        key = compute_cache_key(intent, sensitivity, context_signature)
        path = self._path_for(key)
        with self._lock:
            if not path.exists():
                self._stats["misses"] += 1
                return None
            try:
                entry = self._read(path)
            except (json.JSONDecodeError, OSError, TypeError):
                self._stats["misses"] += 1
                return None
            if entry.is_expired():
                # Eliminar entrada caducada
                try:
                    path.unlink()
                except OSError:
                    pass
                self._stats["expired"] += 1
                self._stats["misses"] += 1
                return None
            # Touch: actualizar last_accessed
            entry.last_accessed = time.time()
            try:
                self._write(path, entry)
            except OSError:
                pass
            self._stats["hits"] += 1
            return entry

    # ------------------------------------------------------------------
    # Record
    # ------------------------------------------------------------------

    def record(
        self,
        intent: str,
        sensitivity: str,
        context_signature: str,
        result: dict[str, Any],
        *,
        ttl_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GhostEntry:
        key = compute_cache_key(intent, sensitivity, context_signature)
        now = time.time()
        entry = GhostEntry(
            key=key,
            intent=intent,
            sensitivity=sensitivity,
            context_signature=context_signature,
            result=result,
            created_at=now,
            last_accessed=now,
            ttl_seconds=ttl_seconds if ttl_seconds is not None else self._default_ttl,
            metadata=metadata or {},
        )
        path = self._path_for(key)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._write(path, entry)
            self._enforce_max_entries()
        return entry

    # ------------------------------------------------------------------
    # Purge
    # ------------------------------------------------------------------

    def purge(self, reason: str = "manual") -> int:
        """Borra TODAS las entradas. Devuelve el numero de entradas borradas."""
        with self._lock:
            removed = 0
            for f in self._base.rglob("*.json"):
                try:
                    f.unlink()
                    removed += 1
                except OSError:
                    continue
            self._stats["evictions"] += removed
            return removed

    def expire(self) -> int:
        """Recorre todo el cache y elimina entradas caducadas. Devuelve el numero."""
        with self._lock:
            now = time.time()
            removed = 0
            for f in self._base.rglob("*.json"):
                try:
                    entry = self._read(f)
                except (json.JSONDecodeError, OSError, TypeError):
                    continue
                if entry.is_expired(now):
                    try:
                        f.unlink()
                        removed += 1
                    except OSError:
                        continue
            self._stats["expired"] += removed
            return removed

    # ------------------------------------------------------------------
    # Inspeccion
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, int]:
        d = dict(self._stats)
        d["entries"] = self.count()
        return d

    def count(self) -> int:
        return sum(1 for _ in self._base.rglob("*.json"))

    # ------------------------------------------------------------------
    # Privado
    # ------------------------------------------------------------------

    def _path_for(self, key: str) -> Path:
        prefix = key[:2]
        return self._base / prefix / f"{key}.json"

    def _read(self, path: Path) -> GhostEntry:
        data = json.loads(path.read_text(encoding="utf-8"))
        return GhostEntry(**data)

    def _write(self, path: Path, entry: GhostEntry) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(entry.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _enforce_max_entries(self) -> None:
        files = list(self._base.rglob("*.json"))
        if len(files) <= self._max_entries:
            return
        # Cargar last_accessed de cada uno y ordenar ASC (mas viejo primero)
        annotated: list[tuple[float, Path]] = []
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                annotated.append((float(data.get("last_accessed", 0.0)), f))
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                # Corrupta: borrar
                try:
                    f.unlink()
                except OSError:
                    pass
                continue
        annotated.sort(key=lambda t: t[0])
        excess = len(annotated) - self._max_entries
        for _, f in annotated[:excess]:
            try:
                f.unlink()
                self._stats["evictions"] += 1
            except OSError:
                continue
