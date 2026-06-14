"""
MissionRunner — integrador T7 (ADR-049).

Orquesta fetch → artifact → verify → base.add para un conjunto de fuentes
declaradas en una Mission. Sin daemon ni scheduler: solo run_once inyectable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from atlas.knowledge.artifact import KnowledgeArtifact
from atlas.knowledge.base import KnowledgeBase, KnowledgeRejected
from atlas.knowledge.sources import KnowledgeSource
from atlas.knowledge.verifier import KnowledgeVerifier


@dataclass(frozen=True)
class Mission:
    id: str
    domain: str
    goal: str
    source_ids: list[str]
    cadence_s: int


@dataclass(frozen=True)
class MissionReport:
    mission_id: str
    ingested: int
    rejected: int
    errors: tuple[tuple[str, str], ...]   # (source_id, mensaje)
    ingested_ids: tuple[str, ...] = ()


class MissionRunner:
    def __init__(
        self,
        *,
        sources: dict[str, KnowledgeSource],
        verifier: KnowledgeVerifier,
        base: KnowledgeBase,
    ) -> None:
        self._sources = sources
        self._verifier = verifier
        self._base = base

    def run_once(
        self,
        mission: Mission,
        *,
        queries: dict[str, object] | None = None,
    ) -> MissionReport:
        ingested = 0
        rejected = 0
        errors: list[tuple[str, str]] = []
        ingested_ids: list[str] = []

        for source_id in mission.source_ids:
            src = self._sources.get(source_id)
            if src is None:
                errors.append((source_id, f"fuente no registrada: {source_id!r}"))
                continue

            query = (queries or {}).get(source_id)
            try:
                records = src.fetch(query)
            except Exception as exc:  # noqa: BLE001 — aislamos por fuente
                errors.append((source_id, f"fetch error: {exc}"))
                continue

            domain = mission.domain or src.domain

            for rec in records:
                # Construir artifact con id determinista basado en url + hash
                raw_sha256 = hashlib.sha256(rec.payload.encode()).hexdigest()
                artifact_id = f"{source_id}:{raw_sha256[:16]}"

                try:
                    content: Any = json.loads(rec.payload)
                except (json.JSONDecodeError, ValueError):
                    content = rec.payload

                provenance = {
                    "url": rec.url,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "raw_sha256": raw_sha256,
                }

                artifact = KnowledgeArtifact(
                    id=artifact_id,
                    domain=domain,
                    source_id=source_id,
                    content=content,
                    provenance=provenance,
                )

                evidence = self._verifier.verify(artifact, rec.payload)

                try:
                    self._base.add(artifact, evidence)
                    ingested += 1
                    ingested_ids.append(artifact_id)
                except KnowledgeRejected:
                    rejected += 1

        return MissionReport(
            mission_id=mission.id,
            ingested=ingested,
            rejected=rejected,
            errors=tuple(errors),
            ingested_ids=tuple(ingested_ids),
        )
