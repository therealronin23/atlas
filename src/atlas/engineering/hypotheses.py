"""Diagnostic hypotheses for an engineering finding, composed from sources
that already exist (ADC-WO-108, piece 4/5).

This module deliberately does not implement a graph engine, a history
walker, or a recall engine. It routes a finding's location to three
already-live subsystems:

- graph: `atlas.core.graphs.QUERIES` (Cypher) over the project's live Kuzu
  graph, via the same `open_kuzu_database` helper the MCP graph server
  uses (`atlas.mcp.graph_server.build_graph_server`).
- history: `git log` through `atlas.core.git_env.clean_git_env`, the same
  sanitized-environment pattern `EngineeringIncrementalReviewPreparer`
  already uses for read-only Git access.
- memory: `atlas.core.lesson_store.LessonStore.search_by_tag`, the
  existing lesson index -- no new store, no new recall algorithm.

Fail-honest by design: a missing or unreadable source produces a hypothesis
with ``available=False`` and a human-readable ``reason``, never an
exception. One source being absent must never prevent the other two from
being reported.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from atlas.core.git_env import clean_git_env
from atlas.core.graphs import QUERIES
from atlas.core.lesson_store import LessonStore
from atlas.engineering.findings import FindingLocation
from atlas.memory.kuzu_runtime import open_kuzu_database
from atlas.mcp.graph_server import _rows as _kuzu_rows

_GIT_TIMEOUT_S = 30


def module_name_for_path(path: str) -> str | None:
    """Convert a repo-relative source path to a dotted module name.

    Returns ``None`` for anything outside ``src/atlas`` -- the graph only
    ingests that subtree (see `atlas.core.graphs.list_files_at_commit`),
    so a docs/tests/fixtures path has no module identity to look up.
    """
    if not path.startswith("src/atlas/") or not path.endswith(".py"):
        return None
    trimmed = path.removeprefix("src/").removesuffix(".py")
    if trimmed.endswith("/__init__"):
        trimmed = trimmed.removesuffix("/__init__")
    return trimmed.replace("/", ".")


@dataclass(frozen=True)
class GraphHypothesis:
    available: bool
    module: str = ""
    importers: tuple[str, ...] = ()
    blast_radius: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class HistoryHypothesis:
    available: bool
    path: str = ""
    commit_count: int = 0
    last_commit_at: str = ""
    reason: str = ""


@dataclass(frozen=True)
class MemoryHypothesis:
    available: bool
    tag: str = ""
    lesson_count: int = 0
    lesson_ids: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class EngineeringHypothesisSet:
    location: FindingLocation
    graph: GraphHypothesis
    history: HistoryHypothesis
    memory: MemoryHypothesis


def graph_hypothesis(module: str, *, db_path: Path) -> GraphHypothesis:
    """Who imports `module` and what breaks if it changes -- same Cypher
    the `graph_importers`/`graph_blast_radius` MCP tools run, read-only."""
    if not db_path.exists():
        return GraphHypothesis(
            available=False, module=module,
            reason=f"no existe grafo Kuzu en {db_path} -- correr el tick del grafo primero",
        )
    try:
        db = open_kuzu_database(db_path, read_only=True)
    except (RuntimeError, OSError) as exc:
        return GraphHypothesis(
            available=False, module=module,
            reason=f"grafo no abrible: {type(exc).__name__}: {exc}",
        )
    try:
        import kuzu  # local import: only needed on the success path

        conn = kuzu.Connection(db)
        try:
            latest_rows = _kuzu_rows(conn.execute(
                "MATCH (v:FileVersion) RETURN v.commit_sha AS sha "
                "ORDER BY v.ingested_at DESC LIMIT 1"
            ))
            if not latest_rows:
                return GraphHypothesis(
                    available=False, module=module,
                    reason="grafo abrible pero sin ningún commit ingerido",
                )
            sha = latest_rows[0][0]
            importers = [
                row[0]
                for row in _kuzu_rows(conn.execute(
                    QUERIES["direct_importers"], parameters={"path": module, "sha": sha}
                ))
            ]
            blast = [
                row[0]
                for row in _kuzu_rows(conn.execute(
                    QUERIES["blast_radius"], parameters={"path": module, "sha": sha}
                ))
            ]
            return GraphHypothesis(
                available=True, module=module,
                importers=tuple(importers), blast_radius=tuple(blast),
            )
        finally:
            conn.close()
    finally:
        db.close()


def history_hypothesis(repo_root: Path, path: str) -> HistoryHypothesis:
    """Commit count and last-touched date for `path`, via `git log`. A path
    that was never tracked returns `commit_count=0`, not `available=False`
    -- git itself answered the question, the answer is just "never"."""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%H %cI", "--", path],
            cwd=repo_root,
            env=clean_git_env(),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return HistoryHypothesis(
            available=False, path=path,
            reason=f"git log falló: {type(exc).__name__}: {exc}",
        )
    if result.returncode != 0:
        return HistoryHypothesis(
            available=False, path=path,
            reason=f"git log exit={result.returncode}: {result.stderr.strip()[:200]}",
        )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    last_commit_at = lines[0].split(" ", 1)[1] if lines else ""
    return HistoryHypothesis(
        available=True, path=path,
        commit_count=len(lines), last_commit_at=last_commit_at,
    )


def memory_hypothesis(store: LessonStore, tag: str) -> MemoryHypothesis:
    """Lessons already tagged with `tag` -- no new recall algorithm, the
    exact-tag index `LessonStore.search_by_tag` already provides this."""
    try:
        lessons = store.search_by_tag(tag)
    except OSError as exc:
        return MemoryHypothesis(
            available=False, tag=tag,
            reason=f"LessonStore ilegible: {type(exc).__name__}: {exc}",
        )
    return MemoryHypothesis(
        available=True, tag=tag,
        lesson_count=len(lessons),
        lesson_ids=tuple(lesson.id for lesson in lessons),
    )


def compose_hypotheses(
    location: FindingLocation,
    *,
    repo_root: Path,
    graph_db_path: Path,
    lesson_store: LessonStore,
) -> EngineeringHypothesisSet:
    """Compose the three hypotheses for one finding location. Each source
    fails independently -- a missing graph never hides an available
    history, and vice versa."""
    module = module_name_for_path(location.path)
    graph = (
        graph_hypothesis(module, db_path=graph_db_path)
        if module is not None
        else GraphHypothesis(available=False, reason="ruta fuera de src/atlas, sin módulo")
    )
    history = history_hypothesis(repo_root, location.path)
    tag = f"module:{module}" if module is not None else f"path:{location.path}"
    memory = memory_hypothesis(lesson_store, tag)
    return EngineeringHypothesisSet(
        location=location, graph=graph, history=history, memory=memory,
    )
