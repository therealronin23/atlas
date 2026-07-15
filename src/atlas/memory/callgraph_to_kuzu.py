"""Carga el call-graph que Graphify YA generó en KuzuDB — tercer eslabón de
la fusión Graphify→Obsidian→Kuzu (el primero es el grafo bitemporal de
``project_graph``, el segundo el vault de notas vía ``obsidian_to_kuzu``).

STALENESS — importante: los datos vienen de la ÚLTIMA corrida de graphify
sobre el árbol de trabajo (``graphify-out/cache/ast/<version>/``), NO
del working tree actual. Si el repo cambió desde esa corrida, el call-graph
puede estar desalineado con el código real. Regenerar con graphify
(~/proyectos/graphify-study) antes de confiar en resultados sensibles a
cambios recientes — ver ``docs/design/graphify_obsidian_kuzu_fusion.md``.

Esquema real de graphify (inspeccionado en vivo, no asumido de memoria):
cada JSON del cache_dir está *keyed por el content-hash del fichero fuente*
(mismo hash que ``src/graphify-out/cache/stat-index.json``, filename sin
``.json``) y trae:

  - ``nodes``: ficheros/clases/métodos/funciones. ``file_type`` es "code"
    (símbolo real) o "rationale" (texto de docstring extraído — se ignora
    aquí, no es un símbolo del call-graph). ``_callable: true`` marca
    función/método/clase; nodos sin ``source_file`` son símbolos externos
    (imports de librería, ej. "threading", "Path") con ``origin_file`` en
    su lugar.
  - ``edges``: ``relation`` en {calls, indirect_call, method, contains,
    imports, imports_from, inherits, references, rationale_for}, con
    ``confidence`` "EXTRACTED" (resuelto por AST) o "INFERRED" (heurística,
    solo en indirect_call). calls/indirect_call → tabla CALLS; method
    (clase→método) y contains (fichero→clase, ...) → tabla CONTAINS (dato
    barato, ya viene resuelto en el edge).
  - ``raw_calls``: extracción de más bajo nivel, pre-resolución a node ids
    (receiver/callee sueltos). No se usa aquí — ``edges`` ya trae los ids
    resueltos, que es lo que necesita un grafo Symbol→Symbol.

Verificado sobre el cache real: todo edge calls/indirect_call/
contains/method tiene AMBOS extremos dentro de los `nodes` del MISMO
fichero (0 referencias cruzadas rotas) — no hace falta resolver ids entre
ficheros, MERGE global tras cargar todos los nodos ya unifica símbolos
compartidos (ej. imports repetidos de "threading" en varios ficheros).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import kuzu

__all__ = ["load_callgraph_into_kuzu"]

_SCHEMA = (
    "CREATE NODE TABLE IF NOT EXISTS Symbol("
    "id STRING, name STRING, kind STRING, source_file STRING, "
    "source_location STRING, content_hash STRING, ingested_at TIMESTAMP, "
    "PRIMARY KEY(id))",
    "CREATE REL TABLE IF NOT EXISTS CALLS(FROM Symbol TO Symbol, confidence DOUBLE)",
    "CREATE REL TABLE IF NOT EXISTS CONTAINS(FROM Symbol TO Symbol)",
)

# Mismo criterio de tamaño de lote que obsidian_to_kuzu.py: UNWIND $batch
# como lista de parámetros compila el plan de consulta una vez por lote,
# no una vez por fila.
_BATCH_SIZE = 1000

_CALL_RELATIONS = {"calls", "indirect_call"}
_CONTAINS_RELATIONS = {"contains", "method"}
_CONFIDENCE_BY_LABEL = {"EXTRACTED": 1.0, "INFERRED": 0.5}


def _chunks(rows: list[Any], size: int) -> list[list[Any]]:
    return [rows[i : i + size] for i in range(0, len(rows), size)]


def _kind(node: dict[str, Any]) -> str:
    if not node.get("source_file"):
        return "external"
    if node.get("_callable"):
        return "callable"
    return "file"


def load_callgraph_into_kuzu(
    cache_dir: Path,
    db_path: Path,
    *,
    max_db_size: int = 1 << 30,
    source_prefix: str | None = None,
    replace: bool = False,
    strict: bool = False,
) -> dict[str, Any]:
    """Parsea el cache de graphify (``cache_dir``, un JSON por fichero fuente
    keyed por content-hash) y lo persiste como grafo Symbol/CALLS/CONTAINS
    en Kuzu. Idempotente (MERGE, no CREATE) — recargar el mismo cache no
    duplica símbolos ni aristas.

    ``source_prefix`` limita el corpus a ficheros Graphify que contengan al
    menos un nodo de código bajo esa ruta (por ejemplo ``src/atlas``). Con
    ``replace=True`` se elimina primero el call-graph anterior, de modo que no
    sobrevivan símbolos ajenos o borrados. ``strict=True`` convierte cualquier
    cache ilegible en error explícito en vez de producir un grafo parcial.

    Devuelve métricas: ``{"symbols": int, "calls": int, "files": int}``.
    """
    files = sorted(
        p
        for p in cache_dir.rglob("*.json")
        if p.is_file() and p.name != "stat-index.json"
    )
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = kuzu.Database(str(db_path), max_db_size=max_db_size)
    conn = kuzu.Connection(db)
    try:
        for ddl in _SCHEMA:
            conn.execute(ddl)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        symbol_rows: dict[str, dict[str, Any]] = {}
        call_rows: list[dict[str, Any]] = []
        contains_rows: list[dict[str, Any]] = []

        loaded_files = 0
        normalized_prefix = source_prefix.strip().strip("/") if source_prefix else ""
        for path in files:
            content_hash = path.stem
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                if strict:
                    raise ValueError(f"invalid Graphify AST cache file: {path}") from exc
                continue

            if normalized_prefix and not any(
                str(node.get("source_file", "")).strip("/") == normalized_prefix
                or str(node.get("source_file", "")).strip("/").startswith(
                    normalized_prefix + "/"
                )
                for node in data.get("nodes", [])
                if node.get("file_type") == "code"
            ):
                continue
            loaded_files += 1

            nodes = data.get("nodes", [])
            edges = data.get("edges", [])

            local_ids: set[str] = set()
            for node in nodes:
                if node.get("file_type") != "code":
                    continue  # nodos "rationale" no son símbolos
                nid = str(node["id"])
                local_ids.add(nid)
                symbol_rows[nid] = {
                    "id": nid,
                    "name": str(node.get("label", "")),
                    "kind": _kind(node),
                    "source_file": str(node.get("source_file", "")),
                    "source_location": str(node.get("source_location", "")),
                    "content_hash": content_hash,
                    "ts": now,
                }

            for edge in edges:
                src, dst = edge.get("source"), edge.get("target")
                if src not in local_ids or dst not in local_ids:
                    continue  # extremo es un nodo rationale (u otro no-símbolo)
                relation = edge.get("relation")
                if relation in _CALL_RELATIONS:
                    confidence = _CONFIDENCE_BY_LABEL.get(edge.get("confidence"), 0.5)
                    call_rows.append({"src": src, "dst": dst, "confidence": confidence})
                elif relation in _CONTAINS_RELATIONS:
                    contains_rows.append({"src": src, "dst": dst})

        rows = list(symbol_rows.values())
        if replace:
            conn.execute("MATCH (s:Symbol) DETACH DELETE s")

        for batch in _chunks(rows, _BATCH_SIZE):
            conn.execute(
                "UNWIND $rows AS row "
                "MERGE (s:Symbol {id: row.id}) "
                "SET s.name = row.name, s.kind = row.kind, "
                "s.source_file = row.source_file, s.source_location = row.source_location, "
                "s.content_hash = row.content_hash, s.ingested_at = row.ts",
                {"rows": batch},
            )

        for batch in _chunks(call_rows, _BATCH_SIZE):
            conn.execute(
                "UNWIND $rows AS row "
                "MATCH (a:Symbol {id: row.src}), (b:Symbol {id: row.dst}) "
                "MERGE (a)-[c:CALLS]->(b) SET c.confidence = row.confidence",
                {"rows": batch},
            )

        for batch in _chunks(contains_rows, _BATCH_SIZE):
            conn.execute(
                "UNWIND $rows AS row "
                "MATCH (a:Symbol {id: row.src}), (b:Symbol {id: row.dst}) "
                "MERGE (a)-[:CONTAINS]->(b)",
                {"rows": batch},
            )

        return {"symbols": len(rows), "calls": len(call_rows), "files": loaded_files}
    finally:
        conn.close()
        db.close()
