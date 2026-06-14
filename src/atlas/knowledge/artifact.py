from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class KnowledgeArtifact:
    """Unidad atómica de conocimiento normalizado.

    provenance claves esperadas:
      - url | endpoint : origen de la fetch
      - fetched_at     : ISO 8601 timestamp
      - raw_sha256     : hash del payload crudo antes de normalizar
    """

    id: str
    domain: str          # p.ej. "security/cve"
    source_id: str
    content: dict[str, Any] | str   # payload normalizado
    provenance: dict[str, Any]
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Serialización determinista; segura para json.dumps."""
        return {
            "id": self.id,
            "domain": self.domain,
            "source_id": self.source_id,
            "content": self.content,
            "provenance": self.provenance,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeArtifact":
        return cls(
            id=data["id"],
            domain=data["domain"],
            source_id=data["source_id"],
            content=data["content"],
            provenance=data["provenance"],
            schema_version=data.get("schema_version", 1),
        )
