"""A3.3 — Activador reversible de plugins staged (ADR-073, condición 4).

"Activador reversible que consuma sólo ese recibo, aplique contribuciones
declarativas y permita revocar/borrar staging sin tocar el árbol principal."

Consume EXCLUSIVAMENTE un `PluginReceipt.status == "issued"` — nunca vuelve a
mirar el `MaterializationResult` original ni reinterpreta el veredicto de
admisión. Antes de aplicar nada re-verifica, de forma independiente
(`compute_tree_sha256`), que el árbol staged sigue siendo EXACTAMENTE el que
el recibo describe (defensa TOCTOU: staging no está protegido por permisos de
filesystem, solo por convención + re-verificación en cada punto de confianza),
y re-lee/re-hashea el manifest contra `receipt.manifest_sha256` antes de
confiar en sus contribuciones.

Activar es su propia decisión, separada de emitir el recibo (un `admit` de A2
es evidencia, nunca permiso de instalación — dicho explícito en la CLI de
A3.1): consulta el MISMO `Decider` protocol que el resto del sistema, con
`requires_approval=True` — bajo `HumanDecider` toda activación se suspende
(`pending_approval`, resuelta por `approve_activation()`, DELIBERADAMENTE
fuera del seam del decisor, mismo patrón que `PluginReceiptBroker.approve()`
y `atlas update approve`); bajo `AutonomousDecider`, por invariantes.

`revoke()` nunca consulta al decisor (retirar capacidad no necesita permiso,
igual que `ColdUpdateManager.rollback_applied`/`reject()`) y por defecto
también borra el staging del recibo — tal como pide la condición 4 — sin
tocar nunca nada fuera de `active_root`/`staged_root`.
"""

from __future__ import annotations

import hashlib
import json
import shutil
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
from atlas.mcp.plugin_admission import PLUGIN_MANIFEST_FILENAME
from atlas.mcp.plugin_manifest import PluginManifest
from atlas.mcp.plugin_materializer import compute_tree_sha256
from atlas.mcp.plugin_receipt_broker import PluginReceipt, PluginReceiptBroker


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AppliedContribution(_StrictModel):
    contribution_id: str
    kind: Literal["skill", "prompt", "rule", "command"]
    path: str
    active_path: str


# Alias a nivel de módulo: `PluginActivator` define un método `list()`, que
# sombrea el builtin `list` para la resolución de anotaciones DENTRO de la
# clase (independiente del orden de definición — `from __future__ import
# annotations` las deja como texto, resuelto contra el namespace completo de
# la clase). `_AppliedContributions` evita el choque sin renombrar la API
# pública `.list()` (mismo nombre que `PluginReceiptBroker.list()`).
_AppliedContributions = list[AppliedContribution]


class ActivationRecord(_StrictModel):
    schema_version: Literal["1.0"]
    activation_id: str
    receipt_id: str
    plugin_id: str | None
    staged_root: str
    active_root: str | None
    status: Literal["pending_approval", "activated", "denied", "failed", "revoked"]
    verdict: Literal["Allow", "Deny", "RequiresHuman"] | None
    decider_name: str
    applied: list[AppliedContribution]
    reason_codes: list[str]
    created_at: str
    decided_at: str | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PluginActivator:
    def __init__(
        self,
        *,
        broker: PluginReceiptBroker,
        merkle: MerkleLogger,
        active_root: Path,
        store_dir: Path,
        decider: Decider | None = None,
    ) -> None:
        self._broker = broker
        self._merkle = merkle
        self._active_root = active_root
        self._decider: Decider = decider or HumanDecider()
        self._store_dir = store_dir
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._records_file = self._store_dir / "activations.json"
        self._records: dict[str, ActivationRecord] = {}
        self._load()

    def activate(self, receipt_id: str) -> ActivationRecord:
        receipt = self._broker.get(receipt_id)
        if receipt is None:
            raise KeyError(f"recibo no encontrado: {receipt_id}")
        if receipt.status != "issued":
            raise ValueError(
                f"recibo {receipt_id} no está emitido (status={receipt.status}); "
                "nada que activar"
            )

        activation_id = uuid.uuid4().hex[:12]
        staged_root = Path(receipt.staged_root)
        active_root = self._active_root / (receipt.plugin_id or activation_id)
        if active_root.exists():
            return self._store(
                _failed(
                    activation_id, receipt, "plugin_already_active", staged_root,
                    decider_name=type(self._decider).__name__,
                )
            )

        manifest = self._reverify(receipt)
        if isinstance(manifest, str):
            return self._store(
                _failed(
                    activation_id, receipt, manifest, staged_root,
                    decider_name=type(self._decider).__name__,
                )
            )

        action = DecisionAction(
            kind="plugin_activation",
            requires_approval=True,
            sensitivity="normal",
            mutating=True,
            reversible=True,
            descriptor=receipt.plugin_id or "",
            reason=f"activar plugin staged {receipt.plugin_id} desde recibo {receipt_id}",
        )
        verdict = self._decider.decide(
            action,
            f"activate plugin {receipt.plugin_id}",
            context={"receipt_id": receipt_id, "staged_root": str(staged_root)},
        )
        return self._resolve(
            activation_id, receipt, verdict, manifest, active_root,
            decider_name=type(self._decider).__name__,
        )

    def approve_activation(self, activation_id: str) -> ActivationRecord:
        """Resolución HUMANA explícita de una activación `pending_approval`.

        Re-verifica TODO de nuevo (recibo sigue `issued`, árbol sigue igual):
        el tiempo entre `activate()` y esta llamada es otra ventana TOCTOU."""
        record = self._require(activation_id)
        if record.status != "pending_approval":
            raise RuntimeError(
                f"activación {activation_id} no está pendiente (status={record.status})"
            )
        receipt = self._broker.get(record.receipt_id)
        if receipt is None or receipt.status != "issued":
            return self._store(
                record.model_copy(
                    update={
                        "status": "failed",
                        "reason_codes": ["receipt_no_longer_issued"],
                        "decided_at": _now(),
                    }
                )
            )
        staged_root = Path(record.staged_root)
        active_root = self._active_root / (receipt.plugin_id or activation_id)
        if active_root.exists():
            return self._store(
                record.model_copy(
                    update={
                        "status": "failed",
                        "reason_codes": ["plugin_already_active"],
                        "decided_at": _now(),
                    }
                )
            )
        manifest = self._reverify(receipt)
        if isinstance(manifest, str):
            return self._store(
                record.model_copy(
                    update={
                        "status": "failed",
                        "reason_codes": [manifest],
                        "decided_at": _now(),
                    }
                )
            )
        applied, apply_error = self._apply(staged_root, active_root, manifest)
        if apply_error is not None:
            return self._store(
                record.model_copy(
                    update={
                        "status": "failed",
                        "reason_codes": [apply_error],
                        "decided_at": _now(),
                    }
                )
            )
        approved = record.model_copy(
            update={
                "status": "activated",
                "verdict": "Allow",
                "active_root": str(active_root),
                "applied": applied,
                "decided_at": _now(),
            }
        )
        self._store(approved)
        self._log("plugin.activation_approved", approved)
        return approved

    def revoke(self, activation_id: str, *, keep_staging: bool = False) -> ActivationRecord:
        record = self._require(activation_id)
        if record.status != "activated":
            raise RuntimeError(
                f"activación {activation_id} no está activa (status={record.status})"
            )
        if record.active_root is not None:
            shutil.rmtree(record.active_root, ignore_errors=True)
        if not keep_staging:
            shutil.rmtree(record.staged_root, ignore_errors=True)
            sidecar = Path(record.staged_root).with_name(
                Path(record.staged_root).name + ".provenance.json"
            )
            sidecar.unlink(missing_ok=True)
        revoked = record.model_copy(
            update={"status": "revoked", "active_root": None, "applied": [], "decided_at": _now()}
        )
        self._store(revoked)
        self._log("plugin.revoked", revoked)
        return revoked

    def get(self, activation_id: str) -> ActivationRecord | None:
        return self._records.get(activation_id)

    def list(self) -> list[ActivationRecord]:
        return sorted(self._records.values(), key=lambda r: r.created_at, reverse=True)

    # -- internals ---------------------------------------------------------

    def _reverify(self, receipt: PluginReceipt) -> PluginManifest | str:
        """Re-hashea árbol y manifest contra el recibo; devuelve el manifest
        parseado o un reason_code si algo cambió desde que se emitió."""
        staged_root = Path(receipt.staged_root)
        if not staged_root.is_dir():
            return "staged_root_missing"
        try:
            tree_sha256 = compute_tree_sha256(staged_root)
        except ValueError:
            return "staged_tree_mutated_since_receipt"
        if tree_sha256 != receipt.provenance.tree_sha256:
            return "staged_tree_mutated_since_receipt"

        manifest_path = staged_root / PLUGIN_MANIFEST_FILENAME
        if manifest_path.is_symlink() or not manifest_path.is_file():
            return "manifest_missing"
        raw = manifest_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != receipt.manifest_sha256:
            return "manifest_changed_since_receipt"
        try:
            manifest = PluginManifest.model_validate_json(raw)
        except Exception:  # noqa: BLE001
            return "manifest_invalid"
        if manifest.plugin_id != receipt.plugin_id:
            return "manifest_plugin_id_mismatch"
        return manifest

    def _resolve(
        self,
        activation_id: str,
        receipt: PluginReceipt,
        verdict: Verdict,
        manifest: PluginManifest,
        active_root: Path,
        *,
        decider_name: str,
    ) -> ActivationRecord:
        if isinstance(verdict, Deny):
            record = _record(
                activation_id, receipt, status="denied", verdict="Deny",
                active_root=None, applied=[], reason_codes=[], decided_at=_now(),
                decider_name=decider_name,
            )
            self._store(record)
            self._log("plugin.activation_denied", record)
            return record
        if isinstance(verdict, RequiresHuman):
            record = _record(
                activation_id, receipt, status="pending_approval", verdict="RequiresHuman",
                active_root=None, applied=[], reason_codes=[], decided_at=None,
                decider_name=decider_name,
            )
            self._store(record)
            self._log("plugin.activation_pending", record)
            return record
        if not isinstance(verdict, Allow):  # pragma: no cover
            raise TypeError(f"veredicto desconocido: {type(verdict).__name__}")

        applied, apply_error = self._apply(Path(receipt.staged_root), active_root, manifest)
        if apply_error is not None:
            return self._store(
                _failed(
                    activation_id, receipt, apply_error, Path(receipt.staged_root),
                    decider_name=decider_name,
                )
            )
        record = _record(
            activation_id, receipt, status="activated", verdict="Allow",
            active_root=str(active_root), applied=applied, reason_codes=[], decided_at=_now(),
            decider_name=decider_name,
        )
        self._store(record)
        self._log("plugin.activated", record)
        return record

    def _apply(
        self, staged_root: Path, active_root: Path, manifest: PluginManifest
    ) -> tuple[_AppliedContributions, str | None]:
        try:
            active_root.mkdir(parents=True, exist_ok=False)
        except OSError:
            return [], "plugin_already_active"
        applied: _AppliedContributions = []
        try:
            for contribution in manifest.contributions:
                kind_dir = active_root / contribution.kind
                kind_dir.mkdir(parents=True, exist_ok=True)
                target = kind_dir / f"{contribution.contribution_id}.md"
                source_abs = (staged_root / contribution.path).resolve()
                target.symlink_to(source_abs)
                applied.append(
                    AppliedContribution(
                        contribution_id=contribution.contribution_id,
                        kind=contribution.kind,
                        path=contribution.path,
                        active_path=str(target),
                    )
                )
        except OSError:
            shutil.rmtree(active_root, ignore_errors=True)
            return [], "apply_failed"
        return applied, None

    def _require(self, activation_id: str) -> ActivationRecord:
        record = self._records.get(activation_id)
        if record is None:
            raise KeyError(f"activación no encontrada: {activation_id}")
        return record

    def _store(self, record: ActivationRecord) -> ActivationRecord:
        self._records[record.activation_id] = record
        self._save()
        return record

    def _log(self, action: str, record: ActivationRecord) -> None:
        self._merkle.log(
            action=action,
            agent="plugin_activator",
            result="success" if record.status == "activated" else (
                "blocked" if record.status in ("denied", "failed", "revoked") else "pending"
            ),
            risk_level="critical",
            payload={
                "activation_id": record.activation_id,
                "receipt_id": record.receipt_id,
                "plugin_id": record.plugin_id,
                "status": record.status,
                "verdict": record.verdict,
                "reason_codes": record.reason_codes,
            },
        )

    def _load(self) -> None:
        if not self._records_file.is_file():
            return
        try:
            raw = json.loads(self._records_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for item in raw.get("activations", []):
            try:
                record = ActivationRecord.model_validate(item)
            except Exception:  # noqa: BLE001 — fila corrupta, se ignora
                continue
            self._records[record.activation_id] = record

    def _save(self) -> None:
        payload = {
            "activations": [r.model_dump(mode="json") for r in self._records.values()]
        }
        self._records_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _record(
    activation_id: str,
    receipt: PluginReceipt,
    *,
    status: Literal["pending_approval", "activated", "denied", "failed"],
    verdict: Literal["Allow", "Deny", "RequiresHuman"] | None,
    active_root: str | None,
    applied: list[AppliedContribution],
    reason_codes: list[str],
    decided_at: str | None,
    decider_name: str,
) -> ActivationRecord:
    return ActivationRecord(
        schema_version="1.0",
        activation_id=activation_id,
        receipt_id=receipt.receipt_id,
        plugin_id=receipt.plugin_id,
        staged_root=receipt.staged_root,
        active_root=active_root,
        status=status,
        verdict=verdict,
        decider_name=decider_name,
        applied=applied,
        reason_codes=reason_codes,
        created_at=_now(),
        decided_at=decided_at,
    )


def _failed(
    activation_id: str, receipt: PluginReceipt, reason_code: str, staged_root: Path,
    *, decider_name: str = "",
) -> ActivationRecord:
    return ActivationRecord(
        schema_version="1.0",
        activation_id=activation_id,
        receipt_id=receipt.receipt_id,
        plugin_id=receipt.plugin_id,
        staged_root=str(staged_root),
        active_root=None,
        status="failed",
        verdict=None,
        decider_name=decider_name,
        applied=[],
        reason_codes=[reason_code],
        created_at=_now(),
        decided_at=_now(),
    )

