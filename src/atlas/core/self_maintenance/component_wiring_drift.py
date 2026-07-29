"""Detector de deriva component_reality_matrix.jsonl↔grafo real (2026-07-30).

El 2026-07-29 se encontraron 8 filas donde `component_reality_matrix.jsonl`
afirmaba "no WIRED" mientras el grafo estructural (AST real, no grep)
mostraba importadores reales — nadie las había contrastado desde que se
escribieron (`fabric/policy.py` etc., importados por `orchestrator.py`,
llevaban meses marcados como huérfanos). Mismo principio que
``ecosystem_drift.py``: determinista, barato, nunca LLM/red, la lógica vive
aquí en TDD real; ``sanitation_audit.py`` sólo importa y envuelve
fail-open.

Dos direcciones de deriva, simétricas — el canon puede mentir en cualquiera:
- SOBRECLAMADO: ``statuses`` incluye ``WIRED`` pero NINGÚN fichero de
  ``code`` tiene importadores reales.
- SUBCLAMADO: ``statuses`` NO incluye ``WIRED`` pero TODOS los ficheros de
  ``code`` sí tienen importadores reales (el bug real de ayer).

Deliberadamente SIN veredicto para filas MIXTAS (algún fichero con
importadores, otro sin ellos): un componente puede nombrar específicamente
el papel del fichero SIN importadores — "Event Kernel projection" sobre
``core_bridge.py`` + ``store.py`` es justo ese caso: sólo ``core_bridge.py``
es la "proyección" que el nombre describe, aunque ``store.py`` esté muy
usado por otras once cosas. Forzar un veredicto ahí exigiría entender qué
nombra el componente, algo que este detector no sabe — sería exactamente el
tipo de afirmación no verificada que existe para atrapar."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _module_name(rel_path: str) -> str | None:
    """``src/atlas/fabric/policy.py`` -> ``atlas.fabric.policy``. ``None``
    para cualquier cosa que no sea código Python bajo ``src/`` (config,
    docs citados en ``code`` por error, etc.) — no es lo que este detector
    sabe verificar contra el grafo de imports."""
    if not rel_path.startswith("src/") or not rel_path.endswith(".py"):
        return None
    return rel_path[len("src/"):-len(".py")].replace("/", ".")


def _default_importers_of(repo_root: Path, db_path: Path | None) -> Callable[[str], list[str]]:
    """Consulta el grafo real vía ``build_graph_server`` a su PROPIA última
    SHA ingerida (``graph_freshness``, que nunca lanza), no contra HEAD: el
    daemon poll cada 3600s, así que exigir FRESH dejaría este detector mudo
    la mayor parte del tiempo. El coste es mirar el árbol tal como estaba en
    esa SHA, no el actual — aceptable para un radar, no para una puerta."""
    from atlas.mcp.graph_server import build_graph_server
    from atlas.memory.project_graph import DEFAULT_GRAPH_DB, graph_freshness

    path = db_path or DEFAULT_GRAPH_DB
    state = graph_freshness(path, repo_root=repo_root)
    sha = state.get("graph_commit_sha") or ""
    server = build_graph_server(path, repo_root=repo_root)
    tools = {t.name: t for t in server._tool_manager.list_tools()}  # noqa: SLF001
    graph_importers = tools["graph_importers"]

    def _query(module: str) -> list[str]:
        result: Any = graph_importers.fn(module=module, commit_sha=sha)
        return list(result)

    return _query


def component_wiring_drift(
    repo_root: Path,
    *,
    matrix_path: Path | None = None,
    importers_of: Callable[[str], list[str]] | None = None,
    db_path: Path | None = None,
) -> list[str]:
    """Filas de ``component_reality_matrix.jsonl`` cuya afirmación de
    ``WIRED`` en ``statuses`` contradice al grafo real. Fail-honesto: si el
    doc no existe, o una línea no parsea, o el grafo no responde para un
    fichero (STALE, DB ausente…), esa fila/fichero se trata como
    desconocido y NUNCA se fuerza un hallazgo desde una señal ausente —
    nunca lanza."""
    path = matrix_path or (repo_root / "docs" / "canon" / "component_reality_matrix.jsonl")
    if not path.is_file():
        return []

    query = importers_of or _default_importers_of(repo_root, db_path)

    findings: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue

        modules = [
            (raw, mod) for raw in row.get("code", []) if (mod := _module_name(raw)) is not None
        ]
        if not modules:
            continue

        wired_count = 0
        known_count = 0
        for _raw, mod in modules:
            try:
                importers = query(mod)
            except Exception:  # noqa: BLE001 — un fichero desconocido no invalida el resto
                continue
            known_count += 1
            if importers:
                wired_count += 1
        if known_count == 0 or known_count != len(modules):
            # Alguno de los ficheros no dio señal fiable: mixto por
            # incertidumbre, no por naming — igual de silencioso que un
            # mixto real, mismo motivo (no forzar veredicto sin evidencia
            # completa).
            continue

        claims_wired = "WIRED" in row.get("statuses", [])
        all_wired = wired_count == len(modules)
        none_wired = wired_count == 0
        row_id = row.get("id", "?")
        row_name = row.get("name", "?")

        if claims_wired and none_wired:
            findings.append(
                f"{row_id} ({row_name}): statuses incluye WIRED pero 0 importadores "
                f"reales en {[m[0] for m in modules]}"
            )
        elif not claims_wired and all_wired:
            # No asumir CODE_PRESENT/TESTED en el mensaje: filas como "Memory
            # OS" tenían statuses=[PROPOSED_DESIGN] —ni siquiera CODE_PRESENT—
            # con importadores reales igualmente. Citar los statuses TAL
            # CUAL evita que el propio mensaje del detector sobreafirme.
            findings.append(
                f"{row_id} ({row_name}): statuses={row.get('statuses', [])} pero "
                f"TODOS sus ficheros ({[m[0] for m in modules]}) tienen importadores "
                f"reales — falta WIRED"
            )
        # Mixto real (0 < wired_count < len(modules)): silencioso a propósito.

    return findings
