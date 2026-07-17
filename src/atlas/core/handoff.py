"""Atlas Core — `atlas handoff`: pack de sucesión GENERADO desde el sustrato.

T0 (plan de sucesión, memoria "SUCESIÓN DE MODELO"): el siguiente modelo que
opere Atlas no debe heredar un pack de handoff manual que se pudre con cada
sesión — debe poder regenerarlo en cualquier momento leyendo las fuentes
vigentes del repo (`WORK_LEDGER.md`, `AGENTS.md`, `docs/design/actor_roles.md`,
`docs/design/atlas_master_plan.md`) y del sustrato de memoria (registros
`harness:*` migrados por `scripts/migrate_harness_memory.py`, T0.2).

Fail-CERRADO: si una fuente no está disponible, la sección correspondiente
lleva el marcador literal `FUENTE NO DISPONIBLE: <cual>` — nunca omisión
silenciosa (el próximo modelo debe SABER qué le falta, no asumir que no
existía).

Determinismo: el sha256 de cada fichero en `MANIFEST.json["files"]` se
calcula SOLO sobre el cuerpo (sin la cabecera `GENERADO ... <timestamp>`),
para que dos llamadas seguidas sobre el mismo sustrato produzcan el mismo
hash aunque el timestamp de generación cambie — el timestamp vive solo en la
cabecera de cada fichero y en `MANIFEST.json["generated_at"]`, nunca en el
hash.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atlas.memory.memory_index import SqliteMemoryIndex

_HARNESS_PREFIX = "harness:"
# Marcador fijo que `scripts/migrate_harness_memory.py` incrusta literalmente
# al frente de cada memoria migrada — contrato compartido con Task 1.
_MIGRATION_TAG_RE = re.compile(r"^\[migrado de memoria-harness [^\]]+\]\s*")

_MD_FILENAMES = (
    "00_ESTADO.md",
    "01_QUIEN_ES_QUIEN.md",
    "02_INVARIANTES.md",
    "03_MEMORIA_CLAVE.md",
    "04_PLAN.md",
)


def _fuente_no_disponible(cual: str) -> str:
    return f"FUENTE NO DISPONIBLE: {cual}"


def _read_or_none(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def head_sha(repo_root: Path) -> str:
    """SHA completo de HEAD de `repo_root`; "unknown" si no es un repo git o
    git falla — nunca lanza (usado también por `atlas handoff --check`)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return "unknown"
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def extract_where_block(ledger_text: str) -> str | None:
    """Extrae de `ledger_text` el bloque desde `## WHERE` hasta la SEGUNDA
    entrada `- **` (exclusive): incluye la primera entrada completa (con sus
    líneas de continuación indentadas) y corta justo antes de la segunda. Si
    solo hay una entrada (o ninguna), corta en el siguiente header `## ` o al
    final del texto. None si no hay cabecera `## WHERE`."""
    lines = ledger_text.splitlines()
    where_idx = next((i for i, ln in enumerate(lines) if ln.strip() == "## WHERE"), None)
    if where_idx is None:
        return None
    entry_idxs = [i for i in range(where_idx + 1, len(lines)) if lines[i].startswith("- **")]
    if len(entry_idxs) >= 2:
        end_idx = entry_idxs[1]
    else:
        end_idx = next(
            (i for i in range(where_idx + 1, len(lines)) if lines[i].startswith("## ")),
            len(lines),
        )
    return "\n".join(lines[where_idx:end_idx]).rstrip("\n")


def estado_body(repo_root: Path) -> str:
    """Cuerpo de `00_ESTADO.md`: el bloque WHERE más reciente de
    `WORK_LEDGER.md`."""
    text = _read_or_none(repo_root / "WORK_LEDGER.md")
    if text is None:
        return _fuente_no_disponible("WORK_LEDGER.md")
    block = extract_where_block(text)
    if block is None:
        return _fuente_no_disponible("WORK_LEDGER.md (sin sección '## WHERE')")
    return block


def quien_es_quien_body(repo_root: Path) -> str:
    """Cuerpo de `01_QUIEN_ES_QUIEN.md`: `docs/design/actor_roles.md` íntegro."""
    text = _read_or_none(repo_root / "docs" / "design" / "actor_roles.md")
    return text if text is not None else _fuente_no_disponible("docs/design/actor_roles.md")


def invariantes_body(repo_root: Path) -> str:
    """Cuerpo de `02_INVARIANTES.md`: `AGENTS.md` íntegro."""
    text = _read_or_none(repo_root / "AGENTS.md")
    return text if text is not None else _fuente_no_disponible("AGENTS.md")


def plan_body(repo_root: Path) -> str:
    """Cuerpo de `04_PLAN.md`: `docs/design/atlas_master_plan.md` íntegro."""
    text = _read_or_none(repo_root / "docs" / "design" / "atlas_master_plan.md")
    return text if text is not None else _fuente_no_disponible("docs/design/atlas_master_plan.md")


def _description_of(text: str) -> str:
    """Primera línea del texto migrado, sin el marcador
    `[migrado de memoria-harness <fecha>] ` (formato fijo de Task 1)."""
    first_line = text.splitlines()[0] if text else ""
    return _MIGRATION_TAG_RE.sub("", first_line).strip()


def memoria_clave_body(index: SqliteMemoryIndex | None) -> str:
    """Cuerpo de `03_MEMORIA_CLAVE.md`: `name — description` de TODOS los
    registros `harness:*` vigentes del índice, orden alfabético.
    `record_type` no se persiste en el schema SQL (ver docstring de
    `SqliteMemoryIndex.upsert`), así que se enumera por prefijo de id
    (`ids_by_prefix`) en vez de filtrar por tipo."""
    if index is None:
        return _fuente_no_disponible("sustrato")
    ids = index.ids_by_prefix(_HARNESS_PREFIX)
    if not ids:
        return "(sin registros harness-memory en el sustrato)"
    lines = []
    for rid in ids:
        name = rid[len(_HARNESS_PREFIX) :]
        text = index.text_of(rid)
        description = _description_of(text) if text is not None else "(texto no disponible)"
        lines.append(f"- {name} — {description}")
    return "\n".join(lines)


def _cabecera(generated_at: str) -> str:
    return (
        f"<!-- GENERADO por atlas handoff {generated_at} — "
        "NO EDITAR A MANO; regenerar con: atlas handoff -->"
    )


def _compose(generated_at: str, body: str) -> str:
    return f"{_cabecera(generated_at)}\n\n{body}\n"


def generate_handoff(
    repo_root: Path, index: SqliteMemoryIndex | None, out_dir: Path
) -> dict[str, str]:
    """Genera el pack de sucesión en `out_dir` desde el sustrato vigente.

    Escribe 6 ficheros (los 5 `.md` con cabecera GENERADO + `MANIFEST.json`)
    y devuelve `{nombre_fichero_md: sha256_del_cuerpo}` — el mismo mapa que
    queda en `MANIFEST.json["files"]`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()

    bodies: dict[str, str] = {
        "00_ESTADO.md": estado_body(repo_root),
        "01_QUIEN_ES_QUIEN.md": quien_es_quien_body(repo_root),
        "02_INVARIANTES.md": invariantes_body(repo_root),
        "03_MEMORIA_CLAVE.md": memoria_clave_body(index),
        "04_PLAN.md": plan_body(repo_root),
    }

    files_sha: dict[str, str] = {}
    for name in _MD_FILENAMES:
        body = bodies[name]
        (out_dir / name).write_text(_compose(generated_at, body), encoding="utf-8")
        files_sha[name] = hashlib.sha256(body.encode("utf-8")).hexdigest()

    manifest = {
        "head_sha": head_sha(repo_root),
        "generated_at": generated_at,
        "files": files_sha,
    }
    (out_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return files_sha
