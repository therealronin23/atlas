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
import urllib.error
import urllib.request
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
# Counter-sign transport type alias + HTTP implementation
# ---------------------------------------------------------------------------

# Transporte con respuesta: recibe (witness_id, payload) y devuelve la
# counter-signature del testigo como str, o None si falla.
CounterSignTransport = Callable[[str, bytes], "str | None"]


class HttpWitnessTransport:
    """Transporte HTTP real que hace POST del payload y recibe counter-signature.

    Usa solo ``urllib.request`` (stdlib). En caso de error de red realiza un
    único reintento; si sigue fallando loguea un warning y devuelve ``None``
    sin propagar la excepción.

    Parameters
    ----------
    endpoints:
        Mapa ``witness_id → URL`` donde hacer POST.
    timeout_s:
        Timeout por intento en segundos (default 5).
    """

    def __init__(
        self,
        endpoints: dict[str, str],
        *,
        timeout_s: float = 5.0,
    ) -> None:
        self._endpoints = endpoints
        self._timeout_s = timeout_s

    def post(self, witness_id: str, payload: bytes) -> "str | None":
        """POST *payload* al endpoint del testigo y devuelve la counter-signature.

        Parameters
        ----------
        witness_id:
            Identificador del testigo; se resuelve en URL vía ``endpoints``.
        payload:
            Bytes del GossipMessage serializado.

        Returns
        -------
        str | None
            Body de la respuesta HTTP decodificado como UTF-8, o ``None`` si el
            testigo no está registrado o si la petición falla tras el reintento.
        """
        url = self._endpoints.get(witness_id)
        if url is None:
            _log.warning("HttpWitnessTransport: unknown witness_id %r", witness_id)
            return None

        def _attempt() -> str:
            req = urllib.request.Request(
                url,
                data=payload,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                body: bytes = resp.read()
                return body.decode("utf-8")

        try:
            return _attempt()
        except (urllib.error.URLError, TimeoutError) as exc:
            _log.warning(
                "HttpWitnessTransport: first attempt failed for %r (%s); retrying",
                witness_id,
                exc,
            )

        try:
            return _attempt()
        except (urllib.error.URLError, TimeoutError) as exc:
            _log.warning(
                "HttpWitnessTransport: retry failed for %r (%s); giving up",
                witness_id,
                exc,
            )
            return None


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
    counter_transport:
        Transport opcional que devuelve la counter-signature del testigo como
        str hex, o None si falla.
    witness_verifiers:
        Mapa ``witness_id → SigVerifier`` usado para verificar criptográficamente
        cada counter-signature antes de contarla. Si es ``None`` o si un
        ``witness_id`` no tiene entrada en el mapa, la counter-signature NO se
        cuenta (safe default: falla cerrada).
    """

    def __init__(
        self,
        sig_verifier: SigVerifier,
        transport: Transport | None = None,
        counter_transport: CounterSignTransport | None = None,
        witness_verifiers: "dict[str, SigVerifier] | None" = None,
    ) -> None:
        self._sig_verifier = sig_verifier
        self._transport: Transport = transport if transport is not None else _noop_transport
        self._counter_transport: CounterSignTransport | None = counter_transport
        self._witness_verifiers: dict[str, SigVerifier] = witness_verifiers or {}
        # witness_id → Witness (local references para observe())
        self._witnesses: dict[str, "Witness"] = {}  # type: ignore[name-defined]
        # witness_id → set de tree_size vistos (para check_quorum)
        self._seen_by: dict[str, set[int]] = {}
        # tree_size → {witness_id: counter_signature_str} — solo firmas verificadas
        self._counter_sigs: dict[int, dict[str, str]] = {}

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

            # Counter-signature opcional: solicita al testigo remoto que firme
            # el STH para reforzar la garantía anti-split-view.
            # La firma se verifica criptográficamente antes de contarla; si no
            # hay verifier para el testigo o la firma es inválida, NO se cuenta
            # (safe default: falla cerrada — una string arbitraria no da quórum).
            if self._counter_transport is not None:
                try:
                    sig = self._counter_transport(wid, payload)
                except Exception as exc:  # noqa: BLE001
                    _log.warning(
                        "counter_transport error for witness %r: %s", wid, exc
                    )
                    sig = None
                if sig is not None:
                    verifier = self._witness_verifiers.get(wid)
                    if verifier is None:
                        _log.warning(
                            "no verifier for witness %r; counter-sig not counted", wid
                        )
                    else:
                        try:
                            sig_bytes_ok = verifier.verify(payload, sig)
                        except Exception as exc:  # noqa: BLE001
                            _log.warning(
                                "counter-sig verification error for witness %r: %s",
                                wid, exc,
                            )
                            sig_bytes_ok = False
                        if sig_bytes_ok:
                            tree_size = message.sth.tree_size
                            self._counter_sigs.setdefault(tree_size, {})[wid] = sig
                        else:
                            _log.warning(
                                "counter-sig failed verification for witness %r; "
                                "not counted",
                                wid,
                            )

    def counter_signature_coverage(self, tree_size: int) -> int:
        """Devuelve el número de counter-signatures recibidas para *tree_size*.

        Returns
        -------
        int
            0 si no hay counter_transport configurado o no hay sigs para el
            tree_size dado.
        """
        return len(self._counter_sigs.get(tree_size, {}))

    def has_quorum(self, tree_size: int, *, min_witnesses: int = 2) -> bool:
        """Comprueba si hay suficientes counter-signatures para *tree_size*.

        Un quórum se considera alcanzado cuando el número de counter-signatures
        recibidas es mayor o igual que *min_witnesses*.

        Parameters
        ----------
        tree_size:
            Tamaño del árbol del STH a comprobar.
        min_witnesses:
            Umbral mínimo de firmas (default 2).

        Returns
        -------
        bool
            True si ``counter_signature_coverage(tree_size) >= min_witnesses``.
        """
        return self.counter_signature_coverage(tree_size) >= min_witnesses

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
