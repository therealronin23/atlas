#!/usr/bin/env python3
"""Auditoría de saneamiento — el motor del CICLO (read-only, no borra ni mueve).

Reporta candidatos para el ciclo de saneamiento (REPO_STANDARD.md §3). NO actúa:
el humano/agente decide KEEP/QUARANTINE/DELETE. Correr cada ciclo (p.ej. al cerrar
un Gate, o mensual):

    python3 scripts/sanitation_audit.py

Comprueba:
  1. VAPOR DE SISTEMA — módulos src/atlas con 0 importadores no-test (excluye
     entrypoints). Candidatos a "cablear o cuarentena" (regla wire-before-claim).
  2. MÓDULOS CLASIFICADOS — módulos con 0 importadores estáticos pero dueño
     explícito: subprocess, componente inyectable, utilidad standalone o PARK.
  3. CUARENTENA VENCIDA — carpetas en docs/archive/_graveyard/ más viejas que el
     grace; candidatas a `git rm` si nadie las rescató.
  4. CARPETAS VACÍAS.
  5. REFERENCIAS STALE — rutas docs/...md citadas en ficheros clave que ya no existen.

Salida = informe; código de salida 0 siempre (es un radar, no una puerta).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

_SKIP_DIRS = {".git", ".venv", ".venv-redteam", "__pycache__", "node_modules", ".mypy_cache",
              ".pytest_cache", ".ruff_cache", "_graveyard"}

ROOT = Path(__file__).resolve().parent.parent
GRACE_DAYS = 30  # una cuarentena sobrevive >=1 ciclo; pasado el grace, candidata a git rm

# Módulos SIN caller de producción pero con dueño/estado explícito.
#
# 2026-07-31 (F0.2): esta tabla ADELGAZÓ de 17 a 9 entradas. Ocho existían sólo
# para tapar puntos ciegos del escáner viejo, y el resolutor AST las resuelve
# solo — verificadas una a una por grep antes de retirarlas:
#   - live_loop, benchmark_gate, evolution_gate, panorama_scout, topic_expander,
#     incremental, gmail: imports DIFERIDOS dentro de funciones
#     (`maintenance_facade`, `orchestrator.py:1563`, `fabric/testing.py:50`).
#     `ast.walk` los ve; el escáner "a nivel de módulo" no.
#   - impacted_tests: caller real `python -m atlas.engineering.impacted_tests`
#     en `.githooks/pre-commit:79`, ahora detectado por el pase de comandos.
# Una entrada aquí ya NO debería compensar al detector: si hace falta, es señal
# de que el detector tiene un hueco que hay que arreglar en `dormant_modules`.
_CLASSIFIED_ZERO_IMPORTERS = {
    "src/atlas/tools/_crawl4ai_worker.py": "KEEP subprocess entrypoint used by CrawlerTool in isolated venv",
    "src/atlas/core/lesson_runner.py": "PARK tested lesson workflow; no runtime owner in current slice",
    "src/atlas/core/incremental_coder.py": "PARK tested coding workflow; no runtime owner in current slice",
    "src/atlas/core/history_compactor.py": "PARK standalone context utility; caller-owned",
    "src/atlas/core/token_budget.py": "PARK standalone context utility; caller-owned",
    "src/atlas/core/self_maintenance/sota_snapshot.py": "PARK benchmark context recorder; no scheduler owner enabled",
    "src/atlas/business/legacy.py": "PARK Business Core Fase 15 (LegacyLinkLayer); draft-first, sin flujo real que lo consuma todavia",
    "src/atlas/events/core_bridge.py": "PARK ADR-058 (CoreEventBridge proyecta EventBus->OsEvent canon); nada vivo lo suscribe hoy, Mission Layer/Radar leen el bus real directamente",
    "src/atlas/security/node_identity.py": "KEEP by design (backlog t6-node-identity-module, done): standalone crypto module, sin segundo nodo real (Hermes VPS de baja) que lo consuma todavia -- documentado explicitamente como standalone en el propio item",
}


def vapor_audit() -> list[str]:
    """Módulos sin un solo caller de producción. Resolución REAL de imports
    (AST), delegada a `atlas.core.self_maintenance.dormant_modules` — como
    `ecosystem_drift` y `component_wiring_drift`, la lógica vive en `src/`
    con TDD real y aquí sólo se envuelve fail-open.

    2026-07-31 (F0.2): antes esto era la heurística de texto
    `import .*\\bmod\\b|from .*\\bmod\\b import|\\.mod\\b`. Su tercera rama
    convertía cualquier mención textual del stem —un `self.reproduction`, una
    cadena `"diagnostics"`, un comentario— en un "importador". Falso
    NEGATIVO, el sentido peligroso: el radar callaba. Medido: no veía
    `engineering/reproduction.py` (489 loc) ni `engineering/diagnostics.py`
    (391 loc), los dos módulos dormidos más grandes del repo, porque esas
    palabras aparecen como texto en `logging/merkle_logger.py:109` y
    `core/doctor.py`. Reportaba 2 dormidos donde había 16."""
    try:
        from atlas.core.self_maintenance.dormant_modules import dormant_modules

        return dormant_modules(ROOT, classified=_CLASSIFIED_ZERO_IMPORTERS)
    except Exception as exc:  # noqa: BLE001 — radar opcional, nunca bloquea
        return [f"dormant_modules no pudo ejecutarse: {exc}"]


def classified_zero_importers() -> list[str]:
    """Módulos sin importador estático pero con estado/owner explícito."""
    return [
        f"{path} — {reason}"
        for path, reason in sorted(_CLASSIFIED_ZERO_IMPORTERS.items())
        if (ROOT / path).is_file()
    ]


def graveyard_overdue() -> list[str]:
    gy = ROOT / "docs" / "archive" / "_graveyard"
    if not gy.is_dir():
        return []
    out: list[str] = []
    for d in sorted(gy.iterdir()):
        if not d.is_dir():
            continue
        m = re.search(r"(\d{4}-\d{2}-\d{2})", d.name)
        if not m:
            continue
        age = (date.today() - datetime.strptime(m.group(1), "%Y-%m-%d").date()).days
        flag = "  ⏰ VENCIDA (revisar rescatar/git rm)" if age >= GRACE_DAYS else f"  ({age}d, en grace)"
        out.append(f"{d.relative_to(ROOT)}{flag}")
    return out


def empty_dirs() -> list[str]:
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        if not dirnames and not filenames:
            out.append(str(Path(dirpath).relative_to(ROOT)))
    return out


def stale_refs() -> list[str]:
    key = ["README.md", "AGENTS.md", "ROADMAP.md", "CHANGELOG.md", "WORK_LEDGER.md"]
    out: list[str] = []
    for name in key:
        f = ROOT / name
        if not f.is_file():
            continue
        for ref in re.findall(r"docs/[A-Za-z0-9_./-]+\.(?:md|tex|pdf|bib)", f.read_text(encoding="utf-8", errors="ignore")):
            if not (ROOT / ref).exists():
                out.append(f"{name} → {ref} (no existe)")
    return out


def docs_index_drift() -> list[str]:
    """Desviaciones árbol↔INDEX.yaml (REPO_STANDARD §1). Delegado al validador
    de scripts/docs_index_audit.py; fail-open a informe de error, nunca rompe
    el radar."""
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "docs_index_audit", ROOT / "scripts" / "docs_index_audit.py"
        )
        if spec is None or spec.loader is None:
            raise ImportError("no se pudo cargar docs_index_audit.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        report = module.validate()
        out: list[str] = []
        out += [f"SIN entrada en índice: {p}" for p in report["missing"]]
        out += [f"entrada HUÉRFANA: {p}" for p in report["orphans"]]
        out += [f"verificación CADUCADA: {p}" for p in report["expired"]]
        return out
    except Exception as exc:  # noqa: BLE001 — radar opcional, nunca bloquea
        return [f"docs_index_audit no pudo ejecutarse: {exc}"]


def docs_graph_drift() -> list[str]:
    """Enlaces rotos + huérfanos del grafo de docs (scripts/docs_graph.py).
    Fail-open a informe de error, nunca rompe el radar."""
    try:
        import importlib.util
        import sys as _sys

        spec = importlib.util.spec_from_file_location(
            "docs_graph", ROOT / "scripts" / "docs_graph.py"
        )
        if spec is None or spec.loader is None:
            raise ImportError("no se pudo cargar docs_graph.py")
        module = importlib.util.module_from_spec(spec)
        _sys.modules["docs_graph"] = module  # dataclasses exigen registro
        spec.loader.exec_module(module)
        return list(module.graph_drift())
    except Exception as exc:  # noqa: BLE001 — radar opcional, nunca bloquea
        return [f"docs_graph no pudo ejecutarse: {exc}"]


def ecosystem_map_drift() -> list[str]:
    """ADRs reales sin fila (ni individual ni por rango) en
    docs/design/atlas_ecosystem_map.md — spec B+C §5. Lógica real vive en
    atlas.core.self_maintenance.ecosystem_drift (TDD real, no un script
    suelto); fail-open aquí, nunca rompe el radar."""
    try:
        from atlas.core.self_maintenance.ecosystem_drift import ecosystem_map_drift as _impl

        return _impl(ROOT)
    except Exception as exc:  # noqa: BLE001 — radar opcional, nunca bloquea
        return [f"ecosystem_drift no pudo ejecutarse: {exc}"]


def component_wiring_drift() -> list[str]:
    """Filas de docs/canon/component_reality_matrix.jsonl cuya afirmación
    de WIRED contradice al grafo real (AST, no grep). El 2026-07-29 se
    encontraron 8 filas desfasadas así, sin corregir desde que se
    escribieron. Lógica real vive en
    atlas.core.self_maintenance.component_wiring_drift (TDD real, no un
    script suelto); fail-open aquí, nunca rompe el radar."""
    try:
        from atlas.core.self_maintenance.component_wiring_drift import (
            component_wiring_drift as _impl,
        )

        return _impl(ROOT)
    except Exception as exc:  # noqa: BLE001 — radar opcional, nunca bloquea
        return [f"component_wiring_drift no pudo ejecutarse: {exc}"]


def _section(title: str, items: list[str], ok: str) -> None:
    print(f"\n## {title}")
    if not items:
        print(f"  ✓ {ok}")
    else:
        for it in items:
            print(f"  - {it}")


def main() -> int:
    print("# Auditoría de saneamiento —", date.today().isoformat())
    try:
        rev = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
        print(f"HEAD: {rev}")
    except Exception:
        pass
    _section("Vapor de sistema (0 importadores no-test → cablear o cuarentena)",
             vapor_audit(), "ningún módulo huérfano")
    _section("Módulos 0-importer clasificados", classified_zero_importers(),
             "ningún módulo clasificado")
    _section(f"Cuarentena (grace {GRACE_DAYS}d)", graveyard_overdue(), "graveyard vacío")
    _section("Carpetas vacías", empty_dirs(), "ninguna")
    _section("Referencias docs/ stale en ficheros clave", stale_refs(), "ninguna")
    _section("Índice de docs (árbol↔INDEX.yaml)", docs_index_drift(), "sin desviaciones")
    _section("Grafo de docs (enlaces rotos + huérfanos)", docs_graph_drift(), "sin señales")
    _section("Mapa del ecosistema (ADR↔fila, spec B+C §5)", ecosystem_map_drift(),
             "todo ADR tiene fila o rango que lo cubre")
    _section("Matriz de componentes↔grafo real (WIRED verificado)", component_wiring_drift(),
             "ninguna fila de component_reality_matrix.jsonl contradice al grafo")
    print("\n(Radar read-only: decide KEEP/QUARANTINE/DELETE según REPO_STANDARD §3.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
