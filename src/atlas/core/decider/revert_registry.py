"""Registro de undo por ``action_hash`` (ADR-040 slice 6).

La autonomía solo procede sobre lo reversible (invariante 4 del
``AutonomousDecider``). Cuando una acción reversible se ejecuta, su primitiva de
undo real (snapshot OMEGA / server MCP) se persiste aquí, atada al
``action_hash`` exacto que el decisor autorizó. ``revert(action_hash)`` en el
orquestador resuelve el handle y dispara la primitiva correspondiente.

Persistencia en JSON plano (stdlib): el conjunto de handles vivos es pequeño y
el formato debe sobrevivir a un reinicio del proceso.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SNAPSHOT = "snapshot"
MCP_SERVER = "mcp_server"

_KINDS = frozenset({SNAPSHOT, MCP_SERVER})


@dataclass(frozen=True)
class UndoHandle:
    """Primitiva de undo concreta. ``ref`` es el snapshot_id o el nombre del server."""

    kind: str
    ref: str


class RevertRegistry:
    """Mapa persistente ``action_hash -> UndoHandle``."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._entries: dict[str, UndoHandle] = self._load()

    def register(self, action_hash: str, kind: str, ref: str) -> None:
        """Ata un handle de undo a un ``action_hash`` autorizado."""
        if kind not in _KINDS:
            raise ValueError(f"kind de undo desconocido: {kind!r}")
        self._entries[action_hash] = UndoHandle(kind=kind, ref=ref)
        self._flush()

    def get(self, action_hash: str) -> UndoHandle | None:
        return self._entries.get(action_hash)

    def forget(self, action_hash: str) -> None:
        """Descarta el handle tras un revert consumado (idempotente)."""
        if self._entries.pop(action_hash, None) is not None:
            self._flush()

    def __contains__(self, action_hash: str) -> bool:
        return action_hash in self._entries

    def _load(self) -> dict[str, UndoHandle]:
        if not self._path.is_file():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return {
            h: UndoHandle(kind=v["kind"], ref=v["ref"])
            for h, v in raw.items()
            if isinstance(v, dict) and v.get("kind") in _KINDS and "ref" in v
        }

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {h: {"kind": u.kind, "ref": u.ref} for h, u in self._entries.items()}
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)
