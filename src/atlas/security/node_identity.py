"""NodeIdentity — identidad local de nodo (keypair Ed25519 + heartbeat firmado).

STANDALONE — SIN CONSUMIDOR TODAVÍA (guarda anti wire-before-claim)
--------------------------------------------------------------------
Este módulo implementa docs/backlog.yaml:t6-node-identity-module, el "First
Practical Step" que docs/design/fleet_security_plan.md propone para una futura
arquitectura multi-nodo (explícitamente NO Kubernetes/consenso Byzantine/
override remoto en esta fase). HOY no existe un segundo nodo real: Hermes VPS
está de baja desde mayo (ver hermes-vps-deployment-playbook-2026-05.md) y no
hay transporte remoto ni control-plane que consuma esta identidad. Por tanto
este módulo es PURO y CERO integrado:

  - no abre sockets, no hace I/O de red, no depende de ningún otro nodo real;
  - no lo importa ningún control-plane ni transporte existente en el repo;
  - la persistencia en disco (si se necesita) es responsabilidad del llamador,
    igual que atlas.transparency.key_store separa "cargar/generar claves" de
    "cómo se usan" — aquí no se replica ese layer de persistencia a propósito,
    para no fingir un ciclo de vida de nodo que todavía no existe.

Cuando exista un segundo nodo real que necesite consumir esta identidad sobre
un transporte (ver t6-hermes-redeploy-execute), ese trabajo se hace en un
módulo de transporte/control-plane separado que IMPORTE NodeIdentity — no
se debe expandir este archivo con supuestos de red no verificados.

Reutiliza el primitivo de firma Ed25519 ya existente en
``atlas.security.authorization`` (Ed25519Signer/Ed25519Verifier, que envuelven
la librería ``cryptography`` ya dependencia del repo) en vez de introducir una
dependencia criptográfica nueva.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field

from atlas.security.authorization import Ed25519Signer, Ed25519Verifier


# ---------------------------------------------------------------------------
# Documento de identidad pública
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NodeIdentityDocument:
    """Documento público exportable: identifica un nodo por su clave pública.

    No contiene material privado. Es lo único que un verificador remoto
    necesitaría para comprobar heartbeats de este nodo — hoy nadie lo consume
    (ver docstring del módulo), pero el documento ya es autocontenido para
    cuando exista un consumidor real.
    """

    node_id: str
    public_key_hex: str
    algo: str
    created_at_ns: int
    metadata: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialización canónica (claves ordenadas, sin espacios)."""
        doc = {
            "algo": self.algo,
            "created_at_ns": self.created_at_ns,
            "metadata": self.metadata,
            "node_id": self.node_id,
            "public_key_hex": self.public_key_hex,
        }
        return json.dumps(doc, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, data: str) -> "NodeIdentityDocument":
        doc = json.loads(data)
        return cls(
            node_id=doc["node_id"],
            public_key_hex=doc["public_key_hex"],
            algo=doc["algo"],
            created_at_ns=doc["created_at_ns"],
            metadata=dict(doc.get("metadata", {})),
        )


# ---------------------------------------------------------------------------
# Heartbeat / recibo firmado
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SignedHeartbeat:
    """Heartbeat/recibo de un nodo, firmado con su clave privada.

    El cuerpo firmado (``signing_body``) liga ``node_id`` + ``seq`` +
    ``timestamp_ns`` + ``payload_hash`` — alterar cualquiera de esos campos
    invalida la firma, igual que ``CosignedRequest``/``Receipt`` en
    ``atlas.transparency.client_cosign``.
    """

    node_id: str
    seq: int
    timestamp_ns: int
    payload_hash: str  # SHA-256 hex del payload original
    signature: str

    def signing_body(self) -> bytes:
        """Bytes canónicos firmados: JSON compacto con claves ordenadas."""
        return json.dumps(
            {
                "node_id": self.node_id,
                "payload_hash": self.payload_hash,
                "seq": self.seq,
                "timestamp_ns": self.timestamp_ns,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def to_json(self) -> str:
        return json.dumps(
            {
                "node_id": self.node_id,
                "payload_hash": self.payload_hash,
                "seq": self.seq,
                "signature": self.signature,
                "timestamp_ns": self.timestamp_ns,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, data: str) -> "SignedHeartbeat":
        doc = json.loads(data)
        return cls(
            node_id=doc["node_id"],
            seq=doc["seq"],
            timestamp_ns=doc["timestamp_ns"],
            payload_hash=doc["payload_hash"],
            signature=doc["signature"],
        )


def verify_heartbeat(
    heartbeat: SignedHeartbeat, payload: bytes, public_key_hex: str
) -> bool:
    """True si *heartbeat* está firmado por la clave con *public_key_hex* y
    liga exactamente a *payload*.

    Falla (False, nunca lanza) si:
    - el ``payload_hash`` no coincide con el hash real de *payload*;
    - la firma no verifica contra la clave pública dada;
    - la clave pública o la firma vienen malformadas (hex inválido).

    Solo necesita el hex de clave pública (p.ej. de un
    ``NodeIdentityDocument``) — no requiere el objeto ``NodeIdentity`` ni
    ninguna clave privada, para que un verificador remoto pueda comprobar
    heartbeats sin tocar material sensible.
    """
    expected_hash = hashlib.sha256(payload).hexdigest()
    if heartbeat.payload_hash != expected_hash:
        return False
    try:
        public_key_bytes = bytes.fromhex(public_key_hex)
    except ValueError:
        return False
    verifier = Ed25519Verifier(public_key_bytes)
    return verifier.verify(heartbeat.signing_body(), heartbeat.signature)


# ---------------------------------------------------------------------------
# NodeIdentity — keypair + firma local
# ---------------------------------------------------------------------------

class NodeIdentity:
    """Identidad local de un nodo: keypair Ed25519 + firma de heartbeats.

    Uso: ``NodeIdentity.generate()`` crea un keypair en memoria (no persiste a
    disco — eso es decisión del llamador, ver docstring del módulo). El nodo
    exporta su ``identity_document()`` (solo clave pública + metadata) y firma
    payloads de heartbeat/recibo con ``sign_heartbeat()``.
    """

    def __init__(
        self,
        node_id: str,
        signer: Ed25519Signer,
        public_key_bytes: bytes,
        *,
        metadata: dict[str, str] | None = None,
        created_at_ns: int | None = None,
    ) -> None:
        self.node_id = node_id
        self._signer = signer
        self._public_key_bytes = public_key_bytes
        self.metadata = dict(metadata or {})
        self.created_at_ns = (
            created_at_ns if created_at_ns is not None else time.time_ns()
        )

    @property
    def public_key_hex(self) -> str:
        return self._public_key_bytes.hex()

    @classmethod
    def generate(
        cls,
        *,
        node_id: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> "NodeIdentity":
        """Genera un keypair Ed25519 nuevo para un nodo.

        Si *node_id* no se da, se asigna un UUID4 — suficiente para
        distinguir nodos en pruebas locales; un esquema de node_id derivado
        (p.ej. hash de la clave pública) queda para cuando exista un
        consumidor real que dicte el requisito.
        """
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PrivateKey,
            )
        except ImportError as exc:
            raise RuntimeError("cryptography no instalado") from exc

        key = Ed25519PrivateKey.generate()
        priv_bytes = key.private_bytes_raw()
        pub_bytes = key.public_key().public_bytes_raw()
        signer = Ed25519Signer(priv_bytes)
        return cls(
            node_id=node_id or str(uuid.uuid4()),
            signer=signer,
            public_key_bytes=pub_bytes,
            metadata=metadata,
        )

    def identity_document(self) -> NodeIdentityDocument:
        """Documento público exportable — sin material privado."""
        return NodeIdentityDocument(
            node_id=self.node_id,
            public_key_hex=self.public_key_hex,
            algo=self._signer.algo,
            created_at_ns=self.created_at_ns,
            metadata=dict(self.metadata),
        )

    def sign_heartbeat(self, payload: bytes, *, seq: int) -> SignedHeartbeat:
        """Firma *payload* (heartbeat/recibo) y devuelve un ``SignedHeartbeat``.

        *seq* es responsabilidad del llamador (p.ej. contador monótono como
        ``ClientCosigner``) — este módulo no impone ordering ni lo persiste,
        para no fingir un protocolo multi-nodo que aún no existe.
        """
        payload_hash = hashlib.sha256(payload).hexdigest()
        timestamp_ns = time.time_ns()
        body = json.dumps(
            {
                "node_id": self.node_id,
                "payload_hash": payload_hash,
                "seq": seq,
                "timestamp_ns": timestamp_ns,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        signature = self._signer.sign(body)
        return SignedHeartbeat(
            node_id=self.node_id,
            seq=seq,
            timestamp_ns=timestamp_ns,
            payload_hash=payload_hash,
            signature=signature,
        )
