"""Cosecha de la suite congelada de defectos — verdad-terreno para el fitness.

El lazo de autoconstrucción tiene RESTRICCIONES ("pytest pasa", "mypy limpio")
pero ninguna FUNCIÓN DE FITNESS, y por eso rinde 7,8% end-to-end (13 aplicados
de 167 propuestos en 71 días) frente al 35-50% de aceptación de PRs reales del
campo. DGM (arXiv:2505.22954, ICLR 2026) señala la validación empírica sobre un
benchmark como el ingrediente habilitante: *probar que un cambio es netamente
beneficioso es imposible en la práctica*, así que hay que medirlo. Sin métrica
que subir, un lazo sólo puede no-empeorar.

Este módulo construye ese benchmark desde el historial propio, con el método de
SWE-bench:

    base = padre(commit_de_arreglo)
    se aplica SÓLO la parte de `tests/` del diff del arreglo
    el test debe FALLAR ahí          -> hay un defecto reproducible
    con el arreglo entero debe PASAR -> el defecto es el que se cree

**La propiedad que lo hace no-hackeable**: se guarda el estado del defecto y el
parche de TESTS, nunca el diff del arreglo. La respuesta no vive en el repo, así
que el lazo no puede leerla — sólo resolverla. Es la diferencia entre medir
capacidad y medir memoria, y es justo lo que falla en el 19,78% de los casos
"resueltos" de SWE-bench que en realidad hackean el harness.

La ejecución (¿falla en base? ¿pasa con el arreglo?) NO está aquí: la hace
`EngineeringReproductionRunner`, que ya corre un target pytest acotado desde un
commit inmutable en un worktree efímero de solo lectura dentro del jail sin red.
Aquí sólo se selecciona y se serializa.

Uso:  python -m atlas.core.self_maintenance.frozen_defects --limit 20
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from atlas.core.git_env import clean_git_env

__all__ = [
    "FrozenDefect",
    "build_candidate",
    "candidate_commits",
    "split_test_patch",
    "write_defects",
]

_GIT_TIMEOUT_S = 60
#: `fix(scope): asunto` — el scope da el subsistema, para no cosechar veinte
#: defectos del mismo rincón y creer que se mide el sistema entero.
_SCOPE_RE = re.compile(r"^fix\(([^)]+)\)")
DEFAULT_OUTPUT = Path("docs") / "fixtures" / "fitness" / "frozen_defects.jsonl"


@dataclass(frozen=True)
class FrozenDefect:
    """Un defecto reproducible. `test_patch` toca sólo `tests/`."""

    id: str
    fix_sha: str
    base_sha: str
    subject: str
    subsystem: str
    test_files: tuple[str, ...] = ()
    test_patch: str = field(default="", repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "fix_sha": self.fix_sha,
            "base_sha": self.base_sha,
            "subject": self.subject,
            "subsystem": self.subsystem,
            "test_files": list(self.test_files),
            "test_patch": self.test_patch,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FrozenDefect:
        return cls(
            id=str(data["id"]),
            fix_sha=str(data["fix_sha"]),
            base_sha=str(data["base_sha"]),
            subject=str(data.get("subject", "")),
            subsystem=str(data.get("subsystem", "")),
            test_files=tuple(data.get("test_files", ())),
            test_patch=str(data.get("test_patch", "")),
        )


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        env=clean_git_env(),
        capture_output=True,
        text=True,
        check=False,
        timeout=_GIT_TIMEOUT_S,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def candidate_commits(
    repo_root: Path, *, ref: str = "HEAD", limit: int | None = None
) -> list[str]:
    """Commits `fix(` que tocan a la vez `tests/` y `src/`.

    Las dos condiciones son necesarias y por motivos distintos: sin cambio en
    `src/` no hay defecto de código que resolver, y sin test no hay forma de
    demostrar que se resolvió. Un `fix(` que sólo toca docs o config no mide
    capacidad de ingeniería.
    """
    if limit is not None and limit <= 0:
        return []
    shas = _git(repo_root, "log", "--format=%H", "--grep=^fix(", ref).split()
    out: list[str] = []
    for sha in shas:
        files = _git(
            repo_root, "show", "--name-only", "--format=", "--diff-filter=AM", sha
        ).split()
        has_test = any(f.startswith("tests/") and f.endswith(".py") for f in files)
        has_src = any(f.startswith("src/") and f.endswith(".py") for f in files)
        if has_test and has_src:
            out.append(sha)
            if limit is not None and len(out) >= limit:
                break
    return out


def split_test_patch(repo_root: Path, fix_sha: str) -> str:
    """Diff del arreglo restringido a `tests/`.

    El pathspec se lo come git, no un filtro posterior sobre el texto: recortar
    un diff a mano es como se filtran por accidente hunks del arreglo, y un
    solo hunk filtrado convierte la métrica en un examen con las respuestas
    detrás.
    """
    return _git(
        repo_root, "diff", f"{fix_sha}^", fix_sha, "--", "tests/"
    )


def build_candidate(repo_root: Path, fix_sha: str) -> FrozenDefect | None:
    """Construye el defecto, o None si el commit no sirve como tal."""
    parent = _git(repo_root, "rev-parse", f"{fix_sha}^").strip()
    if not parent:
        # Commit raíz: no hay estado "antes del defecto" que congelar.
        return None
    subject = _git(repo_root, "log", "-1", "--format=%s", fix_sha).strip()
    test_files = tuple(
        f
        for f in _git(
            repo_root, "show", "--name-only", "--format=", "--diff-filter=AM", fix_sha
        ).split()
        if f.startswith("tests/") and f.endswith(".py")
    )
    if not test_files:
        return None
    patch = split_test_patch(repo_root, fix_sha)
    if not patch.strip():
        return None
    scope = _SCOPE_RE.match(subject)
    return FrozenDefect(
        # Estable entre cosechas: mismo commit, mismo id. Sin esto, recosechar
        # renombraría todos los defectos y se perdería la serie histórica.
        id=hashlib.sha256(fix_sha.encode()).hexdigest()[:12],
        fix_sha=fix_sha,
        base_sha=parent,
        subject=subject,
        subsystem=scope.group(1) if scope else "",
        test_files=test_files,
        test_patch=patch,
    )


def write_defects(defects: Iterable[FrozenDefect], path: Path) -> int:
    """Escribe la suite como JSONL. SOBREESCRIBE a propósito.

    Append-only aquí sería un error: la suite es un CONJUNTO, y recosechar
    duplicaría defectos inflando el denominador del score — el lazo parecería
    empeorar sin haber cambiado nada.
    """
    rows = list(defects)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for defect in rows:
            handle.write(json.dumps(defect.to_dict(), sort_keys=True) + "\n")
    return len(rows)


def harvest(
    repo_root: Path, *, limit: int | None = None, ref: str = "HEAD"
) -> list[FrozenDefect]:
    """Cosecha candidatos. NO verifica que fallen en base — eso exige ejecución
    y lo hace el scorer sobre `EngineeringReproductionRunner`."""
    out: list[FrozenDefect] = []
    for sha in candidate_commits(repo_root, ref=ref, limit=None):
        defect = build_candidate(repo_root, sha)
        if defect is None:
            continue
        out.append(defect)
        if limit is not None and len(out) >= limit:
            break
    return out


def _main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    defects = harvest(args.repo_root, limit=args.limit)
    out = args.out or (args.repo_root / DEFAULT_OUTPUT)
    written = write_defects(defects, out)
    print(f"{written} defectos candidatos -> {out}")
    for defect in defects:
        print(f"  {defect.id}  [{defect.subsystem or '?':14s}] {defect.subject[:64]}")
    print("\nCandidatos SIN verificar: falta comprobar que cada test falla en su base.")
    return 0


if __name__ == "__main__":  # pragma: no cover — entrypoint
    raise SystemExit(_main())
