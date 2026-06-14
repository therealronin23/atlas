"""
KnowledgeBase: store JSONL por dominio, con ley de entrada (Evidence PASS).

Un dominio puede contener "/" (p.ej. "security/cve"). Para mantener un único
directorio plano sin subdirectorios, los "/" se reemplazan por "__" en el nombre
de fichero: "security/cve" → "security__cve.jsonl". Esto es simple, robusto y
reversible si hace falta inspección manual.
"""

from __future__ import annotations

import json
from pathlib import Path

from atlas.core.verify import Evidence, Verdict
from atlas.knowledge.artifact import KnowledgeArtifact


class KnowledgeRejected(Exception):
    """Se intentó ingerir conocimiento no verificado (verdict != PASS)."""


class KnowledgeBase:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _jsonl_path(self, domain: str) -> Path:
        safe = domain.replace("/", "__")
        return self._root / f"{safe}.jsonl"

    def add(self, artifact: KnowledgeArtifact, evidence: Evidence) -> None:
        if evidence.verdict is not Verdict.PASS:
            raise KnowledgeRejected(
                f"artifact {artifact.id!r} rechazado: verdict={evidence.verdict.value!r} != PASS"
            )
        path = self._jsonl_path(artifact.domain)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(artifact.to_dict(), ensure_ascii=False) + "\n")

    def query(self, domain: str) -> list[KnowledgeArtifact]:
        path = self._jsonl_path(domain)
        if not path.is_file():
            return []
        results: list[KnowledgeArtifact] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                results.append(KnowledgeArtifact.from_dict(json.loads(line)))
            except Exception:  # noqa: BLE001 — línea corrupta no tumba la query
                continue
        return results
