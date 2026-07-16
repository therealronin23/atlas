#!/usr/bin/env python3
"""Export Graphify's canonical graph to Obsidian within the real NAME_MAX.

Graphify 0.9.11 caps note stems at 200 bytes, which still exceeds encrypted or
stacked filesystems whose per-component limit can be lower than 255 bytes. The
project pins that Graphify version, so this adapter narrows its filename cap at
runtime while leaving graph labels and the canonical graph JSON untouched.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from graphify import export as graphify_export
from graphify.security import check_graph_file_size_cap
from networkx.readwrite import json_graph


_FILENAME_RESERVE = 16  # .md plus a collision suffix such as _12345.


def _filesystem_name_max(directory: Path) -> int:
    try:
        value = int(os.pathconf(directory, "PC_NAME_MAX"))
    except (OSError, ValueError):
        value = 255
    return max(32, value)


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _looks_graphify_generated(path: Path, relative: str, owned: set[str]) -> bool:
    if relative in owned or relative in {
        ".graphify_obsidian_manifest.json",
        ".obsidian/graph.json",
        "graph.canvas",
    }:
        return True
    if path.suffix.lower() != ".md":
        return False
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:16_384]
    except OSError:
        return False
    node_note = head.startswith("---\nsource_file:") and "graphify/" in head
    community_note = (
        head.startswith("---\ntype: community\n") and "\n## Members\n" in head
    )
    return node_note or community_note


def _user_owned_files(output_dir: Path) -> list[tuple[Path, Path]]:
    manifest = _load_optional_json(
        output_dir / ".graphify_obsidian_manifest.json"
    )
    raw_owned = manifest.get("files")
    owned = {
        str(value)
        for value in raw_owned
        if isinstance(value, str)
    } if isinstance(raw_owned, list) else set()
    preserved: list[tuple[Path, Path]] = []
    for path in output_dir.rglob("*"):
        if path.is_symlink():
            raise ValueError("Obsidian vault must not contain symlinks")
        if not path.is_file():
            continue
        relative_path = path.relative_to(output_dir)
        relative = relative_path.as_posix()
        if not _looks_graphify_generated(path, relative, owned):
            preserved.append((path, relative_path))
    return preserved


def _write_export(
    graph: Any,
    communities: dict[int, list[str]],
    labels: dict[int, str],
    cohesion: dict[int, float],
    output_dir: Path,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    name_max = _filesystem_name_max(output_dir)
    stem_limit = max(16, min(200, name_max - _FILENAME_RESERVE))
    original_cap = graphify_export._cap_filename

    def cap_for_filesystem(value: str, limit: int = 200) -> str:
        return original_cap(value, min(limit, stem_limit))

    graphify_export._cap_filename = cap_for_filesystem
    try:
        notes = graphify_export.to_obsidian(
            graph,
            communities,
            str(output_dir),
            community_labels=labels or None,
            cohesion=cohesion or None,
        )
        graphify_export.to_canvas(
            graph,
            communities,
            str(output_dir / "graph.canvas"),
            community_labels=labels or None,
        )
    finally:
        graphify_export._cap_filename = original_cap
    if notes < graph.number_of_nodes():
        raise RuntimeError("Obsidian export skipped canonical graph nodes")
    over_limit = [
        path.name
        for path in output_dir.iterdir()
        if len(path.name.encode("utf-8")) > name_max
    ]
    if over_limit:
        raise RuntimeError("Obsidian export produced an over-limit filename")
    return notes


def export_obsidian(
    graph_path: Path,
    output_dir: Path,
    *,
    replace_generated: bool = False,
) -> int:
    graph_candidate = graph_path.expanduser().absolute()
    output_candidate = output_dir.expanduser().absolute()
    if graph_candidate.is_symlink() or not graph_candidate.is_file():
        raise ValueError("graph path must be a regular non-symlink file")
    if output_candidate.is_symlink() or (
        output_candidate.exists() and not output_candidate.is_dir()
    ):
        raise ValueError("output path must be a non-symlink directory")
    graph_path = graph_candidate.resolve()
    output_dir = output_candidate.resolve()

    check_graph_file_size_cap(graph_path)
    raw = json.loads(graph_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("graph JSON must be an object")
    if "links" not in raw and isinstance(raw.get("edges"), list):
        raw = dict(raw, links=raw["edges"])
    try:
        graph = json_graph.node_link_graph(raw, edges="links")
    except TypeError:  # NetworkX compatibility before the edges= keyword.
        graph = json_graph.node_link_graph(raw)

    analysis = _load_optional_json(graph_path.parent / ".graphify_analysis.json")
    communities_raw = analysis.get("communities")
    if not isinstance(communities_raw, dict):
        communities_raw = {}
    communities = {
        int(key): value
        for key, value in communities_raw.items()
        if isinstance(value, list)
    }
    cohesion_raw = analysis.get("cohesion")
    if not isinstance(cohesion_raw, dict):
        cohesion_raw = {}
    cohesion = {
        int(key): float(value)
        for key, value in cohesion_raw.items()
        if isinstance(value, (int, float))
    }
    if not communities:
        for node_id, data in graph.nodes(data=True):
            raw_community = data.get("community")
            try:
                community = int(raw_community)
            except (TypeError, ValueError):
                continue
            communities.setdefault(community, []).append(str(node_id))

    labels_raw = _load_optional_json(graph_path.parent / ".graphify_labels.json")
    labels = {int(key): str(value) for key, value in labels_raw.items()}

    if not replace_generated:
        return _write_export(graph, communities, labels, cohesion, output_dir)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    preserved = _user_owned_files(output_dir) if output_dir.exists() else []
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.rebuild-",
            dir=output_dir.parent,
        )
    )
    backup = output_dir.parent / f".{output_dir.name}.backup-{os.getpid()}"
    try:
        notes = _write_export(graph, communities, labels, cohesion, temporary)
        for source, relative in preserved:
            destination = temporary / relative
            if destination.exists():
                if destination.read_bytes() != source.read_bytes():
                    raise RuntimeError(
                        "user-owned Obsidian note collides with generated output"
                    )
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        if backup.exists():
            raise RuntimeError("stale Obsidian backup blocks atomic replacement")
        if output_dir.exists():
            output_dir.rename(backup)
        try:
            temporary.rename(output_dir)
        except Exception:
            if backup.exists() and not output_dir.exists():
                backup.rename(output_dir)
            raise
        if backup.exists():
            shutil.rmtree(backup)
        return notes
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, default=Path("graphify-out/graph.json"))
    parser.add_argument("--output", type=Path, default=Path("graphify-vault"))
    parser.add_argument("--replace-generated", action="store_true")
    args = parser.parse_args()
    try:
        notes = export_obsidian(
            args.graph,
            args.output,
            replace_generated=args.replace_generated,
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: Obsidian export failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    print(f"Obsidian vault: {notes} notes in {args.output}/")
    print(f"Canvas: {args.output}/graph.canvas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
