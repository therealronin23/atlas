"""ADR-053 Gossip protocol — distribución del Signed Tree Head entre observadores.

El protocolo gossip asegura que múltiples observadores independientes reciben
el mismo STH en aproximadamente la misma época. Si un operador envía STH
conflictivos a diferentes observadores, el gossip lo expone.

Un mensaje de gossip encapsula:
  - El STH confirmado por la log (el "truth")
  - El timestamp en que el observador lo recibió (para detecting skew)
  - El ID del observador que reporta (para rastreabilidad)
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from typing import Callable

from atlas.security.authorization import SigVerifier
from atlas.transparency.log import SignedTreeHead

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GossipMessage:
    """Mensaje de gossip que distribuye un Signed Tree Head.

    Attributes
    ----------
    witness_id:
        Identificador opaco del observador que reporta (e.g., UUID, fingerprint).
    sth:
        El Signed Tree Head confirmado por la log.
    received_at_ns:
        Timestamp en nanosegundos (UTC epoch) cuando el observador recibió el STH.
    """

    witness_id: str
    sth: SignedTreeHead
    received_at_ns: int

    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        """Serialización canónica del mensaje gossip para distribución.

        Formato: JSON compacto con claves ordenadas, sin espacios.
        El STH se serializa incluyendo sus campos directamente (no anidado).

        Returns
        -------
        bytes
            JSON canónico (sort_keys=True, separators=(',', ':')).
        """
        doc = {
            "received_at_ns": self.received_at_ns,
            "sth": {
                "algo": self.sth.algo,
                "root_hash": self.sth.root_hash.hex(),
                "signature": self.sth.signature,
                "timestamp": self.sth.timestamp,
                "tree_size": self.sth.tree_size,
            },
            "witness_id": self.witness_id,
        }
        return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()


# ---------------------------------------------------------------------------
# Transport type alias
# ---------------------------------------------------------------------------

# Transport callable: recibe (witness_id, message_bytes) y devuelve None.
# Inyectable para tests — la implementación HTTP real usa requests u httpx
# fuera del path crítico.
Transport = Callable[[str, bytes], None]


def _noop_transport(witness_id: str, message_bytes: bytes) -> None:
    """Transport por defecto: no hace nada (tests, embedded)."""


# ---------------------------------------------------------------------------
# WitnessNetwork
# ---------------------------------------------------------------------------


class WitnessNetwork:
    """Red de testigos RFC 9162 que distribuye STH por gossip y comprueba quórum.

    Parameters
    ----------
    sig_verifier:
        Verificador de firmas usado para validar los STH que cada Witness observa.
    transport:
        Callable(witness_id, message_bytes) para entregar el GossipMessage al
        testigo remoto. Inyectable: en tests se usa un stub; en producción se
        envía vía HTTP. El WitnessNetwork nunca importa requests directamente.
    """

    def __init__(
        self,
        sig_verifier: SigVerifier,
        transport: Transport | None = None,
    ) -> None:
        self._sig_verifier = sig_verifier
        self._transport: Transport = transport if transport is not None else _noop_transport
        # witness_id → Witness (local references para observe())
        self._witnesses: dict[str, "Witness"] = {}  # type: ignore[name-defined]
        # witness_id → set de tree_size vistos (para check_quorum)
        self._seen_by: dict[str, set[int]] = {}

    def register(self, witness_id: str, witness: "Witness") -> None:  # type: ignore[name-defined]
        """Registra un testigo local con el ID dado.

        Parameters
        ----------
        witness_id:
            Identificador único del testigo (opaco).
        witness:
            Instancia de :class:`~atlas.transparency.witness.Witness`.
        """
        self._witnesses[witness_id] = witness
        self._seen_by.setdefault(witness_id, set())

    def broadcast(self, message: GossipMessage) -> None:
        """Distribuye *message* a todos los testigos registrados.

        Para cada testigo:
        - Entrega el mensaje serializado vía el transport inyectado.
        - Llama a witness.observe(message.sth) para registrar el STH.
        - En caso de error (firma inválida, excepción del transport) registra
          en el log y continúa — un testigo defectuoso no aborta la red.

        Parameters
        ----------
        message:
            GossipMessage a distribuir.
        """
        payload = message.to_bytes()
        for wid, witness in self._witnesses.items():
            # Intento de entrega por transport (puede ser remoto).
            try:
                self._transport(wid, payload)
            except Exception as exc:  # noqa: BLE001
                _log.warning("transport error to witness %r: %s", wid, exc)
                continue

            # Observación local (verifica firma, detecta split-view).
            try:
                witness.observe(message.sth)
                self._seen_by[wid].add(message.sth.tree_size)
            except Exception as exc:  # noqa: BLE001
                _log.warning(
                    "witness %r rejected sth tree_size=%d: %s",
                    wid, message.sth.tree_size, exc,
                )

    def check_quorum(self, tree_size: int) -> bool:
        """Comprueba si >= ceil(2/3 * N) testigos han visto el STH para *tree_size*.

        Parameters
        ----------
        tree_size:
            Tamaño del árbol del STH a comprobar.

        Returns
        -------
        bool
            True si se alcanza el quórum de 2/3 sobre el total de testigos
            registrados. False si no hay testigos o no se alcanza el umbral.
        """
        n = len(self._witnesses)
        if n == 0:
            return False
        threshold = math.ceil(2 * n / 3)
        count = sum(
            1 for seen in self._seen_by.values() if tree_size in seen
        )
        return count >= threshold

    def detect_split_view_across_witnesses(self) -> bool:
        """Detecta split-view entre pares de testigos en la red.

        Itera sobre todos los pares de testigos registrados y comprueba si
        alguno detecta un conflicto (mismo tree_size, diferente root_hash).
        Reutiliza el método Witness.detect_split_view() para cada par.

        Returns
        -------
        bool
            True si algún par de testigos revela un split-view attack.
            False si no hay testigos, lista vacía, o ningún par conflicta.
        """
        witness_list = list(self._witnesses.values())
        if len(witness_list) < 2:
            return False

        # Itera sobre todos los pares de testigos.
        for i in range(len(witness_list)):
            for j in range(i + 1, len(witness_list)):
                w_i = witness_list[i]
                w_j = witness_list[j]
                # Comprueba todos los STHs vistos por w_i contra todos los de w_j.
                for tree_size_i, sth_i in w_i._seen.items():
                    for tree_size_j, sth_j in w_j._seen.items():
                        if w_i.detect_split_view(sth_i, sth_j):
                            return True
        return False
