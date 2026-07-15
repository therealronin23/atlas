#!/usr/bin/env python3
"""Atomically import Graphify JSON into Neo4j with parameterized UNWIND batches."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    from neo4j import GraphDatabase
except ImportError:  # pragma: no cover - exercised only in an incomplete operator env
    print(
        "ERROR: neo4j driver is not installed; install the pinned knowledge-stack requirements.",
        file=sys.stderr,
    )
    raise SystemExit(1)


_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_SCALAR_TYPES = (str, int, float, bool)


def _identifier(value: object, *, kind: str, uppercase: bool = False) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing {kind}")
    normalized = value.upper() if uppercase else value.capitalize()
    if not _IDENTIFIER.fullmatch(normalized):
        raise ValueError(f"unsafe {kind}: {value!r}")
    return normalized


def _properties(raw: Mapping[str, object], *, identifier: str) -> dict[str, object]:
    properties = {
        key: value
        for key, value in raw.items()
        if isinstance(key, str)
        and not key.startswith("_")
        and isinstance(value, _SCALAR_TYPES)
    }
    properties["id"] = identifier
    return properties


def _chunks(rows: Sequence[dict[str, object]], size: int) -> Iterator[list[dict[str, object]]]:
    for start in range(0, len(rows), size):
        yield list(rows[start : start + size])


def _prepare_graph(
    graph: Mapping[str, object],
) -> tuple[dict[str, list[dict[str, object]]], dict[str, list[dict[str, object]]]]:
    # Graphify 0.9.11 reports the underlying NetworkX graph as undirected but
    # still emits an ordered source/target pair for each Neo4j relationship.
    # The link order, not this metadata flag, is the exporter's live contract.
    if graph.get("multigraph") is True:
        raise ValueError("Graphify multigraph exports are not supported")

    raw_nodes = graph.get("nodes")
    raw_links = graph.get("links")
    if not isinstance(raw_nodes, list) or not isinstance(raw_links, list):
        raise ValueError("Graphify export must contain nodes and links lists")

    node_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    node_ids: set[str] = set()
    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict):
            raise ValueError("every Graphify node must be an object")
        node_id = raw_node.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("every Graphify node must have a non-empty string id")
        if node_id in node_ids:
            raise ValueError(f"duplicate Graphify node id: {node_id!r}")
        node_ids.add(node_id)
        label = _identifier(raw_node.get("file_type") or "entity", kind="node label")
        node_groups[label].append(
            {"id": node_id, "props": _properties(raw_node, identifier=node_id)}
        )

    edge_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    edge_keys: set[tuple[str, str, str]] = set()
    for raw_link in raw_links:
        if not isinstance(raw_link, dict):
            raise ValueError("every Graphify link must be an object")
        source = raw_link.get("source")
        target = raw_link.get("target")
        if not isinstance(source, str) or not isinstance(target, str):
            raise ValueError("every Graphify link must have string source and target ids")
        if source not in node_ids or target not in node_ids:
            raise ValueError(f"Graphify link references a missing endpoint: {source!r} -> {target!r}")
        relation = _identifier(
            raw_link.get("relation") or "relates_to",
            kind="relationship type",
            uppercase=True,
        )
        edge_key = (source, target, relation)
        if edge_key in edge_keys:
            raise ValueError(f"duplicate Graphify relationship: {edge_key!r}")
        edge_keys.add(edge_key)
        edge_groups[relation].append(
            {
                "source": source,
                "target": target,
                "props": {
                    key: value
                    for key, value in raw_link.items()
                    if isinstance(key, str)
                    and not key.startswith("_")
                    and key not in {"source", "target"}
                    and isinstance(value, _SCALAR_TYPES)
                },
            }
        )

    return dict(sorted(node_groups.items())), dict(sorted(edge_groups.items()))


def _ensure_schema(transaction: Any) -> None:
    transaction.run(
        "CREATE CONSTRAINT graphify_node_id IF NOT EXISTS "
        "FOR (n:GraphifyNode) REQUIRE n.id IS UNIQUE"
    ).consume()


def _import_transaction(
    transaction: Any,
    node_groups: Mapping[str, list[dict[str, object]]],
    edge_groups: Mapping[str, list[dict[str, object]]],
    replace: bool,
    batch_size: int,
    expected_nodes: int,
    expected_relationships: int,
) -> tuple[int, int]:
    if replace:
        transaction.run("MATCH (n) DETACH DELETE n").consume()

    imported_nodes = 0
    for label, rows in node_groups.items():
        query = (
            "UNWIND $rows AS row\n"
            f"MERGE (n:GraphifyNode:{label} {{id: row.id}})\n"
            "SET n = row.props"
        )
        for batch in _chunks(rows, batch_size):
            transaction.run(query, rows=batch).consume()
            imported_nodes += len(batch)
            print(f"Imported nodes: {imported_nodes}/{expected_nodes}", flush=True)

    imported_relationships = 0
    for relation, rows in edge_groups.items():
        query = (
            "UNWIND $rows AS row\n"
            "MATCH (a:GraphifyNode {id: row.source})\n"
            "MATCH (b:GraphifyNode {id: row.target})\n"
            f"MERGE (a)-[r:{relation}]->(b)\n"
            "SET r = row.props"
        )
        for batch in _chunks(rows, batch_size):
            transaction.run(query, rows=batch).consume()
            imported_relationships += len(batch)
            print(
                f"Imported relationships: {imported_relationships}/{expected_relationships}",
                flush=True,
            )

    record = transaction.run(
        "CALL () { MATCH (n) RETURN count(n) AS nodes }\n"
        "CALL () { MATCH ()-[r]->() RETURN count(r) AS relationships }\n"
        "RETURN nodes, relationships"
    ).single(strict=True)
    actual = (int(record["nodes"]), int(record["relationships"]))
    expected = (expected_nodes, expected_relationships)
    if actual != expected:
        raise RuntimeError(
            f"database count {actual} does not match Graphify export {expected}; "
            "the import transaction will be rolled back"
        )
    return actual


def import_graph(
    driver: Any,
    graph: Mapping[str, object],
    *,
    replace: bool,
    batch_size: int,
) -> tuple[int, int]:
    """Import with atomic count-parity validation so partial writes roll back.

    Cardinality equality proves completeness of this transaction, not semantic
    identity with an already-populated database. A content digest is a separate
    future integrity control.
    """

    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    node_groups, edge_groups = _prepare_graph(graph)
    expected_nodes = sum(map(len, node_groups.values()))
    expected_relationships = sum(map(len, edge_groups.values()))

    with driver.session() as session:
        session.execute_write(_ensure_schema)
        return session.execute_write(
            _import_transaction,
            node_groups,
            edge_groups,
            replace,
            batch_size,
            expected_nodes,
            expected_relationships,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "graph_file",
        nargs="?",
        type=Path,
        default=Path("graphify-out/graph.json"),
        help="Graphify node-link JSON export (default: graphify-out/graph.json)",
    )
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="atomically replace the existing derived graph after verification",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    password = os.getenv("NEO4J_PASSWORD")
    if not password:
        parser.error("NEO4J_PASSWORD is required")
    if args.batch_size < 1:
        parser.error("--batch-size must be >= 1")
    if not args.graph_file.is_file():
        parser.error(f"Graph JSON file not found: {args.graph_file}")

    try:
        loaded = json.loads(args.graph_file.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("top-level JSON value must be an object")
        graph: Mapping[str, object] = loaded
        node_groups, edge_groups = _prepare_graph(graph)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: cannot validate {args.graph_file}: {exc}", file=sys.stderr)
        return 1

    expected_nodes = sum(map(len, node_groups.values()))
    expected_relationships = sum(map(len, edge_groups.values()))
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    print(
        f"Importing {expected_nodes} nodes and {expected_relationships} relationships "
        f"from {args.graph_file} into {uri}",
        flush=True,
    )

    driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=5)
    try:
        driver.verify_connectivity()
        actual_nodes, actual_relationships = import_graph(
            driver,
            graph,
            replace=args.replace,
            batch_size=args.batch_size,
        )
    except Exception as exc:
        print(f"ERROR: Neo4j import failed: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        driver.close()

    print(
        f"Import committed and verified: {actual_nodes} nodes, "
        f"{actual_relationships} relationships.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
