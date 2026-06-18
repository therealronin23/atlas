"""
Atlas Core — Block Memory (ADR-030).

Absorbs Letta/MemGPT *core memory*: a small set of labelled, character-bounded
text blocks that are always in context and that the agent edits in place
(persona, human, project, ...). This is the complement to Atlas's existing
*archival* memory (KuzuVectorStore + relevance/recency ranking) — block memory
is the always-resident working set, archival is the searchable long tail.

Design constraints (AGENTS.md coding rules):
  - stdlib only (json + dataclasses). No new dependency (rule 6).
  - Every mutation is logged to the Merkle ledger (rule 1).
  - Blocks are character-bounded; an over-limit edit raises rather than silently
    truncating, so the caller (agent) must summarise/evict — the MemGPT
    pressure mechanism, not a lossy write.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from atlas.logging.merkle_logger import MerkleLogger

DEFAULT_LIMIT = 2000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BlockMemoryError(Exception):
    """Base error for block-memory operations."""


class BlockNotFound(BlockMemoryError):
    pass


class BlockExists(BlockMemoryError):
    pass


class BlockLimitExceeded(BlockMemoryError):
    """Raised when an edit would push a block past its character limit."""


@dataclass
class MemoryBlock:
    label: str
    value: str = ""
    limit: int = DEFAULT_LIMIT
    description: str = ""
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def chars(self) -> int:
        return len(self.value)

    @property
    def is_full(self) -> bool:
        return self.chars >= self.limit


class BlockMemory:
    """Manager for the agent's always-in-context labelled memory blocks.

    Blocks are persisted together in a single ``blocks.json`` because the whole
    set is small and always loaded together.
    """

    AGENT = "block_memory"

    def __init__(self, store_path: Path, merkle: "MerkleLogger | None" = None) -> None:
        self._dir = store_path
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "blocks.json"
        self._merkle = merkle
        self._blocks: dict[str, MemoryBlock] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            raw = json.loads(self._file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for label, data in raw.get("blocks", {}).items():
            try:
                self._blocks[label] = MemoryBlock(**data)
            except TypeError:
                continue

    def _save(self) -> None:
        payload = {"blocks": {label: b.to_dict() for label, b in self._blocks.items()}}
        self._file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _log(self, action: str, label: str, extra: dict[str, Any] | None = None) -> None:
        if self._merkle is None:
            return
        payload = {"label": label}
        if extra:
            payload.update(extra)
        self._merkle.log(
            action=action,
            agent=self.AGENT,
            result="success",
            risk_level="safe",
            payload=payload,
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, label: str) -> MemoryBlock | None:
        return self._blocks.get(label)

    def labels(self) -> list[str]:
        return sorted(self._blocks)

    def all(self) -> list[MemoryBlock]:
        return [self._blocks[label] for label in self.labels()]

    def render(self) -> str:
        """Render all blocks as a context string for prompt injection.

        Each block becomes a labelled XML-ish section, ordered by label so the
        output is deterministic.
        """
        parts: list[str] = []
        for block in self.all():
            parts.append(f"<{block.label}>\n{block.value}\n</{block.label}>")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Mutations (each enforces the limit and audits)
    # ------------------------------------------------------------------

    def create(
        self, label: str, value: str = "", limit: int = DEFAULT_LIMIT, description: str = ""
    ) -> MemoryBlock:
        if label in self._blocks:
            raise BlockExists(f"block '{label}' already exists")
        if len(value) > limit:
            raise BlockLimitExceeded(f"value ({len(value)}) exceeds limit ({limit})")
        block = MemoryBlock(label=label, value=value, limit=limit, description=description)
        self._blocks[label] = block
        self._save()
        self._log("memory.block.created", label, {"limit": limit, "chars": block.chars})
        return block

    def set(self, label: str, value: str) -> MemoryBlock:
        block = self._require(label)
        if len(value) > block.limit:
            raise BlockLimitExceeded(
                f"value ({len(value)}) exceeds '{label}' limit ({block.limit})"
            )
        block.value = value
        block.updated_at = _now_iso()
        self._save()
        self._log("memory.block.edited", label, {"op": "set", "chars": block.chars})
        return block

    def append(self, label: str, text: str, sep: str = "\n") -> MemoryBlock:
        block = self._require(label)
        new_value = f"{block.value}{sep}{text}" if block.value else text
        if len(new_value) > block.limit:
            raise BlockLimitExceeded(
                f"append would push '{label}' to {len(new_value)} > limit ({block.limit})"
            )
        block.value = new_value
        block.updated_at = _now_iso()
        self._save()
        self._log("memory.block.edited", label, {"op": "append", "chars": block.chars})
        return block

    def replace(self, label: str, old: str, new: str) -> MemoryBlock:
        block = self._require(label)
        if old not in block.value:
            raise BlockMemoryError(f"substring not found in '{label}'")
        candidate = block.value.replace(old, new)
        if len(candidate) > block.limit:
            raise BlockLimitExceeded(
                f"replace would push '{label}' to {len(candidate)} > limit ({block.limit})"
            )
        block.value = candidate
        block.updated_at = _now_iso()
        self._save()
        self._log("memory.block.edited", label, {"op": "replace", "chars": block.chars})
        return block

    def delete(self, label: str) -> None:
        self._require(label)
        del self._blocks[label]
        self._save()
        self._log("memory.block.deleted", label)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require(self, label: str) -> MemoryBlock:
        block = self._blocks.get(label)
        if block is None:
            raise BlockNotFound(f"block '{label}' does not exist")
        return block


__all__ = [
    "BlockMemory",
    "MemoryBlock",
    "BlockMemoryError",
    "BlockNotFound",
    "BlockExists",
    "BlockLimitExceeded",
    "DEFAULT_LIMIT",
]
