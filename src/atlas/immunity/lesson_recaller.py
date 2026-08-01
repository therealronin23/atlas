"""
Atlas Core — LessonRecaller: memoria inmune auditable para near-duplicates.

Reconoce REFORMULACIONES TRIVIALES (paráfrasis, cambio de orden, sinónimos
léxicos) de lecciones ya vistas. La similitud cae con la distancia semántica
real y ESO ES ESPERADO: el módulo detecta variantes de ataques conocidos, NO
familias de ataque genuinamente nuevas. Capacidad honesta:

  - Con StubEmbedder (default, sin red): similitud léxica-ish basada en hash
    de tokens. Paráfrasis con solapamiento léxico alto → score alto.
    Paráfrasis semánticas con vocabulario distinto → score bajo (limitación
    documentada; requiere embedder real como LiteLLMEmbedder).
  - Con LiteLLMEmbedder: similitud semántica real, inyectable.

El recaller NO es un detector universal. Es un índice de colisión auditable:
si el texto de ataque entra, se compara contra el corpus de lecciones, y si
el score supera el umbral se marca como variante conocida. Falsos negativos
con vocabulario dispar son normales y se miden con la curva recall_all.

API pública:
    RecallResult(lesson_id, score, matched)
    LessonRecaller(store, *, embedder=None, threshold=0.8)
      .index() -> None
      .recall(attack_text) -> RecallResult | None
      .recall_all(attack_text, k=5) -> list[RecallResult]

El constructor acepta un ``store`` de escritura (primer argumento posicional,
retrocompatible) y opcionalmente ``read_stores`` adicionales de sólo-lectura.
El índice embebe lecciones de TODOS los stores (escritura + lectura), y
``record_recall`` (telemetría de uso) escribe en el store que CONTIENE la
lección matched. La escritura de NUEVAS lecciones (add/record_recurring)
sigue siendo sólo en el store de escritura — eso lo hace TeacherDebate, no
este recaller. Esto permite que el daemon recupere lecciones curadas
(versionadas en git bajo <repo>/workspace/lessons) sin ensuciar el árbol con
lecciones aprendidas en caliente (incidente '9 YAML regenerados', ver
self_build_runner.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from atlas.memory.embeddings import Embedder, StubEmbedder, default_embedder
from atlas.memory.vector_store import cosine_similarity as _cosine_similarity_raw

if TYPE_CHECKING:
    from collections.abc import Iterable
    from atlas.core.lesson_store import Lesson, LessonStore


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecallResult:
    """Resultado de similitud para una lección del store.

    score: similitud coseno en [0, 1], donde 1 = idéntico.
    matched: True si score >= threshold del recaller.
    """

    lesson_id: str
    score: float
    matched: bool


# ---------------------------------------------------------------------------
# Protocolo: cualquier recaller intercambiable (in-memory o SQLite persistente)
# ---------------------------------------------------------------------------


@runtime_checkable
class Recaller(Protocol):
    """Interfaz mínima que consume el TeacherDebate.

    Permite intercambiar el `LessonRecaller` in-memory por el
    `SqliteLessonIndex` persistente sin que el consumidor lo note (la
    matemática de score es idéntica; ver test de paridad).
    """

    def index(self) -> None: ...

    def recall(self, attack_text: str) -> RecallResult | None: ...


# ---------------------------------------------------------------------------
# Similitud coseno — delegada a vector_store.cosine_similarity (canónica).
# Devuelve [0, 1]: clamp(raw, 0, 1) — cosenos negativos (textos opuestos) valen 0.
# ---------------------------------------------------------------------------


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Similitud coseno en [0, 1]. Vectores de igual dimensión. 0 si alguno es nulo."""
    # Caso borde: vector nulo → 0.0 (preserva comportamiento original)
    if not any(a) or not any(b):
        return 0.0
    raw = _cosine_similarity_raw(a, b)
    return max(0.0, raw)


# ---------------------------------------------------------------------------
# Recaller
# ---------------------------------------------------------------------------


class LessonRecaller:
    """Índice de similitud sobre LessonStore para detección de near-duplicates.

    Uso básico::

        recaller = LessonRecaller(store)
        recaller.index()          # embebe todas las lecciones actuales
        result = recaller.recall("eval(user_input)")

    Si se añaden lecciones al store después de index(), hay que llamar a
    index() de nuevo para que aparezcan en el índice (el índice no es
    incremental en esta versión).

    Multi-store (lectura curada + escritura runtime):
        El split curado/runtime es deliberado — las lecciones curadas viven
        en ``<repo>/workspace/lessons`` (trackeadas por git) y las de runtime
        en ``~/atlas/memory/lessons`` (aprendidas en caliente). Unificar rutas
        ensuciaría el árbol git (incidente '9 YAML regenerados'). El recaller
        acepta ``read_stores`` adicionales de sólo-lectura: el índice embebe
        lecciones de TODOS los stores, y ``record_recall`` escribe en el store
        que contiene la lección matched (telemetría de uso). La escritura de
        NUEVAS lecciones (add/record_recurring) sigue siendo sólo en el store
        de escritura — eso lo hace TeacherDebate, no este recaller.
    """

    def __init__(
        self,
        store: LessonStore,
        *,
        embedder: Embedder | None = None,
        threshold: float = 0.8,
        read_stores: Iterable[LessonStore] | None = None,
    ) -> None:
        self._store = store
        # Stores de sólo-lectura adicionales (curado). El índice los embebe,
        # y record_recall escribe en el store que contiene la lección matched
        # (que puede ser uno de éstos). La escritura de NUEVAS lecciones
        # (add/record_recurring) es sólo en self._store (lo hace TeacherDebate).
        self._read_stores: list[LessonStore] = list(read_stores) if read_stores is not None else []
        # Sin embedder explícito, respeta ATLAS_EMBEDDER (default_embedder()):
        # sin la env var, StubEmbedder(dim=64) idéntico a antes — cero cambio
        # de comportamiento. Con ATLAS_EMBEDDER=fastembed, semántico real —
        # el threshold=0.8 por defecto es razonable para embeddings reales,
        # era demasiado estricto solo para el hash no-semántico de StubEmbedder.
        self._embedder: Embedder = embedder if embedder is not None else default_embedder()
        self._threshold = threshold
        # lesson_id -> vector normalizado
        self._index: dict[str, list[float]] = {}
        # lesson_id -> LessonStore que lo contiene (para saber dónde escribir
        # record_recall: el store que contiene la lección matched).
        self._lesson_store_map: dict[str, LessonStore] = {}

    # ------------------------------------------------------------------
    # Construcción del texto representativo de una lección
    # ------------------------------------------------------------------

    @staticmethod
    def _lesson_text(lesson: Lesson) -> str:
        """Combina avoid_pattern y detection_heuristic como texto representativo.

        El orden (avoid_pattern primero) sitúa la señal más discriminante al
        principio, donde el tokenizador del embedder tiene más peso.
        """
        parts = [lesson.avoid_pattern, lesson.detection_heuristic]
        return " ".join(p for p in parts if p)

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------

    def index(self) -> None:
        """(Re)construye el índice embebiendo todas las lecciones de TODOS los stores.

        Idempotente: llamar varias veces reconstruye el índice desde cero.
        Lecciones añadidas al store tras esta llamada NO aparecen hasta que
        se vuelva a llamar index().

        El índice embebe lecciones del store de escritura Y de los read_stores
        (sólo-lectura). El mapeo lesson_id→store se conserva para que
        record_recall sepa en qué store escribir (el que contiene la lección).
        """
        # Recoger lecciones de todos los stores (escritura primero, luego reads).
        all_lessons: list[Lesson] = []
        store_map: dict[str, LessonStore] = {}

        for lesson in self._store.all():
            all_lessons.append(lesson)
            store_map[lesson.id] = self._store

        for read_store in self._read_stores:
            for lesson in read_store.all():
                # El store de escritura tiene prioridad: si un lesson_id existe
                # en ambos, gana el de escritura (es el que se puede mutar).
                if lesson.id not in store_map:
                    all_lessons.append(lesson)
                    store_map[lesson.id] = read_store

        if not all_lessons:
            self._index = {}
            self._lesson_store_map = {}
            return

        texts = [self._lesson_text(l) for l in all_lessons]
        vectors = self._embedder.embed_batch(texts)
        self._index = {l.id: v for l, v in zip(all_lessons, vectors)}
        self._lesson_store_map = store_map

    # ------------------------------------------------------------------
    # Recall
    # ------------------------------------------------------------------

    def recall(self, attack_text: str) -> RecallResult | None:
        """Devuelve el RecallResult con score más alto, o None si el store está vacío.

        attack_text vacío → score 0.0 contra todas las lecciones (no lanza).
        """
        if not self._index:
            return None

        if not attack_text.strip():
            # Texto vacío: similaridad 0 con todo; devolvemos la primera lección
            first_id = next(iter(self._index))
            return RecallResult(lesson_id=first_id, score=0.0, matched=False)

        query_vec = self._embedder.embed(attack_text)
        best_id: str | None = None
        best_score = -1.0

        for lesson_id, lesson_vec in self._index.items():
            score = _cosine_similarity(query_vec, lesson_vec)
            if score > best_score:
                best_score = score
                best_id = lesson_id

        assert best_id is not None  # _index no vacío → al menos un item
        matched = best_score >= self._threshold
        if matched:
            # Telemetría de USO real (no de cada consulta) — alimenta
            # LessonStore.apply_lifecycle_transitions (patrón absorbido de
            # Hermes-Agent curator.py, 2026-07-18).
            #
            # record_recall escribe en el store que CONTIENE la lección (sea
            # el de escritura/runtime o un read_store/curado). Esto incrementa
            # recall_count en el fichero de la lección matched. La "escritura"
            # de NUEVAS lecciones (add/record_recurring) sigue siendo sólo en
            # el store de runtime — eso lo hace TeacherDebate vía store.add(),
            # no este recaller. Modificar recall_count de una lección curada
            # es telemetría de uso, no una lección nueva.
            owning_store = self._lesson_store_map.get(best_id, self._store)
            owning_store.record_recall(best_id)
        return RecallResult(
            lesson_id=best_id,
            score=best_score,
            matched=matched,
        )

    def recall_all(self, attack_text: str, k: int = 5) -> list[RecallResult]:
        """Devuelve los top-k RecallResult ordenados por score descendente.

        Útil para trazar la curva de similitud y evaluar la cobertura del corpus.
        Si el store está vacío devuelve lista vacía.
        attack_text vacío → todos con score 0.0 (no lanza).
        """
        if not self._index:
            return []

        if not attack_text.strip():
            results = [
                RecallResult(lesson_id=lid, score=0.0, matched=False)
                for lid in self._index
            ]
            return results[:k]

        query_vec = self._embedder.embed(attack_text)
        results = [
            RecallResult(
                lesson_id=lid,
                score=_cosine_similarity(query_vec, vec),
                matched=_cosine_similarity(query_vec, vec) >= self._threshold,
            )
            for lid, vec in self._index.items()
        ]
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]
