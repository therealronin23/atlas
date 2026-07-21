#!/usr/bin/env python3
"""Índice máquina de docs/ — generador + validador (REPO_STANDARD §1).

El orden de docs/ no puede ser prosa que se pudre: `docs/INDEX.yaml` declara
cada documento con `type` (qué es), `status` (vigente/propuesto/superseded/
historico) y `verified` (última fecha en que alguien contrastó sus afirmaciones
con la realidad). Este script lo mantiene honesto:

    python3 scripts/docs_index_audit.py            # valida (radar, exit 0)
    python3 scripts/docs_index_audit.py --strict   # valida (exit 1 si desviación)
    python3 scripts/docs_index_audit.py --write    # (re)genera preservando los
                                                   # campos curados a mano
                                                   # (status/verified/notes)

Reglas del validador:
  1. Doc en el árbol sin entrada en el índice → FALTA (nuevo sin clasificar).
  2. Entrada en el índice sin doc en el árbol → HUÉRFANA (movido/borrado sin
     actualizar el índice).
  3. `status: vigente` con `verified` a más de VERIFY_MAX_DAYS → CADUCADO
     (afirma estado sin contraste reciente; re-verificar o degradar).

Exclusiones: `docs/inbox/` (aún sin triage), `docs/self_audit_*` (estado
runtime, gitignorado), `__pycache__`, ficheros no documentales (.pyc, etc.).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
INDEX_NAME = "INDEX.yaml"
VERIFY_MAX_DAYS = 90

# type por directorio de primer nivel bajo docs/ (taxonomía REPO_STANDARD §1).
_TYPE_BY_DIR = {
    "decisions": "decision",
    "design": "design",
    "operations": "operacion",
    "governance": "norma",
    "audits": "evidencia",
    "compliance": "compliance",
    "membrana": "compliance",
    "outreach": "difusion",
    "knowledge": "conocimiento",
    "skills": "conocimiento",
    "superpowers": "design",
    "demo": "difusion",
    "archive": "historia",
    "architecture": "design",
    "canon": "canon",
    "roadmap": "plan",
}

_DOC_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".txt", ".html", ".bib", ".bbl", ".py"}


def _is_indexable(path: Path, docs_dir: Path) -> bool:
    rel = path.relative_to(docs_dir)
    parts = rel.parts
    if not parts:
        return False
    if parts[0] == "inbox":
        return False
    if "__pycache__" in parts:
        return False
    if rel.name == INDEX_NAME:
        return False
    if rel.name.startswith("self_audit_"):
        return False  # estado runtime, gitignorado
    return path.suffix.lower() in _DOC_SUFFIXES


def _infer_type(rel: Path) -> str:
    top = rel.parts[0] if rel.parts else ""
    return _TYPE_BY_DIR.get(top, "conocimiento")


def _infer_status(rel: Path) -> str:
    if not rel.parts:
        return "propuesto"
    if rel.parts[0] == "archive":
        return "historico"
    # docs/handoff = packs de sucesión: snapshots congelados (historia).
    # GENERATED es el handoff regenerable actual, pero una regeneración no le
    # concede autoridad por sí misma: entra como propuesta hasta verificación.
    if rel.parts[0] == "handoff" and (len(rel.parts) < 2 or rel.parts[1] != "GENERATED"):
        return "historico"
    return "propuesto"


def scan_tree(docs_dir: Path | None = None) -> list[Path]:
    docs_dir = docs_dir or (ROOT / "docs")
    return sorted(
        p.relative_to(docs_dir.parent)
        for p in docs_dir.rglob("*")
        if p.is_file() and _is_indexable(p, docs_dir)
    )


def load_index(docs_dir: Path | None = None) -> dict[str, dict]:
    docs_dir = docs_dir or (ROOT / "docs")
    index_path = docs_dir / INDEX_NAME
    if not index_path.is_file():
        return {}
    raw = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    return {e["path"]: e for e in raw.get("entries", [])}


def write_index(docs_dir: Path | None = None) -> int:
    """(Re)genera INDEX.yaml. Preserva status/verified/notes curados a mano de
    las entradas que siguen existiendo; las nuevas entran con defaults."""
    docs_dir = docs_dir or (ROOT / "docs")
    existing = load_index(docs_dir)
    entries = []
    for rel in scan_tree(docs_dir):
        key = str(rel)
        prev = existing.get(key, {})
        inferred_status = _infer_status(rel.relative_to("docs"))
        prev_status = prev.get("status")
        # Migración de defaults: 'vigente' era el default histórico del
        # generador — si la taxonomía ahora infiere 'historico', el default
        # cede. Los status curados a mano (propuesto/superseded/…) se
        # conservan SIEMPRE (contrato del header).
        if prev_status in (None, "vigente") and inferred_status == "historico":
            status = inferred_status
        else:
            status = prev_status if prev_status is not None else inferred_status
        entry = {
            "path": key,
            "type": prev.get("type", _infer_type(rel.relative_to("docs"))),
            "status": status,
            "verified": prev.get("verified"),
        }
        if prev.get("notes"):
            entry["notes"] = prev["notes"]
        entries.append(entry)
    payload = {
        "generated": date.today().isoformat(),
        "entries": entries,
    }
    header = (
        "# Índice MÁQUINA de docs/ — no editar el layout a mano sin razón.\n"
        "# Generado/validado por scripts/docs_index_audit.py (REPO_STANDARD §1).\n"
        "# Campos curados a mano que --write PRESERVA: type, status, verified, notes.\n"
        "# status: vigente | propuesto | superseded | historico\n"
    )
    (docs_dir / INDEX_NAME).write_text(
        header + yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return len(entries)


def validate(docs_dir: Path | None = None, *, today: date | None = None) -> dict[str, list[str]]:
    docs_dir = docs_dir or (ROOT / "docs")
    today = today or date.today()
    tree = {str(p) for p in scan_tree(docs_dir)}
    index = load_index(docs_dir)

    missing = sorted(tree - set(index))
    orphans = sorted(set(index) - tree)
    expired: list[str] = []
    unverified: list[str] = []
    for key, entry in index.items():
        if entry.get("status") != "vigente" or key not in tree:
            continue
        verified = entry.get("verified")
        if verified is None:
            unverified.append(key)
            continue
        try:
            vdate = date.fromisoformat(str(verified))
        except ValueError:
            expired.append(f"{key} (verified ilegible: {verified!r})")
            continue
        if (today - vdate).days > VERIFY_MAX_DAYS:
            expired.append(f"{key} (verified {verified}, >{VERIFY_MAX_DAYS}d)")
    return {"missing": missing, "orphans": orphans, "expired": expired, "unverified": sorted(unverified)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="(re)genera el índice")
    parser.add_argument("--strict", action="store_true", help="exit 1 si hay faltas, huérfanas o caducadas")
    parser.add_argument("--require-verified", action="store_true", help="incluye vigentes nunca verificadas como fallo")
    args = parser.parse_args()

    if args.write:
        n = write_index()
        print(f"INDEX.yaml regenerado: {n} entradas")
        return 0

    report = validate()
    print(f"# Auditoría del índice de docs — {datetime.now():%Y-%m-%d}")
    for section, title in (
        ("missing", "Docs SIN entrada en el índice (clasificar o triage)"),
        ("orphans", "Entradas HUÉRFANAS (doc movido/borrado; actualizar índice)"),
        ("expired", "Vigentes con verificación CADUCADA (re-verificar o degradar)"),
        ("unverified", "Vigentes NUNCA verificadas (deuda visible; --require-verified para fallar)"),
    ):
        items = report[section]
        print(f"\n## {title}")
        if items:
            for item in items:
                print(f"  - {item}")
        else:
            print("  ✓ ninguna")
    blocking = any(report[key] for key in ("missing", "orphans", "expired"))
    if args.require_verified and report["unverified"]:
        blocking = True
    return 1 if (args.strict and blocking) else 0


if __name__ == "__main__":
    sys.exit(main())
