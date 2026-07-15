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
_PROVIDER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _imports_home() -> Path:
    home = Path(os.environ.get("ATLAS_HOME", "~/atlas")).expanduser()
    return home / "os_imports"


def _validated_provider(raw: object) -> str:
    provider = str(raw or "unknown")
    if not _PROVIDER_RE.fullmatch(provider):
        raise ValueError("provider must be a safe 1-64 character identifier")
    return provider


def _secure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)


def _assert_private_regular_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"refusing unsafe import path: {path}")
    os.chmod(path, 0o600)


def _write_new_private(path: Path, content: str) -> bool:
    """Create one private regular file without following links.

    Returns False if another writer already created the same digest path.
    """

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        _assert_private_regular_file(path)
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    return True


def _append_private(path: Path, lines: list[str]) -> None:
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


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
    _secure_directory(raw_dir)

    canonical = json.dumps(raw, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    provider = _validated_provider(raw.get("provider", "unknown"))
    # Provider is provenance, never path material. Hash-only naming removes the
    # traversal surface and makes idempotence content-addressed across providers.
    raw_path = raw_dir / f"{digest}.json"
    if not raw_path.resolve().is_relative_to(raw_dir.resolve()):
        raise ValueError("raw import path escaped its storage directory")
    raw_ref = str(raw_path)

    already = not _write_new_private(raw_path, canonical + "\n")

    records_path = home / "memory_records.jsonl"
    if already:
        existing: list[dict[str, Any]] = []
        if records_path.exists():
            _assert_private_regular_file(records_path)
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
    _append_private(
        records_path,
        [json.dumps(record, ensure_ascii=False) for record in records],
    )
    return ImportResult(source_ref=raw_ref, raw_preserved=True,
                        already_imported=False, records=records)


def list_imported_records(base: Path | None = None, limit: int = 200) -> list[dict[str, Any]]:
    home = base or _imports_home()
    path = home / "memory_records.jsonl"
    if not path.exists():
        return []
    _assert_private_regular_file(path)
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return records[-limit:]
