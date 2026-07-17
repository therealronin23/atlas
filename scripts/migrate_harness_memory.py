#!/usr/bin/env python3
"""Migración de memorias del harness (Claude Code, ~/.claude/projects/.../memory)
al sustrato de memoria propio de Atlas (SqliteMemoryIndex + MemoryTrunk).

T0.2 del plan de sucesión (docs/plan de sucesión, memoria "SUCESIÓN DE MODELO"):
cuando el driver conversacional (Claude Code / Fable) no esté, la inteligencia
debe vivir en el sustrato, no en un harness propietario. Este script lee las
memorias .md del harness (frontmatter `name`/`description`/`metadata.type`),
las particiona por tipo y las escribe en el índice propio con procedencia —
EXCEPTO las de tipo `user` (dato personal del operador), que se quedan en el
harness a propósito (no se migran, se reportan como "queda en harness").

También soporta `--extra-doc` (repetible) para ingerir un doc .md arbitrario
íntegro como doctrina (`record_type="doctrine"`), sin parsear frontmatter —
lo necesita la Task 3 del mismo plan.

Dry-run por defecto: sin `--apply` solo IMPRIME el reporte, no toca ningún
fichero ni base de datos (default honesto — evita escribir sobre la BD de
producción por accidente).

Uso:
    python scripts/migrate_harness_memory.py                    # dry-run
    python scripts/migrate_harness_memory.py --apply             # escribe en ~/atlas-mcp/memory.db
    python scripts/migrate_harness_memory.py --apply \\
        --extra-doc docs/design/algo.md --extra-doc docs/otro.md
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TypedDict

from atlas.mcp.memory_server import build_gated_index
from atlas.mcp.memory_trunk import MemoryTrunk
from atlas.memory.memory_index import SqliteMemoryIndex

# Se incrusta literalmente en el texto migrado — contrato fijo con el plan T0
# (.superpowers/sdd/task-1-brief.md): "[migrado de memoria-harness 2026-07-16] ...".
_MIGRATION_TAG = "2026-07-16"

# metadata.type -> memory_class. `user` NO está aquí a propósito: se gestiona
# aparte (nunca se migra, ver `_plan`).
_FACTUAL_TYPES = {"project", "reference"}
_PERSONAL_TYPES = {"feedback"}
_NOT_MIGRATED_TYPE = "user"


class MigrationReport(TypedDict):
    migrated: int
    skipped_user: int
    errors: list[str]


class _PlanItem:
    """Una memoria del harness ya clasificada, lista para escribir. Separado de
    la escritura para que el dry-run pueda calcular el reporte sin tocar disco."""

    __slots__ = ("record_id", "text", "memory_class")

    def __init__(self, record_id: str, text: str, memory_class: str) -> None:
        self.record_id = record_id
        self.text = text
        self.memory_class = memory_class


def _default_memory_dir() -> Path:
    """Deriva el dir de memoria del harness con la convención real de Claude
    Code (~/.claude/projects/<cwd-con-guiones>/memory), a partir de la raíz del
    repo (padre de scripts/) — no del cwd real del proceso — para que el
    default sea estable venga como venga invocado el script."""
    repo_root = Path(__file__).resolve().parent.parent
    sanitized = str(repo_root).replace("/", "-")
    return Path.home() / ".claude" / "projects" / sanitized / "memory"


def _default_db_path() -> Path:
    return Path.home() / "atlas-mcp" / "memory.db"


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Parsea el frontmatter YAML-lite de una memoria del harness SIN depender
    de una lib YAML nueva (PyYAML ya está en el repo, pero el formato real es
    fijo y simple: claves top-level `name`/`description` + un bloque
    `metadata:` con `type` anidado 2 espacios — ver memoria real en
    ~/.claude/projects/.../memory/*.md). Devuelve (campos, cuerpo íntegro)."""
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("frontmatter ausente: el fichero no empieza con '---'")
    try:
        end = lines[1:].index("---") + 1
    except ValueError as exc:
        raise ValueError("frontmatter sin '---' de cierre") from exc

    fields: dict[str, str] = {}
    in_metadata = False
    for line in lines[1:end]:
        if not line.strip():
            continue
        if line[0].isspace():
            # Línea anidada bajo `metadata:` — solo nos interesa `type`
            # (node_type/originSessionId no son relevantes para la migración).
            if not in_metadata:
                continue
            key, sep, value = line.strip().partition(":")
            if sep and key.strip() == "type":
                fields["type"] = value.strip().strip("\"'")
            continue
        in_metadata = False
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip()
        if key == "metadata":
            in_metadata = True
            continue
        fields[key] = value.strip().strip("\"'")

    body = "\n".join(lines[end + 1 :]).strip("\n")
    return fields, body


def _plan(memory_dir: Path) -> tuple[list[_PlanItem], int, list[str]]:
    """Clasifica cada memoria .md de `memory_dir` SIN escribir nada — la usan
    tanto `migrate` (que sí escribe) como el dry-run del CLI (que no). Un dir
    inexistente simplemente no produce ficheros (glob no lanza). Devuelve
    (items a migrar, nº de `user` saltadas, errores no fatales)."""
    items: list[_PlanItem] = []
    skipped_user = 0
    errors: list[str] = []
    for path in sorted(memory_dir.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
            fields, body = _parse_frontmatter(content)
        except (OSError, ValueError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue

        name = fields.get("name")
        description = fields.get("description")
        mem_type = fields.get("type")
        if not name or not description or not mem_type:
            errors.append(f"{path.name}: frontmatter incompleto (falta name/description/metadata.type)")
            continue

        if mem_type == _NOT_MIGRATED_TYPE:
            skipped_user += 1
            continue
        if mem_type in _FACTUAL_TYPES:
            memory_class = "factual"
        elif mem_type in _PERSONAL_TYPES:
            memory_class = "personal"
        else:
            errors.append(f"{path.name}: metadata.type desconocido {mem_type!r}, no migrado")
            continue

        text = f"[migrado de memoria-harness {_MIGRATION_TAG}] {description}\n\n{body}"
        items.append(_PlanItem(f"harness:{name}", text, memory_class))
    return items, skipped_user, errors


def migrate(memory_dir: Path, index: SqliteMemoryIndex) -> MigrationReport:
    """Migra las memorias `project`/`reference`/`feedback` de `memory_dir` al
    índice propio. Las `user` se saltan a propósito (dato personal, queda en
    harness). Idempotente: dos llamadas seguidas no duplican — `MemoryTrunk.add`
    hace upsert por `record_id` (ver `SqliteMemoryIndex.upsert`)."""
    trunk = MemoryTrunk(index)
    items, skipped_user, errors = _plan(memory_dir)
    for item in items:
        trunk.add(
            item.text,
            record_id=item.record_id,
            record_type="harness-memory",
            memory_class=item.memory_class,
        )
    return {"migrated": len(items), "skipped_user": skipped_user, "errors": errors}


def migrate_extra_doc(doc_path: Path, index: SqliteMemoryIndex) -> str:
    """Ingiere `doc_path` ÍNTEGRO (sin parsear frontmatter) como doctrina.
    Idempotente por el mismo motivo que `migrate` (upsert por record_id)."""
    trunk = MemoryTrunk(index)
    text = doc_path.read_text(encoding="utf-8")
    record_id = f"doctrine:{doc_path.stem}"
    trunk.add(text, record_id=record_id, record_type="doctrine")
    return record_id


def _print_report(
    memory_dir: Path, report: MigrationReport, extra_docs: list[Path], *, applied: bool
) -> None:
    mode = "APLICADO" if applied else "DRY-RUN (usa --apply para escribir de verdad)"
    print(f"[migrate_harness_memory] {mode}")
    print(f"  memory_dir: {memory_dir}")
    print(
        f"  migrated={report['migrated']} skipped_user={report['skipped_user']} "
        f"errors={len(report['errors'])}"
    )
    for err in report["errors"]:
        print(f"    ! {err}")
    for doc in extra_docs:
        print(f"  extra-doc: {doc} -> doctrine:{doc.stem}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--memory-dir", type=Path, default=_default_memory_dir(), help="Dir de memorias del harness (.md)."
    )
    parser.add_argument("--db", type=Path, default=_default_db_path(), help="Ruta del sustrato SQLite propio.")
    parser.add_argument(
        "--apply", action="store_true", help="Escribe de verdad; sin este flag solo imprime el reporte (dry-run)."
    )
    parser.add_argument(
        "--extra-doc",
        type=Path,
        action="append",
        default=[],
        dest="extra_docs",
        metavar="PATH",
        help="Doc .md arbitrario a ingerir íntegro como doctrina (repetible).",
    )
    args = parser.parse_args(argv)

    memory_dir: Path = args.memory_dir
    extra_docs: list[Path] = list(args.extra_docs)

    if not args.apply:
        items, skipped_user, errors = _plan(memory_dir)
        report: MigrationReport = {"migrated": len(items), "skipped_user": skipped_user, "errors": errors}
        _print_report(memory_dir, report, extra_docs, applied=False)
        return 0

    index = build_gated_index(args.db)
    try:
        report = migrate(memory_dir, index)
        for doc in extra_docs:
            migrate_extra_doc(doc, index)
        _print_report(memory_dir, report, extra_docs, applied=True)
    finally:
        index.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
