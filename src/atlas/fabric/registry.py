"""ConnectorRegistry — perfiles aprobados + detección de rug-pull.

Un descriptor de conector/tool que cambia tras su aprobación (rug pull:
descripción inocua al aprobar, maliciosa después) se detecta por hash
canónico y degrada la conexión hasta re-aprobación humana. Determinista,
sin juicio LLM."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from atlas.events.emit import emit_event
from atlas.events.schemas import Risk
from atlas.events.store import OsEventStore


def descriptor_hash(descriptor: dict[str, Any]) -> str:
    canonical = json.dumps(descriptor, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _default_approvals_path() -> Path:
    home = Path(os.environ.get("ATLAS_HOME", "~/atlas")).expanduser()
    return home / "connections" / "approved_descriptors.json"


class ConnectorRegistry:
    """Registra descriptores aprobados y verifica que no muten."""

    def __init__(
        self,
        approvals_path: Path | None = None,
        store: OsEventStore | None = None,
    ) -> None:
        self._path = approvals_path or _default_approvals_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._store = store

    def _load(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        data: dict[str, str] = json.loads(self._path.read_text(encoding="utf-8"))
        return data

    def _save(self, approved: dict[str, str]) -> None:
        self._path.write_text(
            json.dumps(approved, indent=2, sort_keys=True), encoding="utf-8"
        )

    def approve_descriptor(
        self, connector_id: str, descriptor: dict[str, Any]
    ) -> str:
        """Fija el hash del descriptor tal y como lo aprobó el humano."""
        digest = descriptor_hash(descriptor)
        approved = self._load()
        approved[connector_id] = digest
        self._save(approved)
        emit_event(
            self._store,
            "connector.descriptor.approved",
            f"Descriptor de {connector_id} aprobado ({digest[:12]}…)",
            actor="governance",
            source="atlas.fabric.registry",
            payload={"connector_id": connector_id, "sha256": digest},
        )
        return digest

    def verify_descriptor(
        self, connector_id: str, current_descriptor: dict[str, Any]
    ) -> dict[str, Any]:
        """Compara el descriptor actual con el aprobado.

        - sin aprobación previa → unapproved (no se usa hasta aprobar);
        - hash igual → ok;
        - hash distinto → rug_pull_suspected: la conexión queda degradada y
          exige re-aprobación humana explícita.
        """
        approved = self._load()
        expected = approved.get(connector_id)
        current = descriptor_hash(current_descriptor)
        if expected is None:
            return {"status": "unapproved", "connector_id": connector_id,
                    "sha256": current}
        if current == expected:
            return {"status": "ok", "connector_id": connector_id,
                    "sha256": current}
        emit_event(
            self._store,
            "connector.descriptor.mismatch",
            f"RUG PULL sospechado en {connector_id}: el descriptor cambió tras "
            "la aprobación",
            actor="governance",
            source="atlas.fabric.registry",
            risk=Risk.CRITICAL,
            payload={"connector_id": connector_id, "approved_sha256": expected,
                     "current_sha256": current,
                     "action_required": "re-aprobación humana"},
        )
        return {"status": "rug_pull_suspected", "connector_id": connector_id,
                "approved_sha256": expected, "current_sha256": current}
