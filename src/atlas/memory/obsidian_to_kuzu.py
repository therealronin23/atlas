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

# 2026-07-09: un conn.execute() por fila midió 21min para 4360 notas +
# 26392 links (vault Obsidian real vía fusión Graphify). UNWIND $batch
# como lista de parámetros mide ~16x más rápido en microbenchmark local
# (una sola compilación de plan de consulta por lote, no una por fila).
_BATCH_SIZE = 1000


def _chunks(rows: list[Any], size: int) -> list[list[Any]]:
    return [rows[i : i + size] for i in range(0, len(rows), size)]


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
        note_rows = [
            {
                "path": rel_path,
                "title": str(note["frontmatter"].get("title") or Path(rel_path).stem),
                "note_type": str(note["frontmatter"].get("type") or ""),
                "community": str(note["frontmatter"].get("community", "")),
                "tags": [str(t) for t in note["tags"]],
                "ts": now,
            }
            for rel_path, note in vault.items()
        ]
        for batch in _chunks(note_rows, _BATCH_SIZE):
            conn.execute(
                "UNWIND $rows AS row "
                "MERGE (n:ObsidianNote {path: row.path}) "
                "SET n.title = row.title, n.note_type = row.note_type, "
                "n.community = row.community, n.tags = row.tags, n.ingested_at = row.ts",
                {"rows": batch},
            )

        link_rows: list[dict[str, str]] = []
        unresolved = 0
        for rel_path, note in vault.items():
            for target in note["wikilinks"]:
                target_path = stem_to_path.get(target)
                if target_path is None:
                    unresolved += 1
                    continue
                link_rows.append({"src": rel_path, "dst": target_path})

        for batch in _chunks(link_rows, _BATCH_SIZE):
            conn.execute(
                "UNWIND $rows AS row "
                "MATCH (a:ObsidianNote {path: row.src}), (b:ObsidianNote {path: row.dst}) "
                "MERGE (a)-[:LINKS_TO]->(b)",
                {"rows": batch},
            )

        return {"notes": len(vault), "links": len(link_rows), "unresolved": unresolved}
    finally:
        conn.close()
        db.close()
