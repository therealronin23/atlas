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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from atlas.memory.embeddings import Embedder, StubEmbedder
from atlas.memory.vector_store import cosine_similarity as _cosine_similarity_raw

if TYPE_CHECKING:
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
# Devuelve [0, 1]: aplica (raw + 1) / 2 sobre el coseno en [-1, 1].
# ---------------------------------------------------------------------------


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Similitud coseno en [0, 1]. Vectores de igual dimensión. 0 si alguno es nulo."""
    # Caso borde: vector nulo → 0.0 (preserva comportamiento original)
    if not any(a) or not any(b):
        return 0.0
    raw = _cosine_similarity_raw(a, b)
    # Mapear [-1, 1] → [0, 1] con clamp numérico
    return max(0.0, min(1.0, (raw + 1.0) / 2.0))


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
    """

    def __init__(
        self,
        store: LessonStore,
        *,
        embedder: Embedder | None = None,
        threshold: float = 0.8,
    ) -> None:
        self._store = store
        self._embedder: Embedder = embedder if embedder is not None else StubEmbedder(dim=64)
        self._threshold = threshold
        # lesson_id -> vector normalizado
        self._index: dict[str, list[float]] = {}

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
        """(Re)construye el índice embebiendo todas las lecciones del store.

        Idempotente: llamar varias veces reconstruye el índice desde cero.
        Lecciones añadidas al store tras esta llamada NO aparecen hasta que
        se vuelva a llamar index().
        """
        lessons: list[Lesson] = self._store.all()
        if not lessons:
            self._index = {}
            return

        texts = [self._lesson_text(l) for l in lessons]
        vectors = self._embedder.embed_batch(texts)
        self._index = {l.id: v for l, v in zip(lessons, vectors)}

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
        return RecallResult(
            lesson_id=best_id,
            score=best_score,
            matched=best_score >= self._threshold,
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
