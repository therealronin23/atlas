"""Import de conversaciones externas (Claude/ChatGPT/Cursor) — Fase 8 Memory OS.

Reglas del master prompt §14 que este módulo cumple de verdad:
  * NUNCA destruye la fuente: copia raw a $ATLAS_HOME/os_imports/raw/<sha>.json
    antes de extraer nada (idempotente por hash de contenido).
  * Toda memoria extraída lleva provenance {source, raw_ref} y trust explícito.
  * La extracción es por REGLAS auditables (extraction_method=rules_v1), no un
    LLM fingiendo entender: v1 honesto y determinista.

Capa OS: los registros van a os_imports/memory_records.jsonl (representación).
La ingesta al índice canónico (ADR-057) es cableado futuro vía knowledge_ingest
— declarado en OPEN_QUESTIONS, no fingido aquí.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Marcadores por regla — minúsculas; ampliar AQUÍ y en el test, en el mismo commit.
_DECISION_MARKERS = ("decisión:", "decision:", "decidimos", "queda decidido")
_FAILURE_MARKERS = ("falló", "fallo:", "error '", 'error "', "lección:", "leccion:")
_PATTERN_MARKERS = ("patrón recomendado", "patron recomendado", "error común a evitar")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _imports_home() -> Path:
    home = Path(os.environ.get("ATLAS_HOME", "~/atlas")).expanduser()
    return home / "os_imports"


@dataclass
class ImportResult:
    source_ref: str
    raw_preserved: bool
    already_imported: bool
    records: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_ref": self.source_ref,
            "raw_preserved": self.raw_preserved,
            "already_imported": self.already_imported,
            "records": self.records,
            "record_count": len(self.records),
        }


def _mk_record(kind: str, summary: str, source: str, raw_ref: str) -> dict[str, Any]:
    """Registro conforme a schemas/memory.schema.json."""
    return {
        "memory_id": f"mem_{uuid.uuid4().hex[:12]}",
        "kind": kind,
        "summary": summary[:500],
        "provenance": {
            "source": source,
            "raw_ref": raw_ref,
            "imported_from": "conversation_import.rules_v1",
        },
        "trust": "user_stated",
        "risk": "low",
        "created_at": _now(),
        "contradicts": [],
        "metadata": {"extraction_method": "rules_v1"},
    }


def _extract(messages: list[dict[str, Any]], source: str, raw_ref: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for msg in messages:
        content = str(msg.get("content", ""))
        role = str(msg.get("role", ""))
        for sentence in re.split(r"(?<=[.!?])\s+", content):
            low = sentence.lower()
            if any(m in low for m in _DECISION_MARKERS) and role == "user":
                records.append(_mk_record("decision", sentence.strip(), source, raw_ref))
            elif any(m in low for m in _FAILURE_MARKERS):
                records.append(_mk_record("failure", sentence.strip(), source, raw_ref))
            elif any(m in low for m in _PATTERN_MARKERS):
                records.append(_mk_record("procedural", sentence.strip(), source, raw_ref))
    return records


def import_conversation(raw: dict[str, Any], base: Path | None = None) -> ImportResult:
    home = base or _imports_home()
    raw_dir = home / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    canonical = json.dumps(raw, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    provider = str(raw.get("provider", "unknown"))
    raw_path = raw_dir / f"{provider}_{digest}.json"
    raw_ref = str(raw_path)

    already = raw_path.exists()
    if not already:
        raw_path.write_text(canonical + "\n", encoding="utf-8")

    records_path = home / "memory_records.jsonl"
    if already:
        existing: list[dict[str, Any]] = []
        if records_path.exists():
            for line in records_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    if rec.get("provenance", {}).get("raw_ref") == raw_ref:
                        existing.append(rec)
        return ImportResult(source_ref=raw_ref, raw_preserved=True,
                            already_imported=True, records=existing)

    messages = raw.get("messages", [])
    if not isinstance(messages, list):
        messages = []
    records = _extract(messages, source=f"import:{provider}", raw_ref=raw_ref)
    with records_path.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return ImportResult(source_ref=raw_ref, raw_preserved=True,
                        already_imported=False, records=records)


def list_imported_records(base: Path | None = None, limit: int = 200) -> list[dict[str, Any]]:
    home = base or _imports_home()
    path = home / "memory_records.jsonl"
    if not path.exists():
        return []
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return records[-limit:]
