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

# Entrypoints: 0 importadores estáticos es ESPERADO (se invocan por CLI/ASGI/etc.).
_ENTRYPOINT_HINTS = ("cli", "__main__", "__init__", "conftest", "app", "server", "asgi", "run")

_CLASSIFIED_ZERO_IMPORTERS = {
    "src/atlas/tools/_crawl4ai_worker.py": "KEEP subprocess entrypoint used by CrawlerTool in isolated venv",
    "src/atlas/core/lesson_runner.py": "PARK tested lesson workflow; no runtime owner in current slice",
    "src/atlas/core/incremental_coder.py": "PARK tested coding workflow; no runtime owner in current slice",
    "src/atlas/core/history_compactor.py": "PARK standalone context utility; caller-owned",
    "src/atlas/core/token_budget.py": "PARK standalone context utility; caller-owned",
    "src/atlas/immunity/live_loop.py": "PARK gated hook adapter; no hot-path owner enabled",
    "src/atlas/core/self_maintenance/root_cause_classifier.py": "KEEP injectable component used by ColdUpdateManager when configured",
    "src/atlas/core/self_maintenance/benchmark_gate.py": "KEEP injectable component used by ColdUpdateBatcher when configured",
    "src/atlas/core/self_maintenance/topic_expander.py": "PARK discovery helper; service-runner wiring not enabled",
    "src/atlas/core/self_maintenance/preflight_gate.py": "PARK preflight component; self-build service wiring not enabled",
    "src/atlas/core/self_maintenance/batch_premortem.py": "PARK batch gate; service-runner wiring not enabled",
    "src/atlas/core/self_maintenance/sota_snapshot.py": "PARK benchmark context recorder; no scheduler owner enabled",
    "src/atlas/core/self_maintenance/panorama_scout.py": "PARK discovery scout; no scheduler owner enabled",
    "src/atlas/core/self_maintenance/failure_lesson_sink.py": "KEEP injectable component used by ColdUpdateBatcher when configured",
    "src/atlas/core/self_maintenance/evolution_gate.py": "KEEP optional component used by SelfBuildRunner evolution path when configured",
}


def _modules() -> list[Path]:
    return [p for p in (ROOT / "src" / "atlas").rglob("*.py") if "__pycache__" not in p.parts]


def _py_corpus() -> dict[Path, str]:
    """Lee una sola vez todos los .py de src/ y scripts/ (no tests)."""
    corpus: dict[Path, str] = {}
    for base in (ROOT / "src", ROOT / "scripts"):
        for g in base.rglob("*.py"):
            if set(g.parts) & _SKIP_DIRS:
                continue
            try:
                corpus[g] = g.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
    return corpus


def vapor_audit() -> list[str]:
    out: list[str] = []
    corpus = _py_corpus()
    for f in _modules():
        mod = f.stem
        if mod in _ENTRYPOINT_HINTS:
            continue
        rel = str(f.relative_to(ROOT))
        if rel in _CLASSIFIED_ZERO_IMPORTERS:
            continue
        pat = rf"import .*\b{re.escape(mod)}\b|from .*\b{re.escape(mod)}\b import|\.{re.escape(mod)}\b"
        rx = re.compile(pat)
        if not any(g != f and rx.search(text) for g, text in corpus.items()):
            out.append(rel)
    return out


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
    print("\n(Radar read-only: decide KEEP/QUARANTINE/DELETE según REPO_STANDARD §3.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
