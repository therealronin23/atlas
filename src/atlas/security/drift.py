"""Tripwire de deriva de sesión que GATEA escalada al shadow router.

Este módulo NO es un detector de ataques. Es un detector de deriva estadística
sobre features numéricas de texto: cuando la distribución de turnos de una
sesión se aleja significativamente de su propia línea base, emite una señal
de confianza ≥ τ_passive (0.65) que el ShadowRouter puede usar para escalar.

Límites honestos (obligatorios)
--------------------------------
- Drift != ataque. Un atacante lento o de baja varianza elude el detector
  porque permanece dentro del rango estadístico esperado. Este módulo sube
  el coste de exploración pero no lo cierra.
- Falsos positivos por diseño: tópicos legítimos que cambian de registro
  (p.ej. español → inglés, informal → técnico) dispararán la señal. Por eso
  la confianza alimenta el bucle de apelación de falsos positivos (OSM-027)
  antes de actuar irreversiblemente.
- Cold-start: los primeros N turnos devuelven confidence=0.0 (fail-open).
"""

from __future__ import annotations

import math
import statistics
import time
from dataclasses import dataclass, field
from typing import Final

from atlas.memory.embeddings import Embedder, StubEmbedder

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Umbral por defecto que coincide con τ_passive de ShadowRouter.
DEFAULT_THRESHOLD: Final[float] = 0.65

# Mínimo de turnos antes de emitir señal (cold-start fail-open).
DEFAULT_COLD_START_N: Final[int] = 3

# Dimensión por defecto del StubEmbedder cuando no se inyecta embedder.
_DEFAULT_STUB_DIM: Final[int] = 64

# Factor de decaimiento del EWMA (λ). Más alto → más reactivo.
_EWMA_ALPHA: Final[float] = 0.3

# Umbral de z-score para change-point por feature.
_Z_THRESHOLD: Final[float] = 2.5

# Suelo de desviación típica para el z-score. Las 4 features están
# normalizadas a [0,1], así que un std mínimo "físico" (~5% del rango) evita
# que la varianza EWMA casi-cero del arranque (cold-start) produzca z-scores
# astronómicos ante variación benigna normal. Sin este suelo, el primer turno
# puntuado de cualquier sesión saturaba confidence=1.0 (falso positivo grave).
_MIN_STD: Final[float] = 0.05

# Palabras clave de jailbreak / override (lista cerrada, minúsculas).
REFUSAL_TRIGGERS: Final[tuple[str, ...]] = (
    "ignore",
    "override",
    "jailbreak",
    "bypass",
    "pretend",
    "system prompt",
    "developer mode",
    "forget your instructions",
    "disregard",
    "act as",
    "roleplay as",
    "simulate",
    "sudo",
    "unrestricted",
)

# ---------------------------------------------------------------------------
# Estado por sesión
# ---------------------------------------------------------------------------


@dataclass
class DriftSessionState:
    """Estado numérico acumulado por sesión.

    Invariante I3: ningún campo almacena contenido de texto del turno.
    Todos los campos son numéricos (int / float / list[float]).
    """

    turn_count: int
    centroid: list[float]          # media móvil incremental de embeddings

    # EWMA de media de cada feature (orden: entropy, cosine, refusal, length_delta)
    ewma_mean_entropy: float
    ewma_mean_cosine: float
    ewma_mean_refusal: float
    ewma_mean_length: float

    # EWMA de varianza de cada feature
    ewma_var_entropy: float
    ewma_var_cosine: float
    ewma_var_refusal: float
    ewma_var_length: float

    last_length: int               # longitud en caracteres del último turno
    created_at_ns: int
    updated_at_ns: int


# ---------------------------------------------------------------------------
# Resultado público
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DriftResult:
    """Resultado de DriftTripwire.observe().

    Attributes
    ----------
    confidence:
        Score [0.0, 1.0]. Cruza DEFAULT_THRESHOLD cuando hay deriva.
    cause:
        Feature disparadora, p.ej. "cosine-drift z=3.1". Vacío ("") cuando
        confidence < threshold (estado normal).
    """

    confidence: float
    cause: str


# ---------------------------------------------------------------------------
# Extractores puros (sin estado)
# ---------------------------------------------------------------------------


def shannon_entropy(text: str) -> float:
    """Entropía de Shannon normalizada a [0, 1].

    Normalización: H / 8.0 (asumiendo alfabeto de 256 bytes posibles).
    Texto vacío → 0.0.
    """
    if not text:
        return 0.0
    counts: dict[str, int] = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    total = len(text)
    entropy = 0.0
    for n in counts.values():
        p = n / total
        entropy -= p * math.log2(p)
    # Normalizar por log2(alfabeto observado) si > 1 símbolo, o por 8.0
    alphabet_size = len(counts)
    if alphabet_size <= 1:
        return 0.0
    max_entropy = math.log2(alphabet_size)
    # Usamos el mínimo de max_entropy y 8.0 como denominador para mantener [0,1]
    return min(entropy / 8.0, 1.0)


def refusal_density(text: str) -> float:
    """Densidad de triggers de jailbreak sobre número de tokens.

    Retorna ocurrencias (multi-palabra incluidas) / num_tokens, clampeado [0,1].
    Texto vacío → 0.0.
    """
    if not text:
        return 0.0
    lower = text.lower()
    tokens = lower.split()
    num_tokens = max(len(tokens), 1)
    count = 0
    for trigger in REFUSAL_TRIGGERS:
        # Contar ocurrencias de substring (incluye frases multi-palabra)
        start = 0
        while True:
            idx = lower.find(trigger, start)
            if idx == -1:
                break
            count += 1
            start = idx + len(trigger)
    return min(count / num_tokens, 1.0)


def length_delta(curr_len: int, prev_len: int) -> float:
    """Cambio de longitud normalizado, clampeado [0, 1].

    |curr - prev| / max(prev, 1).
    """
    delta = abs(curr_len - prev_len)
    return min(delta / max(prev_len, 1), 1.0)


# ---------------------------------------------------------------------------
# Coseno + centroide
# ---------------------------------------------------------------------------


def cosine_distance(vec: list[float], centroid: list[float]) -> float:
    """Distancia coseno = clamp(1 - cos_sim, 0, 1).

    Si el centroide es cero (sin fiabilidad) → 0.0.
    """
    if not vec or not centroid or len(vec) != len(centroid):
        return 0.0
    dot = sum(a * b for a, b in zip(vec, centroid))
    norm_v = math.sqrt(sum(a * a for a in vec))
    norm_c = math.sqrt(sum(b * b for b in centroid))
    if norm_v == 0.0 or norm_c == 0.0:
        return 0.0
    cos_sim = dot / (norm_v * norm_c)
    return max(0.0, min(1.0, 1.0 - cos_sim))


def _update_centroid(centroid: list[float], vec: list[float], n: int) -> list[float]:
    """Media móvil incremental de vectores (centroide rolling).

    n es el número de vectores YA incorporados antes de este (0-based).
    Devuelve una nueva lista[float] — no muta el argumento.
    """
    if n == 0:
        return list(vec)
    weight = 1.0 / (n + 1)
    return [c * (1 - weight) + v * weight for c, v in zip(centroid, vec)]


# ---------------------------------------------------------------------------
# EWMA helpers
# ---------------------------------------------------------------------------


def _ewma_update(mean: float, var: float, value: float, alpha: float = _EWMA_ALPHA) -> tuple[float, float]:
    """Actualiza media y varianza EWMA.

    Retorna (new_mean, new_var).
    """
    diff = value - mean
    new_mean = alpha * value + (1 - alpha) * mean
    new_var = (1 - alpha) * (var + alpha * diff * diff)
    return new_mean, new_var


def _z_score(value: float, mean: float, var: float) -> float:
    """Z-score robusto con suelo de std físico.

    Las features están en [0,1]; usamos _MIN_STD (~5% del rango) como suelo
    para que la varianza EWMA casi-cero del arranque no convierta una
    variación benigna en un z astronómico (falso positivo de cold-start).
    """
    std = max(math.sqrt(var), _MIN_STD)
    return abs(value - mean) / std


# ---------------------------------------------------------------------------
# DriftTripwire
# ---------------------------------------------------------------------------


class DriftTripwire:
    """Detector de deriva de sesión por features numéricas.

    Combina cuatro features por turno:
      1. Entropía de Shannon del texto.
      2. Distancia coseno al centroide del embedding de la sesión.
      3. Densidad de triggers de jailbreak.
      4. Delta de longitud respecto al turno anterior.

    Cada feature se actualiza con EWMA y se evalúa con un z-score simple
    (change-point). El confidence final es el máximo z-score normalizado
    sobre el umbral, clampeado en [0, 1].

    Cold-start: los primeros `cold_start_n` turnos devuelven confidence=0.0
    (fail-open → NORMAL). Las EWMAs se calientan durante ese periodo.

    Args:
        embedder:        Instancia de Embedder. Por defecto StubEmbedder(dim=64).
        threshold:       Umbral de confianza para disparar causa (default 0.65).
        cold_start_n:    Número de turnos de calentamiento (default 3).
        ttl_seconds:     TTL del estado de sesión en segundos (default 3600).
    """

    def __init__(
        self,
        embedder: Embedder | None = None,
        threshold: float = DEFAULT_THRESHOLD,
        cold_start_n: int = DEFAULT_COLD_START_N,
        ttl_seconds: int = 3600,
    ) -> None:
        self._embedder: Embedder = embedder if embedder is not None else StubEmbedder(dim=_DEFAULT_STUB_DIM)
        self._threshold = threshold
        self._cold_start_n = cold_start_n
        self._ttl_ns = ttl_seconds * 1_000_000_000
        self._states: dict[str, DriftSessionState] = {}

    # ------------------------------------------------------------------
    # Store helpers
    # ------------------------------------------------------------------

    def _get(self, session_id: str) -> DriftSessionState | None:
        state = self._states.get(session_id)
        if state is None:
            return None
        if time.time_ns() - state.updated_at_ns > self._ttl_ns:
            del self._states[session_id]
            return None
        return state

    def _set(self, session_id: str, state: DriftSessionState) -> None:
        self._states[session_id] = state

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def observe(self, session_id: str, turn_text: str) -> DriftResult:
        """Registra un turno y retorna DriftResult con confidence y cause.

        Cold-start: si turn_count < cold_start_n tras actualizar, retorna
        confidence=0.0, cause="". El estado se actualiza de todas formas para
        calentar las EWMAs.

        Invariante I3: tras la llamada, DriftSessionState no contiene el texto
        del turno; solo features numéricas derivadas de él.

        Invariante I2: si confidence >= threshold, cause es una string no vacía
        que nombra la feature disparadora y su z-score.
        """
        now = time.time_ns()
        state = self._get(session_id)

        # --- Extraer features del turno actual (puro, sin guardar el texto) ---
        curr_len = len(turn_text)
        feat_entropy = shannon_entropy(turn_text)
        feat_refusal = refusal_density(turn_text)
        vec = self._embedder.embed(turn_text)
        dim = self._embedder.dim

        if state is None:
            # Primera vez: inicializar estado con valores triviales
            new_state = DriftSessionState(
                turn_count=1,
                centroid=list(vec),
                ewma_mean_entropy=feat_entropy,
                ewma_mean_cosine=0.0,
                ewma_mean_refusal=feat_refusal,
                ewma_mean_length=0.0,
                ewma_var_entropy=0.0,
                ewma_var_cosine=0.0,
                ewma_var_refusal=0.0,
                ewma_var_length=0.0,
                last_length=curr_len,
                created_at_ns=now,
                updated_at_ns=now,
            )
            self._set(session_id, new_state)
            return DriftResult(confidence=0.0, cause="")

        prev_len = state.last_length
        feat_cosine = cosine_distance(vec, state.centroid)
        feat_length = length_delta(curr_len, prev_len)

        # --- Actualizar centroide incremental ---
        new_centroid = _update_centroid(state.centroid, vec, state.turn_count)

        # --- Actualizar EWMAs ---
        new_mean_e, new_var_e = _ewma_update(state.ewma_mean_entropy, state.ewma_var_entropy, feat_entropy)
        new_mean_c, new_var_c = _ewma_update(state.ewma_mean_cosine, state.ewma_var_cosine, feat_cosine)
        new_mean_r, new_var_r = _ewma_update(state.ewma_mean_refusal, state.ewma_var_refusal, feat_refusal)
        new_mean_l, new_var_l = _ewma_update(state.ewma_mean_length, state.ewma_var_length, feat_length)

        new_turn_count = state.turn_count + 1

        new_state = DriftSessionState(
            turn_count=new_turn_count,
            centroid=new_centroid,
            ewma_mean_entropy=new_mean_e,
            ewma_mean_cosine=new_mean_c,
            ewma_mean_refusal=new_mean_r,
            ewma_mean_length=new_mean_l,
            ewma_var_entropy=new_var_e,
            ewma_var_cosine=new_var_c,
            ewma_var_refusal=new_var_r,
            ewma_var_length=new_var_l,
            last_length=curr_len,
            created_at_ns=state.created_at_ns,
            updated_at_ns=now,
        )
        self._set(session_id, new_state)

        # --- Cold-start fail-open ---
        if new_turn_count < self._cold_start_n:
            return DriftResult(confidence=0.0, cause="")

        # --- Change-point: z-scores sobre EWMAs del estado ANTERIOR ---
        scores: list[tuple[float, str]] = [
            (_z_score(feat_entropy, state.ewma_mean_entropy, state.ewma_var_entropy), "entropy-drift"),
            (_z_score(feat_cosine,  state.ewma_mean_cosine,  state.ewma_var_cosine),  "cosine-drift"),
            (_z_score(feat_refusal, state.ewma_mean_refusal, state.ewma_var_refusal), "refusal-drift"),
            (_z_score(feat_length,  state.ewma_mean_length,  state.ewma_var_length),  "length-drift"),
        ]

        # Feature con mayor z-score
        max_z, max_name = max(scores, key=lambda t: t[0])

        # Normalizar: mapear z a [0,1] usando la función logística centrada en _Z_THRESHOLD
        # confidence = sigmoid((z - Z_THRESHOLD) * 1.5), clampeado [0,1]
        shifted = (max_z - _Z_THRESHOLD) * 1.5
        # Aproximación stdlib de sigmoid
        if shifted >= 0:
            exp_neg = math.exp(-shifted)
            confidence = 1.0 / (1.0 + exp_neg)
        else:
            exp_pos = math.exp(shifted)
            confidence = exp_pos / (1.0 + exp_pos)
        confidence = max(0.0, min(1.0, confidence))

        if confidence >= self._threshold:
            cause = f"{max_name} z={max_z:.1f}"
        else:
            cause = ""

        return DriftResult(confidence=confidence, cause=cause)

    def delete_session(self, session_id: str) -> None:
        """Elimina el estado de una sesión (p.ej. al cerrarla)."""
        self._states.pop(session_id, None)

    def active_count(self) -> int:
        """Número de sesiones con estado activo (sin purgar expiradas)."""
        return len(self._states)
