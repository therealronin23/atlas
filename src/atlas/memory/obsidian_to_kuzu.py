"""Carga un vault Obsidian parseado en KuzuDB — eslabón Graphify→Obsidian→Kuzu.

Kuzu es schema-first (a diferencia del MERGE laissez-faire de Neo4j): el DDL
se declara idempotente al abrir. Esquema mínimo del eslabón; la capa
bitemporal completa es la misión `kuzu_bitemporal_schema` del backlog — aquí
solo se deja `ingested_at` como gancho para no re-migrar.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import kuzu

from atlas.memory.obsidian_vault import parse_vault

__all__ = ["load_vault_into_kuzu"]

_SCHEMA = (
    "CREATE NODE TABLE IF NOT EXISTS ObsidianNote("
    "path STRING, title STRING, note_type STRING, community STRING, "
    "tags STRING[], ingested_at TIMESTAMP, PRIMARY KEY(path))",
    "CREATE REL TABLE IF NOT EXISTS LINKS_TO(FROM ObsidianNote TO ObsidianNote)",
)


def load_vault_into_kuzu(
    vault_root: Path,
    db_path: Path,
    *,
    max_db_size: int = 1 << 30,
) -> dict[str, Any]:
    """Parsea el vault y lo persiste como grafo en Kuzu.

    Los wikilinks se resuelven por stem de nota (convención Obsidian:
    ``[[Nombre]]`` apunta a ``Nombre.md`` en cualquier carpeta). Links sin
    nota destino se cuentan como ``unresolved`` — no rompen la carga.

    Devuelve métricas: notes, links, unresolved.
    """
    vault = parse_vault(vault_root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = kuzu.Database(str(db_path), max_db_size=max_db_size)
    conn = kuzu.Connection(db)
    try:
        for ddl in _SCHEMA:
            conn.execute(ddl)

        # stem → path para resolver wikilinks (primera nota gana en colisión)
        stem_to_path: dict[str, str] = {}
        for rel_path in vault:
            stem = Path(rel_path).stem
            stem_to_path.setdefault(stem, rel_path)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for rel_path, note in vault.items():
            fm = note["frontmatter"]
            conn.execute(
                "MERGE (n:ObsidianNote {path: $path}) "
                "SET n.title = $title, n.note_type = $note_type, "
                "n.community = $community, n.tags = $tags, n.ingested_at = $ts",
                {
                    "path": rel_path,
                    "title": str(fm.get("title") or Path(rel_path).stem),
                    "note_type": str(fm.get("type") or ""),
                    "community": str(fm.get("community", "")),
                    "tags": [str(t) for t in note["tags"]],
                    "ts": now,
                },
            )

        links = 0
        unresolved = 0
        for rel_path, note in vault.items():
            for target in note["wikilinks"]:
                target_path = stem_to_path.get(target)
                if target_path is None:
                    unresolved += 1
                    continue
                conn.execute(
                    "MATCH (a:ObsidianNote {path: $src}), (b:ObsidianNote {path: $dst}) "
                    "MERGE (a)-[:LINKS_TO]->(b)",
                    {"src": rel_path, "dst": target_path},
                )
                links += 1

        return {"notes": len(vault), "links": links, "unresolved": unresolved}
    finally:
        conn.close()
        db.close()
