"""A3.2 — Recibo Merkle + broker de aprobación humana para plugins staged.

ADR-073 (consecuencias A3, condición 3 de docs/design/plugin_manifest_v1.md):
"Recibo Merkle que ligue record_id, manifest, procedencia y decisión; broker
de aprobación humana para review o sensibilidad alta."

No reinventa HITL: reusa el `Decider` protocol (ADR-040,
`atlas.core.decider`) que ya gobierna el resto del orquestador. Un veredicto
`review` de `PluginAdmissionGate` (A2) se traduce a `sensitivity="high"` — el
MISMO lever que `HumanDecider` suspende siempre (regla constitucional #4,
`AGENTS.md`) y que `AutonomousDecider` deniega siempre (invariante 2). Así el
broker se comporta correctamente bajo cualquier decisor configurado sin
lógica de aprobación ad-hoc: un `review` nunca se promueve solo porque nadie
miró.

Un recibo `issued` es evidencia de que la decisión fue tomada (por un humano
o por invariantes deterministas) y de qué árbol exacto (`staged_root` +
`provenance.tree_sha256`) cubre — nunca una autorización de activación por sí
mismo: A3.3 deberá volver a verificar el árbol contra estos campos antes de
aplicar cualquier contribución.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from atlas.core.decider.decider import (
    Allow,
    Decider,
    DecisionAction,
    Deny,
    RequiresHuman,
    Verdict,
)
from atlas.core.decider.human_decider import HumanDecider
from atlas.logging.merkle_logger import MerkleLogger
from atlas.mcp.plugin_materializer import MaterializationResult, MaterializedProvenance


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PluginReceipt(_StrictModel):
    schema_version: Literal["1.0"]
    receipt_id: str
    record_id: str | None
    plugin_id: str | None
    manifest_sha256: str | None
    staged_root: str
    provenance: MaterializedProvenance
    admission_status: Literal["admit", "review"]
    status: Literal["pending_approval", "issued", "declined", "denied"]
    verdict: Literal["Allow", "Deny", "RequiresHuman"]
    decider_name: str
    decline_reason: str | None = None
    created_at: str
    decided_at: str | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PluginReceiptBroker:
    """Emite, persiste y resuelve recibos de plugins staged."""

    def __init__(
        self,
        *,
        merkle: MerkleLogger,
        store_dir: Path,
        decider: Decider | None = None,
    ) -> None:
        self._merkle = merkle
        self._decider: Decider = decider or HumanDecider()
        self._store_dir = store_dir
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._receipts_file = self._store_dir / "receipts.json"
        self._receipts: dict[str, PluginReceipt] = {}
        self._load()

    def request(self, result: MaterializationResult) -> PluginReceipt:
        """Consulta al decisor y emite (o encola) un recibo ligado al árbol staged.

        Solo acepta materializaciones con admisión `admit` o `review`; un
        `block` (o una materialización `failed`) no tiene nada que acreditar
        y se rechaza explícito — un recibo para un plugin ya rechazado sería
        evidencia falsa de que existió una decisión que tomar."""
        admission = result.admission
        if result.status != "materialized" or admission is None:
            raise ValueError(
                "no se puede emitir recibo de una materialización fallida: "
                f"{', '.join(result.reason_codes)}"
            )
        if admission.status == "block":
            raise ValueError(
                "no se puede emitir recibo de una admisión bloqueada "
                f"({', '.join(admission.reason_codes)}); nada que aprobar"
            )

        sensitivity = "high" if admission.status == "review" else "normal"
        action = DecisionAction(
            kind="plugin_receipt",
            requires_approval=(admission.status == "review"),
            sensitivity=sensitivity,
            # Emitir un recibo no otorga ninguna capacidad por sí mismo (solo
            # ata evidencia a una decisión); no es una mutación que necesite
            # undo. La activación real (A3.3) consultará el decisor de nuevo,
            # con mutating=True y su propio undo.
            mutating=False,
            reversible=True,
            descriptor=admission.plugin_id or "",
            reason=f"recibo de plugin staged ({admission.status})",
        )
        sanctioned_intent = f"emitir recibo para plugin staged {admission.plugin_id}"
        verdict = self._decider.decide(
            action,
            sanctioned_intent,
            context={
                "staged_root": result.staged_root,
                "manifest_sha256": admission.manifest_sha256,
                "admission_status": admission.status,
            },
        )

        receipt_id = uuid.uuid4().hex[:12]
        status, decided_at = _status_from_verdict(verdict)
        receipt = PluginReceipt(
            schema_version="1.0",
            receipt_id=receipt_id,
            record_id=admission.scan.record_id if admission.scan else None,
            plugin_id=admission.plugin_id,
            manifest_sha256=admission.manifest_sha256,
            staged_root=result.staged_root or "",
            provenance=result.provenance,  # type: ignore[arg-type]
            admission_status=admission.status,
            status=status,
            verdict=type(verdict).__name__,  # type: ignore[arg-type]
            decider_name=type(self._decider).__name__,
            created_at=_now(),
            decided_at=decided_at,
        )
        self._receipts[receipt_id] = receipt
        self._save()
        self._log(f"plugin.receipt_{status}", receipt)
        return receipt

    def approve(self, receipt_id: str) -> PluginReceipt:
        """Resolución HUMANA explícita de un recibo `pending_approval`.

        Deliberadamente NO pasa por el `Decider`: `RequiresHuman` ya dijo que
        la decisión automática terminó ahí. Esta es la acción de fuera del
        seam (mismo patrón que `atlas update approve` para ColdUpdate)."""
        receipt = self._require(receipt_id)
        if receipt.status != "pending_approval":
            raise RuntimeError(
                f"recibo {receipt_id} no está pendiente (status={receipt.status})"
            )
        approved = receipt.model_copy(
            update={"status": "issued", "verdict": "Allow", "decided_at": _now()}
        )
        self._receipts[receipt_id] = approved
        self._save()
        self._log("plugin.receipt_approved", approved)
        return approved

    def decline(self, receipt_id: str, reason: str = "") -> PluginReceipt:
        receipt = self._require(receipt_id)
        if receipt.status != "pending_approval":
            raise RuntimeError(
                f"recibo {receipt_id} no está pendiente (status={receipt.status})"
            )
        declined = receipt.model_copy(
            update={
                "status": "declined",
                "verdict": "Deny",
                "decided_at": _now(),
                "decline_reason": reason[:500] or None,
            }
        )
        self._receipts[receipt_id] = declined
        self._save()
        self._log("plugin.receipt_declined", declined)
        return declined

    def get(self, receipt_id: str) -> PluginReceipt | None:
        return self._receipts.get(receipt_id)

    def list(self) -> list[PluginReceipt]:
        return sorted(self._receipts.values(), key=lambda r: r.created_at, reverse=True)

    def _require(self, receipt_id: str) -> PluginReceipt:
        receipt = self._receipts.get(receipt_id)
        if receipt is None:
            raise KeyError(f"recibo no encontrado: {receipt_id}")
        return receipt

    def _log(self, action: str, receipt: PluginReceipt) -> None:
        self._merkle.log(
            action=action,
            agent="plugin_receipt_broker",
            result="success" if receipt.status in ("issued",) else (
                "blocked" if receipt.status in ("declined", "denied") else "pending"
            ),
            risk_level="high" if receipt.admission_status == "review" else "moderate",
            payload={
                "receipt_id": receipt.receipt_id,
                "record_id": receipt.record_id,
                "plugin_id": receipt.plugin_id,
                "manifest_sha256": receipt.manifest_sha256,
                "tree_sha256": receipt.provenance.tree_sha256,
                "status": receipt.status,
                "verdict": receipt.verdict,
                "decider_name": receipt.decider_name,
            },
        )

    def _load(self) -> None:
        if not self._receipts_file.is_file():
            return
        try:
            raw = json.loads(self._receipts_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for item in raw.get("receipts", []):
            try:
                receipt = PluginReceipt.model_validate(item)
            except Exception:  # noqa: BLE001 — fila corrupta, se ignora, no bloquea el resto
                continue
            self._receipts[receipt.receipt_id] = receipt

    def _save(self) -> None:
        payload = {"receipts": [r.model_dump(mode="json") for r in self._receipts.values()]}
        self._receipts_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _status_from_verdict(
    verdict: Verdict,
) -> tuple[Literal["issued", "pending_approval", "denied"], str | None]:
    if isinstance(verdict, Allow):
        return "issued", _now()
    if isinstance(verdict, RequiresHuman):
        return "pending_approval", None
    if isinstance(verdict, Deny):
        return "denied", _now()
    raise TypeError(f"veredicto desconocido: {type(verdict).__name__}")  # pragma: no cover
