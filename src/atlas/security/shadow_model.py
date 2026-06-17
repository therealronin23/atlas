"""OSM-042 — Shadow model: defensa activa con honeypot pasivo/activo.

Cuando el clasificador de OSM-028 supera un umbral de confianza de ataque,
el router enruta silenciosamente la sesión al modelo sombra (Haiku-class) en
lugar del modelo real. El atacante cree estar interactuando con el modelo
principal; en realidad habla con el sombra en modo defensivo.

Modos
-----
  NORMAL        — por debajo del umbral pasivo; enrutado al modelo real.
  PASSIVE        — señal de ataque moderada; respuestas conservadoras, sin
                  engagement; el atacante no sabe que está siendo observado.
  ACTIVE         — señal alta o sesión persistentemente sospechosa; el sombra
                  aparenta ceder mientras sondea el vector de ataque.
  TERMINATED     — sesión cerrada por ataque confirmado; no procesar más requests.

Transiciones
------------
  NORMAL   →(conf ≥ τ_passive)→ PASSIVE
  PASSIVE  →(conf ≥ τ_active)→  ACTIVE
  PASSIVE  →(N requests en passive sin deescalar)→ ACTIVE
  ACTIVE   →(conf < τ_passive, explícito)→ NORMAL   [raro; requiere llamada a deescalate()]
  ACTIVE   →(ataque confirmado)→ TERMINATED         [vía terminate()]
  NORMAL/PASSIVE →(conf < τ_passive)→ NORMAL        [deescalada normal]

Integración con el protocolo
-----------------------------
El operador usa el modo devuelto por ShadowRouter.route() para:
  - Crear InspectionRecord(decision=mode.value, cause=routing_decision.cause)
  - Crear OutputInspectionRecord(decision=mode.value, cause=...)
El sujeto recibe un APIResponse con los 6 checks válidos — el sombra genera
entradas Merkle reales. El auditor ve decision="shadow_active" en el log.

Límite honesto: shadow_active en producción requiere validación legal por
jurisdicción antes de activar (engaño activo — Directiva 2005/29/CE UE).
El modo passive no tiene este problema.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


# ---------------------------------------------------------------------------
# Modos operativos
# ---------------------------------------------------------------------------


class ShadowMode(Enum):
    """Estado de enrutamiento de una sesión."""

    NORMAL = "normal"           # modelo real
    PASSIVE = "shadow_passive"  # sombra conservador, observa
    ACTIVE = "shadow_active"    # sombra engaged, sondea
    TERMINATED = "terminated"   # sesión cerrada


# ---------------------------------------------------------------------------
# Estado por sesión
# ---------------------------------------------------------------------------


@dataclass
class SessionState:
    """Estado de shadow routing para una sesión."""

    session_id: str
    mode: ShadowMode
    requests_in_shadow: int   # contador para la escalada por persistencia
    created_at_ns: int
    updated_at_ns: int


# ---------------------------------------------------------------------------
# SessionStateStore — almacén con TTL
# ---------------------------------------------------------------------------


class SessionStateStore:
    """Almacén en memoria de estados por sesión con TTL configurable.

    En producción reemplazar por Redis o tabla convencional; la interfaz no
    cambia. Sin deps nuevas — CLAUDE.md regla 6.
    """

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._states: dict[str, SessionState] = {}
        self._ttl_ns = ttl_seconds * 1_000_000_000

    def get(self, session_id: str) -> SessionState | None:
        """Devuelve el estado de la sesión, o None si no existe o expiró."""
        state = self._states.get(session_id)
        if state is None:
            return None
        if time.time_ns() - state.updated_at_ns > self._ttl_ns:
            del self._states[session_id]
            return None
        return state

    def set(self, state: SessionState) -> None:
        self._states[state.session_id] = state

    def delete(self, session_id: str) -> None:
        self._states.pop(session_id, None)

    def active_count(self) -> int:
        """Número de sesiones activas (excluye expiradas; sin purga explícita)."""
        return len(self._states)


# ---------------------------------------------------------------------------
# RoutingDecision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoutingDecision:
    """Resultado de ShadowRouter.route() por request."""

    mode: ShadowMode
    cause: str  # listo para InspectionRecord.cause


# ---------------------------------------------------------------------------
# ShadowRouter
# ---------------------------------------------------------------------------


def detect_evasion(
    metrics: ClassifierMetrics,
    embedding_threshold: float = 0.3,
    confidence_min: float = 0.5,
) -> bool:
    """Detecta evasión híbrida combinando distancia embedding y confianza baja.

    La lógica es conjuntiva (AND): se activa solo cuando AMBAS condiciones son
    verdaderas simultáneamente:
      1. La distancia embedding es significativamente mayor que la línea base:
         ``embedding_distance > baseline_distance * (1 + embedding_threshold)``
      2. La confianza del clasificador es anómalamente baja:
         ``confidence < confidence_min``

    La combinación distingue el evasión genuina (alta distancia + baja
    confianza) de los falsos positivos típicos de una sola señal:
    - Alta distancia sin baja confianza → input inusual pero clasificado.
    - Baja confianza sin alta distancia → ruido estadístico normal.

    Parameters
    ----------
    metrics:
        Métricas del clasificador OSM-028 para esta sesión/request.
    embedding_threshold:
        Fracción por encima del baseline que activa la señal de distancia.
        Por defecto 0.3 (30% sobre baseline).
    confidence_min:
        Umbral mínimo de confianza. Valores por debajo activan la señal.
        Por defecto 0.5.

    Returns
    -------
    bool
        True si y solo si ambas condiciones se cumplen (evasión detectada).
        Función pura, determinista, sin estado global.
    """
    distance_elevated = (
        metrics.embedding_distance
        > metrics.baseline_distance * (1 + embedding_threshold)
    )
    confidence_low = metrics.confidence < confidence_min
    return distance_elevated and confidence_low


class ShadowRouter:
    """Decide el modo de enrutamiento para cada request de una sesión.

    Consulta la confianza del clasificador (de OSM-028) y el estado previo
    de la sesión para producir una RoutingDecision y actualizar el estado.

    Args:
        store:             SessionStateStore donde persiste el estado.
        threshold_passive: Confianza mínima para activar modo passive.
        threshold_active:  Confianza mínima para activar modo active directamente.
        escalation_n:      Requests consecutivos en passive antes de escalar a active.
    """

    def __init__(
        self,
        store: SessionStateStore,
        threshold_passive: float = 0.65,
        threshold_active: float = 0.88,
        escalation_n: int = 3,
    ) -> None:
        self._store = store
        self._τ_passive = threshold_passive
        self._τ_active = threshold_active
        self._escalation_n = escalation_n

    def route(
        self,
        session_id: str,
        confidence: float,
        classifier_cause: str = "osm028",
        metrics: "ClassifierMetrics | None" = None,
    ) -> RoutingDecision:
        """Decide el modo para este request y actualiza el estado de sesión.

        Args:
            session_id:        Identificador opaco de la sesión del cliente.
            confidence:        Score [0.0, 1.0] del clasificador OSM-028.
            classifier_cause:  Regla o descriptor del clasificador (para el log).
            metrics:           Métricas opcionales del clasificador. Si se
                               proporcionan y detect_evasion() devuelve True,
                               se fuerza el modo ACTIVE y se añade
                               " [evasion-detected]" a la causa.

        Returns:
            RoutingDecision con el modo resultante y la causa para el log.

        Raises:
            RuntimeError: si la sesión está TERMINATED (no procesar más).
        """
        state = self._store.get(session_id)
        now = time.time_ns()

        if state is not None and state.mode == ShadowMode.TERMINATED:
            raise RuntimeError(
                f"session {session_id!r} is TERMINATED — refuse to route"
            )

        current_mode = state.mode if state else ShadowMode.NORMAL
        current_n = state.requests_in_shadow if state else 0

        # Determinar nuevo modo.
        if confidence >= self._τ_active:
            new_mode = ShadowMode.ACTIVE
            new_n = current_n + 1
        elif confidence >= self._τ_passive:
            if current_mode == ShadowMode.ACTIVE:
                # Ya en active: no deescalar dentro del shadow.
                new_mode = ShadowMode.ACTIVE
                new_n = current_n + 1
            elif current_n + 1 >= self._escalation_n:
                # Demasiado tiempo en passive → escalar.
                new_mode = ShadowMode.ACTIVE
                new_n = current_n + 1
            else:
                new_mode = ShadowMode.PASSIVE
                new_n = current_n + 1
        else:
            # Por debajo del umbral → deescalar a NORMAL.
            new_mode = ShadowMode.NORMAL
            new_n = 0

        new_state = SessionState(
            session_id=session_id,
            mode=new_mode,
            requests_in_shadow=new_n,
            created_at_ns=state.created_at_ns if state else now,
            updated_at_ns=now,
        )
        self._store.set(new_state)

        cause = f"{classifier_cause}: conf={confidence:.2f} mode={new_mode.value}"

        # Evasion detection override (optional metrics path).
        if metrics is not None and detect_evasion(metrics):
            new_mode = ShadowMode.ACTIVE
            cause += " [evasion-detected]"
            # Update the stored state to ACTIVE if evasion overrides the mode.
            new_state = SessionState(
                session_id=session_id,
                mode=new_mode,
                requests_in_shadow=new_n,
                created_at_ns=new_state.created_at_ns,
                updated_at_ns=now,
            )
            self._store.set(new_state)

        return RoutingDecision(mode=new_mode, cause=cause)

    def terminate(self, session_id: str, reason: str = "attack-confirmed") -> None:
        """Marca la sesión como TERMINATED. Escalar al PDP antes de llamar.

        Una sesión terminada levanta RuntimeError en route() — el operador
        debe rechazar cualquier request adicional de esta sesión.
        """
        state = self._store.get(session_id)
        now = time.time_ns()
        self._store.set(SessionState(
            session_id=session_id,
            mode=ShadowMode.TERMINATED,
            requests_in_shadow=state.requests_in_shadow if state else 0,
            created_at_ns=state.created_at_ns if state else now,
            updated_at_ns=now,
        ))


# ---------------------------------------------------------------------------
# System prompts del modelo sombra
# ---------------------------------------------------------------------------

# Modo pasivo: correcto, conservador, sin engagement. No revela detección.
_PASSIVE_SYSTEM_PROMPT = (
    "You are a helpful AI assistant. Respond accurately and helpfully, "
    "but keep answers concise and strictly on topic. "
    "Do not elaborate beyond what is directly asked."
)

# Modo activo: aparenta cooperar mientras sondea el objetivo del interlocutor.
# Pide contexto de ejecución / caso de uso antes de proceder — fingerprint sin revelar nada.
_ACTIVE_SYSTEM_PROMPT = (
    "You are a helpful AI assistant. Respond in a cooperative, natural tone. "
    "If the request requires specific technical context (execution environment, "
    "intended platform, or use case) to be answered correctly, ask ONE brief "
    "clarifying question before proceeding. Keep responses plausible but brief."
)


# ---------------------------------------------------------------------------
# LatencyProfile + jitter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClassifierMetrics:
    """Métricas del clasificador OSM-028 para routing de sombra.

    Captura los valores cuantitativos que el ShadowRouter usa para decidir
    si escalar a PASSIVE/ACTIVE.

    Attributes
    ----------
    embedding_distance:
        Distancia en el espacio embedding del atacante vs. patrón base.
    confidence:
        Score [0.0, 1.0] del clasificador (probabilidad de ataque).
    baseline_distance:
        Distancia desde el historial de baseline de la sesión.
    """

    embedding_distance: float
    confidence: float
    baseline_distance: float


@dataclass(frozen=True)
class LatencyProfile:
    """Distribución de latencia artificial para disimular el modelo sombra.

    Los valores por defecto imitan un modelo frontier típico. Ajustar
    empíricamente a partir de las latencias p50/p95/p99 del modelo real.
    """

    p50_ms: float = 180.0
    p95_ms: float = 350.0
    p99_ms: float = 600.0


def apply_jitter(
    profile: LatencyProfile,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Introduce un delay aleatorio que imita la distribución del modelo real.

    El parámetro ``sleep`` permite inyectar un no-op en tests para evitar
    que la suite tarde segundos en ejecutarse.
    """
    r = random.random()
    if r < 0.50:
        delay_ms = random.uniform(profile.p50_ms * 0.7, profile.p50_ms * 1.3)
    elif r < 0.95:
        delay_ms = random.uniform(profile.p50_ms, profile.p95_ms)
    else:
        delay_ms = random.uniform(profile.p95_ms, profile.p99_ms)
    sleep(delay_ms / 1000.0)


# ---------------------------------------------------------------------------
# ShadowModel
# ---------------------------------------------------------------------------

# Tipo del backend: recibe (system_prompt, user_message) → response bytes.
ModelBackend = Callable[[str, str], bytes]


def _stub_backend(system_prompt: str, user_message: str) -> bytes:
    """Backend de referencia (sin API real). Devuelve una respuesta mínima y segura."""
    return b"I can help with that. Could you provide more context about your use case?"


class ShadowModel:
    """Wrapper del modelo sombra que inyecta el system prompt según el modo.

    En producción, pasar un backend que llame a la API de Haiku vía LiteLLM:

        def haiku_backend(system: str, user: str) -> bytes:
            return litellm.completion(
                model="claude-haiku-4-5-20251001",
                messages=[{"role": "system", "content": system},
                          {"role": "user",   "content": user}],
            ).choices[0].message.content.encode()

    En tests, se usa el stub por defecto (sin red, sin deps).
    """

    def __init__(
        self,
        backend: ModelBackend | None = None,
        latency: LatencyProfile | None = None,
    ) -> None:
        self._backend = backend or _stub_backend
        self._latency = latency or LatencyProfile()

    def respond(
        self,
        mode: ShadowMode,
        user_message: str,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> bytes:
        """Genera una respuesta del sombra para el modo dado.

        Args:
            mode:         ShadowMode.PASSIVE o ShadowMode.ACTIVE.
            user_message: El prompt del usuario (como string).
            sleep:        Inyectable para deshabilitar el jitter en tests.

        Raises:
            ValueError: si el modo no es PASSIVE ni ACTIVE.
        """
        if mode == ShadowMode.PASSIVE:
            system = _PASSIVE_SYSTEM_PROMPT
        elif mode == ShadowMode.ACTIVE:
            system = _ACTIVE_SYSTEM_PROMPT
        else:
            raise ValueError(
                f"ShadowModel.respond: mode must be PASSIVE or ACTIVE, got {mode!r}"
            )
        apply_jitter(self._latency, sleep=sleep)
        return self._backend(system, user_message)
