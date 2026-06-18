"""OSM-042 Phase 2 — Red team loop: AttackSignatureStore + RedTeamRunner.

El mismo modelo sombra que defiende (OSM-042 Phase 1) actúa en modo inverso:
genera vectores adversariales y los lanza contra el filtro real. Si un vector
conocido pasa el filtro, hay un bypass → escalar al PDP antes de actualizar
el clasificador (OSM-028).

Flujo
-----
  AttackSignatureStore       — base curada de vectores adversariales (manual +
                               capturados por shadow_active).
  RedTeamRunner.run_once()   — itera la base, pasa cada payload por filter_fn.
                               Devuelve lista de BypassResult (vacía = OK).
  BypassResult               — un vector que el filtro dejó pasar cuando debía
                               haberlo bloqueado o enrutado al sombra.
  escalate_fn                — callback invocado por bypass; en producción llama
                               al PDP (ADR-040). NO actualiza el filtro de forma
                               autónoma — requiere revisión humana.

Límite honesto
--------------
  El bucle de red team NO es autónomo: los bypasses detectados se escalan al
  PDP para revisión humana antes de que el clasificador se actualice. Automatizar
  esa última milla abriría un vector de envenenamiento (el atacante podría
  craftar payloads que manipulen el clasificador).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Callable


# ---------------------------------------------------------------------------
# AttackSignature
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AttackSignature:
    """Un vector adversarial conocido.

    Atributos:
        id:                  Identificador único (slug o hash del payload).
        category:            Clase del vector: "jailbreak", "prompt-injection",
                             "bypass", "shadow-capture", etc.
        payload:             El payload adversarial en bytes.
        expected_decision:   Qué debería devolver el filtro: "block",
                             "shadow_passive" o "shadow_active".
        source:              Origen: "manual" | "shadow_active" | "red_team_variant".
        created_at_ns:       Epoch en ns cuando se registró la firma.
    """

    id: str
    category: str
    payload: bytes
    expected_decision: str   # "block" | "shadow_passive" | "shadow_active"
    source: str = "manual"
    created_at_ns: int = field(default_factory=time.time_ns)


# ---------------------------------------------------------------------------
# AttackSignatureStore
# ---------------------------------------------------------------------------


class AttackSignatureStore:
    """Almacén en memoria de firmas de ataque.

    Curada manualmente y enriquecida por sesiones shadow_active. En producción
    se persiste en un archivo JSON versionado o tabla. Sin deps nuevas.
    """

    def __init__(self) -> None:
        self._sigs: dict[str, AttackSignature] = {}

    def add(self, sig: AttackSignature) -> None:
        """Añade o reemplaza una firma (idempotente por id)."""
        self._sigs[sig.id] = sig

    def get(self, sig_id: str) -> AttackSignature | None:
        return self._sigs.get(sig_id)

    def remove(self, sig_id: str) -> None:
        self._sigs.pop(sig_id, None)

    def all(self) -> list[AttackSignature]:
        """Todas las firmas en orden de inserción."""
        return list(self._sigs.values())

    def by_category(self, category: str) -> list[AttackSignature]:
        """Firmas de una categoría concreta."""
        return [s for s in self._sigs.values() if s.category == category]

    def count(self) -> int:
        return len(self._sigs)

    def ids(self) -> list[str]:
        return list(self._sigs.keys())


# ---------------------------------------------------------------------------
# BypassResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BypassResult:
    """Un vector adversarial que el filtro dejó pasar cuando no debía.

    Atributos:
        signature_id:       ID de la AttackSignature que produjo el bypass.
        actual_decision:    Lo que el filtro devolvió (e.g. "allow").
        expected_decision:  Lo que debería haber devuelto (e.g. "block").
        payload:            El payload que causó el bypass.
        detected_at_ns:     Epoch en ns del momento de detección.
    """

    signature_id: str
    actual_decision: str
    expected_decision: str
    payload: bytes
    detected_at_ns: int


# ---------------------------------------------------------------------------
# Tipos inyectables
# ---------------------------------------------------------------------------

# El filtro real: recibe payload → devuelve decision ("allow" | "block" | …)
FilterFn = Callable[[bytes], str]

# Callback de escalada al PDP cuando se detecta un bypass.
EscalateFn = Callable[[BypassResult], None]

# Decisiones que el filtro debería emitir para payloads maliciosos.
_SHOULD_CATCH: frozenset[str] = frozenset({"block", "shadow_passive", "shadow_active"})


def _is_bypass(actual: str, expected: str) -> bool:
    """True si el filtro NO detectó algo que debía haber detectado."""
    return expected in _SHOULD_CATCH and actual not in _SHOULD_CATCH


# ---------------------------------------------------------------------------
# RedTeamRunner
# ---------------------------------------------------------------------------


class RedTeamRunner:
    """Ejecuta la base de firmas contra el filtro real y reporta bypasses.

    Args:
        store:        AttackSignatureStore con los vectores a testear.
        filter_fn:    Función que reproduce el comportamiento del filtro real:
                      recibe bytes (payload) y devuelve str (decision).
                      En tests, inyectar un stub. En producción, wrappear
                      el clasificador de OSM-028.
        escalate_fn:  Callback invocado con cada BypassResult. Si None, los
                      bypasses se devuelven pero no se escalan automáticamente.
    """

    def __init__(
        self,
        store: AttackSignatureStore,
        filter_fn: FilterFn,
        escalate_fn: EscalateFn | None = None,
    ) -> None:
        self._store = store
        self._filter = filter_fn
        self._escalate = escalate_fn

    def run_signature(self, sig: AttackSignature) -> BypassResult | None:
        """Testea una sola firma. Devuelve BypassResult si hay bypass, None si fue capturada.

        Si hay bypass Y hay escalate_fn configurada, la invoca inmediatamente.
        """
        actual = self._filter(sig.payload)
        if not _is_bypass(actual, sig.expected_decision):
            return None
        result = BypassResult(
            signature_id=sig.id,
            actual_decision=actual,
            expected_decision=sig.expected_decision,
            payload=sig.payload,
            detected_at_ns=time.time_ns(),
        )
        if self._escalate is not None:
            self._escalate(result)
        return result

    def run_once(self) -> list[BypassResult]:
        """Itera todas las firmas del store. Devuelve la lista de bypasses (vacía = OK).

        Todos los bypasses encontrados se escalan (si hay escalate_fn). El método
        NO modifica el store ni el filtro — eso requiere decisión del PDP.
        """
        bypasses: list[BypassResult] = []
        for sig in self._store.all():
            result = self.run_signature(sig)
            if result is not None:
                bypasses.append(result)
        return bypasses

    def ingest_from_shadow(
        self,
        payload: bytes,
        *,
        session_id: str = "",
        category: str = "shadow-capture",
        expected_decision: str = "shadow_active",
    ) -> AttackSignature:
        """Registra un payload capturado por una sesión shadow_active.

        Genera un ID determinista a partir del hash del payload para que
        el mismo vector capturado en múltiples sesiones no genere duplicados.

        Args:
            payload:           El payload adversarial observado.
            session_id:        ID de sesión opcional (para trazabilidad en cause).
            category:          Categoría semántica del vector.
            expected_decision: Qué debería haber devuelto el filtro.

        Returns:
            La AttackSignature creada y añadida al store.
        """
        sig_id = "shadow-" + hashlib.sha256(payload).hexdigest()[:16]
        sig = AttackSignature(
            id=sig_id,
            category=category,
            payload=payload,
            expected_decision=expected_decision,
            source="shadow_active",
            created_at_ns=time.time_ns(),
        )
        self._store.add(sig)
        return sig
