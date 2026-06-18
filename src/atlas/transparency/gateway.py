"""TransparencyGateway — cableado in-path del protocolo de completitud (ADR-053).

Convierte el demo de completeness_demo.py en el sistema real:
cada llamada al modelo pasa automáticamente por el protocolo de
subject-enforced completeness sin que el usuario haga nada.

Flujo completo por request:
  1. subject_cosigner.sign_request(payload)  → CosignedRequest  [cliente/sujeto]
  2. operator_signer firma Receipt            → Receipt          [gateway, on-receive]
  3. InspectionRecord committed al log        → leaf_index_in   [antes del modelo]
  4. call_fn(payload)                         → result bytes    [llamada al modelo]
  5. OutputInspectionRecord committed al log  → leaf_index_out  [después del modelo]
  6. STH + inclusion proofs + Receipt         → APIResponse     [devuelto al caller]

La firma bidireccional (pasos 1 + 2) cierra §6.8 (timestamp backdating):
  - El sujeto firma la petición → el operador no puede omitir sin romper la secuencia.
  - El operador firma el Receipt → el operador no puede negar haber recibido la petición.
  Para falsificar se necesitan AMBAS claves. Análogo a Sello (arXiv 2606.04193)
  pero con el gateway como receptor en lugar de un servicio externo.

Capa 1 (clave local persistente) — transparente al usuario.
Capa 2 (TPM/Secure Enclave via OSM-025) enchufará aquí sin cambiar la interfaz.
"""
from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass

from typing import TYPE_CHECKING

from atlas.security.authorization import Signer
from atlas.transparency.client_cosign import (
    APIResponse,
    ClientCosigner,
    InspectionRecord,
    OutputInspectionRecord,
    Receipt,
)
from atlas.transparency.log import TransparencyLog

if TYPE_CHECKING:
    from atlas.security.shadow_model import ShadowRouter, ShadowModel
    from atlas.transparency.crypto_shred import SaltStore


@dataclass
class GatewayMetrics:
    """Métricas de latencia de una llamada verificada.

    pre_ms:   tiempo hasta que el modelo fue llamado (firma + commit input)
    model_ms: tiempo que tomó la llamada al modelo
    post_ms:  tiempo para commit output + generar STH + proofs
    total_ms: suma de los tres
    """
    pre_ms: float
    model_ms: float
    post_ms: float

    @property
    def total_ms(self) -> float:
        return self.pre_ms + self.model_ms + self.post_ms


class TransparencyGateway:
    """Envuelve cualquier llamada al modelo con subject-enforced completeness.

    Uso:
        gateway = TransparencyGateway(subject_cosigner, operator_signer, log)
        api_resp, metrics = gateway.call(payload, call_fn, task_id="t1")

    La instancia es thread-unsafe (ClientCosigner tiene estado de seq).
    Para uso concurrente, crear una instancia por sesión/usuario.
    """

    def __init__(
        self,
        subject_cosigner: ClientCosigner,
        operator_signer: Signer,
        log: TransparencyLog,
        *,
        session_id: str = "",
        shadow_router: "ShadowRouter | None" = None,
        shadow_model: "ShadowModel | None" = None,
        salt_store: "SaltStore | None" = None,
    ) -> None:
        self._cosigner = subject_cosigner
        self._op_signer = operator_signer
        self._log = log
        self._session_id = session_id
        self._shadow_router = shadow_router
        self._shadow_model = shadow_model
        self._salt_store = salt_store
        # last_tree_size para consistency proof (0 = log vacío antes de esta sesión)
        self._last_tree_size: int = log.tree_size

    # ------------------------------------------------------------------
    # Punto de entrada principal
    # ------------------------------------------------------------------

    def call(
        self,
        payload: bytes,
        call_fn: Callable[[bytes], bytes],
        *,
        task_id: str = "",
        model_id: str = "",
        decision: str = "allow",
        cause: str = "gateway.auto",
        subject_id: str = "",
        confidence: float = 0.0,
    ) -> tuple[APIResponse, GatewayMetrics]:
        """Ejecuta call_fn(payload) envuelto en el protocolo completo.

        Args:
            payload:   Bytes del prompt/request del usuario.
            call_fn:   Función que llama al modelo; recibe payload, devuelve bytes.
            task_id:   Identificador de tarea para el log (opcional).
            model_id:  Identificador del modelo; se hashea como model_version_hash.
            decision:  "allow" | "block" | "inspect" para el InspectionRecord.
            cause:     Causa del evento de inspección.

        Returns:
            (APIResponse, GatewayMetrics)
        """
        t0 = time.perf_counter()

        # Shadow routing (opt-in)
        effective_call_fn = call_fn
        effective_decision = decision
        effective_cause = cause

        if self._shadow_router is not None:
            from atlas.security.shadow_model import ShadowMode, ShadowModel
            routing = self._shadow_router.route(
                session_id=self._session_id or "gateway",
                confidence=confidence,
            )
            if routing.mode != ShadowMode.NORMAL:
                effective_decision = routing.mode.value
                effective_cause = routing.cause
                _sm = self._shadow_model if self._shadow_model is not None else ShadowModel()
                _mode = routing.mode

                def _shadow_call(p: bytes) -> bytes:
                    return _sm.respond(_mode, p.decode("utf-8", errors="replace"), sleep=lambda _: None)

                effective_call_fn = _shadow_call

        # ── Pre: firmar request + commit inspection ──────────────────────
        cosigned, sh = self._cosigner.sign_request_with_salt(payload)

        # Fallback: si el cosigner no tiene salt_store propio pero el gateway sí
        if not sh and self._salt_store is not None:
            entry = self._salt_store.register(cosigned.seq)
            sh = entry.compute_salted_hash(payload)

        now_ns = time.time_ns()

        # Receipt del operador (bidireccional — paso 2)
        receipt = self._issue_receipt(cosigned.seq, cosigned.payload_hash, now_ns)

        # model_version_hash: hash del model_id como proxy de versión
        mvh = hashlib.sha256(model_id.encode()).hexdigest() if model_id else ""

        record = InspectionRecord(
            seq=cosigned.seq,
            payload_hash=cosigned.payload_hash,
            cosig=cosigned.to_json(),
            decision=effective_decision,
            cause=effective_cause,
            timestamp_ns=now_ns,
            model_version_hash=mvh,
            salted_hash=sh,
            subject_id=subject_id,
        )
        leaf_index_in = self._log.append(record.to_bytes())

        t1 = time.perf_counter()

        # ── Llamada al modelo ─────────────────────────────────────────────
        result = effective_call_fn(payload)

        t2 = time.perf_counter()

        # ── Post: commit output + STH + proofs ───────────────────────────
        output_hash = hashlib.sha256(result).hexdigest()
        out_record = OutputInspectionRecord(
            seq=cosigned.seq,
            output_hash=output_hash,
            decision=effective_decision,
            cause=effective_cause,
            timestamp_ns=time.time_ns(),
        )
        leaf_index_out = self._log.append(out_record.to_bytes())

        sth = self._log.signed_tree_head()
        inclusion_in = self._log.prove_inclusion(leaf_index_in)
        inclusion_out = self._log.prove_inclusion(leaf_index_out)
        consistency = self._log.prove_consistency(self._last_tree_size)

        t3 = time.perf_counter()

        api_resp = APIResponse(
            result=result,
            seq_ack=cosigned.seq,
            leaf_bytes=record.to_bytes(),
            leaf_index=leaf_index_in,
            inclusion_proof=inclusion_in,
            sth=sth,
            consistency_proof=consistency,
            consistency_from=self._last_tree_size,
            output_leaf_bytes=out_record.to_bytes(),
            output_leaf_index=leaf_index_out,
            output_inclusion_proof=inclusion_out,
        )

        self._last_tree_size = sth.tree_size

        metrics = GatewayMetrics(
            pre_ms=(t1 - t0) * 1000,
            model_ms=(t2 - t1) * 1000,
            post_ms=(t3 - t2) * 1000,
        )
        return api_resp, metrics

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _issue_receipt(self, seq: int, payload_hash: str, now_ns: int) -> Receipt:
        """El operador firma un Receipt acreditando haber recibido la petición.

        Esto hace la omisión ATRIBUIBLE: si el cliente tiene un Receipt válido
        para seq=n pero el log no tiene inclusión para n, el operador no puede
        alegar fallo de red (OSM-040 / §6.8).
        """
        draft = Receipt(
            seq=seq,
            payload_hash=payload_hash,
            received_at_ns=now_ns,
            signature="",
        )
        sig = self._op_signer.sign(draft.signing_body())
        return Receipt(
            seq=seq,
            payload_hash=payload_hash,
            received_at_ns=now_ns,
            signature=sig,
        )
