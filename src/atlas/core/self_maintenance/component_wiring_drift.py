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

from atlas.core.graphs import QUERIES
from atlas.mcp.graph_server import _rows as _kuzu_rows
from atlas.memory.kuzu_runtime import open_kuzu_database


def _module_name(rel_path: str) -> str | None:
    """``src/atlas/fabric/policy.py`` -> ``atlas.fabric.policy``. ``None``
    para cualquier cosa que no sea código Python bajo ``src/`` (config,
    docs citados en ``code`` por error, etc.) — no es lo que este detector
    sabe verificar contra el grafo de imports."""
    if not rel_path.startswith("src/") or not rel_path.endswith(".py"):
        return None
    return rel_path[len("src/"):-len(".py")].replace("/", ".")


def _default_importers_of(repo_root: Path, db_path: Path | None) -> Callable[[str], list[str]]:
    """Consulta el grafo real a su PROPIA última SHA ingerida
    (``graph_freshness``, que nunca lanza), no contra HEAD: el daemon poll
    cada 3600s, así que exigir FRESH dejaría este detector mudo la mayor
    parte del tiempo. El coste es mirar el árbol tal como estaba en esa SHA,
    no el actual — aceptable para un radar, no para una puerta.

    2026-07-31: UNA conexión Kuzu para TODO el pase, no una por módulo.
    ``build_graph_server._query`` reabre la BD en cada llamada A PROPÓSITO
    (otro proceso regenera el grafo mientras el server MCP sigue vivo,
    ``build_graph_server.__doc__``) -- ese motivo no aplica a
    ``component_wiring_drift``: es un pase de lectura acotado de un solo
    proceso, así que reabrir por módulo era puro coste (medido: la suite
    completa pasó de ~370s a 467-564s por esto). El closure devuelto lleva
    un método ``close()`` que ``component_wiring_drift`` llama al terminar
    el pase; los ``importers_of`` inyectados en tests no lo tienen, y
    ``component_wiring_drift`` lo comprueba con ``hasattr`` antes de usarlo."""
    from atlas.memory.project_graph import DEFAULT_GRAPH_DB, graph_freshness

    path = db_path or DEFAULT_GRAPH_DB
    state = graph_freshness(path, repo_root=repo_root)
    sha = state.get("graph_commit_sha") or ""

    import kuzu

    db = open_kuzu_database(path, read_only=True)
    conn = kuzu.Connection(db)

    def _query(module: str) -> list[str]:
        result: Any = conn.execute(
            QUERIES["direct_importers"], parameters={"path": module, "sha": sha}
        )
        return [row[0] for row in _kuzu_rows(result)]

    def _close() -> None:
        conn.close()
        db.close()

    _query.close = _close  # type: ignore[attr-defined]
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

    try:
        findings = _scan_matrix(path, query)
    finally:
        # Solo el closure del path por-defecto lleva `.close` (ver
        # `_default_importers_of`); un `importers_of` inyectado por un test
        # no gestiona ninguna conexión y no lo necesita.
        close = getattr(query, "close", None)
        if close is not None:
            close()
    return findings


def _scan_matrix(path: Path, query: Callable[[str], list[str]]) -> list[str]:
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
