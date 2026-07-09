"""Ingesta de conocimiento del repo al sustrato de memoria (SqliteMemoryIndex).

"Darle el conocimiento a Atlas" literal (campaña 2026-07-09): los docs de diseño
vigentes, las lecciones YAML y cualquier markdown curado entran al índice
verificable vía ``MemoryTrunk.add_from_knowledge_src`` (memory_class=factual,
con hash de procedencia), para que el recall del tronco los devuelva a
cualquier agente conectado — sin releer ficheros.

Idempotente: el ``record_id`` es determinista (``ki:<ruta>#<n>``) y el upsert
del índice reemplaza el registro si el doc cambió. Chunking por encabezados
``##`` con tope de tamaño — un doc largo entra como N registros consultables,
no como un bloque inservible para recall.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from atlas.mcp.memory_trunk import MemoryTrunk

__all__ = ["chunk_markdown", "ingest_paths", "ingest_repo_knowledge"]

# Tope por chunk: suficiente para una sección coherente, corto para recall útil.
_MAX_CHUNK_CHARS = 2400


def chunk_markdown(text: str) -> list[str]:
    """Trocea markdown por secciones ``##`` y luego por tamaño.

    Cada chunk conserva su encabezado (contexto para el recall). Sin
    encabezados, trocea plano por tamaño.
    """
    sections = re.split(r"(?m)^(?=## )", text)
    chunks: list[str] = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        while len(section) > _MAX_CHUNK_CHARS:
            cut = section.rfind("\n\n", 0, _MAX_CHUNK_CHARS)
            if cut <= 0:
                cut = _MAX_CHUNK_CHARS
            chunks.append(section[:cut].strip())
            section = section[cut:].strip()
        if section:
            chunks.append(section)
    return chunks


def ingest_paths(
    trunk: MemoryTrunk, paths: list[Path], *, repo_root: Path
) -> dict[str, Any]:
    """Ingiere ficheros (md/yaml/txt) como conocimiento factual. Devuelve métricas."""
    docs = 0
    records = 0
    skipped: list[str] = []
    for path in paths:
        if not path.is_file():
            skipped.append(str(path))
            continue
        rel = str(path.relative_to(repo_root)) if path.is_relative_to(repo_root) else str(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        chunks = chunk_markdown(text) if path.suffix == ".md" else [text[: _MAX_CHUNK_CHARS * 2]]
        for i, chunk in enumerate(chunks):
            body = f"[{rel} §{i}]\n{chunk}"
            trunk.add_from_knowledge_src(body, record_id=f"ki:{rel}#{i}", record_type="repo_doc")
            records += 1
        docs += 1
    return {"docs": docs, "records": records, "skipped": skipped}


def ingest_repo_knowledge(
    trunk: MemoryTrunk, repo_root: Path, *, index_yaml: Path | None = None
) -> dict[str, Any]:
    """Ingesta estándar del repo: docs design VIGENTES (según INDEX.yaml) +
    lecciones YAML de workspace/lessons. Es la carga que convierte el sustrato
    en la fuente de contexto de cualquier agente del tronco."""
    import yaml

    idx_path = index_yaml or (repo_root / "docs" / "INDEX.yaml")
    idx = yaml.safe_load(idx_path.read_text(encoding="utf-8"))
    vigentes = [
        repo_root / e["path"]
        for e in idx.get("entries", [])
        if e.get("status") == "vigente" and e["path"].startswith("docs/design/")
    ]
    lessons = sorted((repo_root / "workspace" / "lessons").glob("*.yaml"))
    return ingest_paths(trunk, vigentes + lessons, repo_root=repo_root)


if __name__ == "__main__":
    import argparse
    import json

    from atlas.mcp.memory_server import build_gated_index

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db_path", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    index = build_gated_index(args.db_path)
    try:
        result = ingest_repo_knowledge(MemoryTrunk(index), args.repo_root)
        print(json.dumps(result, indent=2, default=str))
    finally:
        index.close()
