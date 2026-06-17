"""ADR-053 Capas 2+2b — Co-firma del cliente con secuencia monótona + inspección de output.

El cliente co-firma cada request con un número de secuencia monótono.
Una laguna en la secuencia es detectable por el propio usuario: el operador
no puede omitir una inspección sin que el cliente lo detecte.

Flujo completo:
  1. ClientCosigner.sign_request(payload) → CosignedRequest   [cliente]
  2. API gateway (filtro in-path) recibe CosignedRequest,
     corre inspección, commit InspectionRecord al log Merkle   [operador]
  3. Respuesta incluye APIResponse con seq_ack + inclusion_proof + STH
  4. Cliente guarda réplica local; detect_omission() detecta huecos

El operador en este modelo es la infraestructura automatizada del proveedor
(API gateway), no una persona. Las omisiones son consecuencia de excepciones
de configuración o bypasses en la pipeline, no de decisiones individuales.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Sequence

from atlas.security.authorization import SigVerifier, Signer
from atlas.transparency.log import SignedTreeHead


# ---------------------------------------------------------------------------
# Request co-firmado
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CosignedRequest:
    """Un request co-firmado emitido por el cliente.

    El cuerpo firmado es canonical JSON de {payload_hash, seq} — sin
    timestamp (el timestamp lo pone el operador en InspectionRecord,
    evitando disputas de reloj entre cliente y servidor).
    """
    seq: int
    payload_hash: str   # SHA-256 hex del payload original
    signature: str      # firma sobre canonical_JSON({payload_hash, seq})

    def to_json(self) -> str:
        """Serialización canónica del request co-firmado (para InspectionRecord.cosig)."""
        return json.dumps(
            {"payload_hash": self.payload_hash, "seq": self.seq,
             "signature": self.signature},
            sort_keys=True, separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, data: str) -> "CosignedRequest":
        """Reconstruye un CosignedRequest desde su serialización canónica."""
        doc = json.loads(data)
        return cls(seq=doc["seq"], payload_hash=doc["payload_hash"],
                   signature=doc["signature"])


def _signing_body(seq: int, payload_hash: str) -> bytes:
    """Canonical bytes firmados: JSON compacto con claves ordenadas."""
    return json.dumps({"payload_hash": payload_hash, "seq": seq},
                      sort_keys=True, separators=(",", ":")).encode()


# ---------------------------------------------------------------------------
# ClientCosigner
# ---------------------------------------------------------------------------

class ClientCosigner:
    """Emite requests co-firmados con secuencia monótona estrictamente creciente.

    Args:
        signer: cualquier objeto que cumpla el Protocol ``Signer``.
        start_seq: primer número de secuencia (por defecto 0).
    """

    def __init__(self, signer: Signer, *, start_seq: int = 0) -> None:
        self._signer = signer
        self._next_seq = start_seq
        # Último seq emitido; -1 significa que aún no se emitió ninguno.
        self._last_seq: int = start_seq - 1

    @property
    def last_seq(self) -> int:
        """Último número de secuencia emitido (-1 si no se emitió ninguno)."""
        return self._last_seq

    def sign_request(self, payload: bytes) -> CosignedRequest:
        """Firma *payload* y devuelve un ``CosignedRequest`` con seq monótono."""
        seq = self._next_seq
        self._next_seq += 1
        self._last_seq = seq

        payload_hash = hashlib.sha256(payload).hexdigest()
        body = _signing_body(seq, payload_hash)
        signature = self._signer.sign(body)
        return CosignedRequest(seq=seq, payload_hash=payload_hash,
                               signature=signature)


# ---------------------------------------------------------------------------
# Verificación de co-firma
# ---------------------------------------------------------------------------

def verify_cosigned_request(
    request: CosignedRequest,
    payload: bytes,
    verifier: SigVerifier,
) -> bool:
    """Devuelve True si la co-firma es válida y el hash coincide con *payload*.

    Falla (False) si:
    - la firma no verifica con *verifier*;
    - el ``payload_hash`` no coincide con el hash real de *payload*.
    """
    expected_hash = hashlib.sha256(payload).hexdigest()
    if request.payload_hash != expected_hash:
        return False
    body = _signing_body(request.seq, request.payload_hash)
    return verifier.verify(body, request.signature)


# ---------------------------------------------------------------------------
# Registro de inspección (lado del operador)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InspectionRecord:
    """Registro que el filtro in-path crea por cada request inspeccionado.

    Committed al log Merkle ANTES de que el request se reenvíe al modelo.
    Esta ordering garantiza que si el cliente recibió una respuesta del
    modelo existe una InspectionRecord previa en el log (propiedad del
    diseño in-path, no propiedad criptográfica per se).

    Atributos:
        seq:          Número de secuencia del CosignedRequest.
        payload_hash: SHA-256 hex del payload — debe coincidir con CosignedRequest.
                      Permanece en el árbol para siempre; habilita check 4 (binding).
        cosig:        CosignedRequest serializado (JSON compacto).
        decision:     "allow" | "block" | "inspect"
        cause:        Regla o señal que disparó este evento (nunca vacío).
        timestamp_ns: Epoch en nanosegundos, asignado por el operador.
        salted_hash:  SHA-256(salt_i || payload) — OSM-007 crypto-shredding.
                      El salt se guarda FUERA del árbol en un SaltStore borrable.
                      Vacío ("") cuando el crypto-shredding no está configurado.
                      Destruir el salt → contenido irrecuperable sin tocar el árbol.
        model_version_hash: Hash del modelo que procesó este request (SHA-256 hex).
                           Vacío ("") si no hay tracking de versión.
    """
    seq: int
    payload_hash: str
    cosig: str          # json.dumps(CosignedRequest.__dict__ o equivalente)
    decision: str       # "allow" | "block" | "inspect"
    cause: str
    timestamp_ns: int
    salted_hash: str = ""  # SHA-256(salt || payload); "" si no hay crypto-shredding
    model_version_hash: str = ""  # SHA-256 hex del modelo; "" si no hay tracking

    def to_bytes(self) -> bytes:
        """Serialización canónica para append al TransparencyLog."""
        doc = {
            "cause": self.cause,
            "cosig": self.cosig,
            "decision": self.decision,
            "model_version_hash": self.model_version_hash,
            "payload_hash": self.payload_hash,
            "salted_hash": self.salted_hash,
            "seq": self.seq,
            "timestamp_ns": self.timestamp_ns,
        }
        return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()


# ---------------------------------------------------------------------------
# Registro de inspección de output (lado del operador — capa 2b)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OutputInspectionRecord:
    """Registro que el filtro crea para el OUTPUT del modelo, antes de devolverlo.

    Committed al log Merkle ANTES de que el resultado se reenvíe al cliente.
    Simétrico a InspectionRecord (que cubre el input). Juntos cierran la capa
    de inspección completa: input inspeccionado antes del modelo, output
    inspeccionado antes de la respuesta.

    Atributos:
        seq:         Número de secuencia — mismo que el CosignedRequest de entrada.
        output_hash: SHA-256 hex del output del modelo (bytes devueltos).
        decision:    "allow" | "block" | "shadow_passive" | "shadow_active"
        cause:       Regla o señal que disparó el evento (nunca vacío).
        timestamp_ns: Epoch en ns asignado por el operador.
    """
    seq: int
    output_hash: str   # SHA-256(result bytes) — ligado al resultado devuelto
    decision: str      # "allow" | "block" | "shadow_passive" | "shadow_active"
    cause: str
    timestamp_ns: int

    def to_bytes(self) -> bytes:
        """Serialización canónica para append al TransparencyLog."""
        doc = {
            "cause": self.cause,
            "decision": self.decision,
            "output_hash": self.output_hash,
            "record_type": "output",  # distingue de InspectionRecord en el log
            "seq": self.seq,
            "timestamp_ns": self.timestamp_ns,
        }
        return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()


# ---------------------------------------------------------------------------
# Respuesta de la API (lado del cliente — réplica local)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class APIResponse:
    """Mensaje de protocolo que el filtro in-path devuelve por cada request.

    Es el contrato completo de verificación. El cliente corre seis comprobaciones
    independientes contra material que ya posee o puede verificar:

      1. STH firmado: ``sth.verify(operator_log_verifier)`` — cabeza auténtica.
      2. Append-only: ``verify_consistency(...)`` — el log no fue reescrito.
      3. Inclusión input: el InspectionRecord está en el árbol.
      4. Binding input: ``payload_hash`` en ``leaf_bytes`` == hash firmado por el cliente.
      5. Inclusión output: el OutputInspectionRecord está en el mismo árbol.
      6. Binding output: ``SHA-256(result)`` == ``output_hash`` en ``output_leaf_bytes``.

    Checks 1-4 cierran: ack falso (3), reescritura (2), suplantación STH (1),
    sustitución de payload (4). Checks 5-6 cierran la inspección de output:
    el operador no puede omitir la inspección del resultado ni sustituirlo.
    Split-view sigue abierto (§6.1).

    El STH cubre ambas hojas (input + output se commitean en el mismo log).
    La prueba de consistencia es una sola, desde el último head verificado por
    el cliente hasta el head que cubre ambas hojas.

    Atributos:
        result:                  Respuesta del modelo (bytes).
        seq_ack:                 Secuencia reconocida por el operador.
        leaf_bytes:              InputInspectionRecord.to_bytes().
        leaf_index:              Índice de la hoja de input en el log.
        inclusion_proof:         Prueba RFC 9162 de la hoja input en ``sth``.
        sth:                     SignedTreeHead que cubre ambas hojas.
        consistency_proof:       Prueba append-only desde ``consistency_from``.
        consistency_from:        tree_size del último head verificado por el cliente.
        output_leaf_bytes:       OutputInspectionRecord.to_bytes().
        output_leaf_index:       Índice de la hoja de output en el log.
        output_inclusion_proof:  Prueba RFC 9162 de la hoja output en ``sth``.
    """
    result: bytes
    seq_ack: int
    leaf_bytes: bytes
    leaf_index: int
    inclusion_proof: list[bytes]
    sth: SignedTreeHead
    consistency_proof: list[bytes]
    consistency_from: int
    output_leaf_bytes: bytes
    output_leaf_index: int
    output_inclusion_proof: list[bytes]


# ---------------------------------------------------------------------------
# Detector de omisiones
# ---------------------------------------------------------------------------

def detect_omission(
    observed_seqs: Sequence[int],
    last_emitted: int,
) -> list[int]:
    """Devuelve los números de secuencia ausentes entre 0 y *last_emitted*.

    Args:
        observed_seqs: secuencias que el operador sí registró.
        last_emitted: último seq emitido por el cliente (inclusivo).

    Returns:
        Lista de enteros con los huecos, ordenada ascendentemente.
        Vacía si no falta nada.

    El rango esperado es ``[0, last_emitted]`` (asumiendo ``start_seq=0``).
    Huecos intermedios y finales son detectados.
    """
    if last_emitted < 0:
        return []
    observed_set = set(observed_seqs)
    return [s for s in range(last_emitted + 1) if s not in observed_set]


# ---------------------------------------------------------------------------
# OSM-040 — Recibo firmado + atribución de omisión bajo fallo de red
# ---------------------------------------------------------------------------
#
# Problema: un hueco en la secuencia tiene dos causas indistinguibles —
# omisión del operador, o fallo de red (la petición nunca llegó). Sin
# distinguirlas, el operador puede atribuir cualquier omisión real a "se cayó
# la red" (negación plausible).
#
# Solución: el operador emite un RECIBO firmado al RECIBIR la petición, antes
# de inspeccionar (fase 1, barato). Si el cliente tiene un recibo válido para
# seq=n pero el operador nunca exhibe inclusión para n, es una omisión
# ATRIBUIBLE: el operador admitió criptográficamente haber recibido la
# petición; ya no puede alegar fallo de red.


@dataclass(frozen=True)
class Receipt:
    """Acuse de recibo firmado por el operador al recibir un CosignedRequest.

    Fase 1 del protocolo de dos fases (recibo → inclusión). Es barato: no
    requiere inspección ni commit, solo firmar que la petición llegó. El
    cliente lo persiste localmente como prueba de entrega.

    Atributos:
        seq:            Secuencia del CosignedRequest acusado.
        payload_hash:   SHA-256 hex — debe coincidir con el CosignedRequest.
        received_at_ns: Epoch en ns que el operador asigna al recibir.
        signature:      Firma del operador sobre canonical_JSON.
    """
    seq: int
    payload_hash: str
    received_at_ns: int
    signature: str

    def signing_body(self) -> bytes:
        """Bytes canónicos firmados: JSON compacto con claves ordenadas."""
        return json.dumps(
            {"payload_hash": self.payload_hash,
             "received_at_ns": self.received_at_ns, "seq": self.seq},
            sort_keys=True, separators=(",", ":"),
        ).encode()


def verify_receipt(
    receipt: Receipt,
    expected_payload_hash: str,
    verifier: SigVerifier,
) -> bool:
    """True si el recibo está firmado por el operador y liga el hash esperado.

    Falla (False) si la firma no verifica o si el ``payload_hash`` no coincide
    con el que el cliente firmó para ese seq.
    """
    if receipt.payload_hash != expected_payload_hash:
        return False
    return verifier.verify(receipt.signing_body(), receipt.signature)


def attributable_omissions(
    receipted_seqs: Sequence[int],
    observed_seqs: Sequence[int],
) -> list[int]:
    """Omisiones que el operador NO puede atribuir a fallo de red.

    Un seq es una omisión atribuible si el cliente tiene un recibo VÁLIDO para
    él (el operador admitió recibirlo) pero el operador nunca exhibió inclusión
    (no aparece en ``observed_seqs``).

    Args:
        receipted_seqs: seqs para los que el cliente tiene un recibo verificado.
        observed_seqs:  seqs con inclusión confirmada en el log.

    Returns:
        Lista ascendente de seqs recibidos-pero-no-incluidos. Vacía si ninguno.

    Lo que esto NO cubre: seqs sin recibo (el cliente nunca confirmó entrega) —
    ahí el operador conserva la negación plausible y el cliente debe reenviar
    (idempotente por seq). Ver OSM-040 / paper §6.8.
    """
    observed = set(observed_seqs)
    return sorted(s for s in set(receipted_seqs) if s not in observed)
