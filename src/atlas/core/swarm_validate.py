"""
Capa 3 — Validación barata de worktree (ADR-045/046).

`worktree_validate` es la función `validate` que inyecta `SwarmCycle` en cada
`WorktreeWorker`. Es BARATA a propósito: solo comprueba que el diff APLICA y
que los .py tocados PARSEAN. La suite completa vive en `ColdUpdateManager.validate`
(gate del decider, aguas abajo, hoy OFF). Correrla aquí violaría la regla
asimétrica (verificador más barato que productor) y sería el cuello de botella
de cadencia.

Sin red, sin pytest, sin ValidationRunner.
"""

from __future__ import annotations

import ast
import re
import subprocess
import tempfile
from pathlib import Path

from atlas.core.git_env import clean_git_env
from atlas.core.verify import Check, CostTier, Evidence, Verdict

# Extrae paths del lado b/ de las cabeceras +++ de un diff unificado.
_PlusPlus = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)


def _touched_py_paths(diff: str) -> list[str]:
    """Paths Python tocados por el diff (cabeceras '+++ b/<path>')."""
    return [p for p in _PlusPlus.findall(diff) if p.endswith(".py")]


def worktree_validate(path: Path, diff: str) -> Evidence:
    """Valida que el diff APLICA y que los .py resultantes PARSEAN.

    Parámetros
    ----------
    path:
        Directorio raíz del worktree (donde correr `git apply`).
    diff:
        Diff unificado a validar (producido por el DeterministicProducer o LLM).

    Devuelve
    --------
    Evidence con verdict PASS si aplica y parsea; FAIL en cualquier otro caso.
    La lógica es fail-fast: el primer problema para.
    """
    if not diff.strip():
        return Evidence(
            verdict=Verdict.FAIL,
            reason="diff vacío",
            verifier_ids=("worktree_validate",),
        )

    # Escribe el diff a un fichero temporal y corre git apply --check.
    patch_fd, patch_name = tempfile.mkstemp(suffix=".patch")
    patch_path = Path(patch_name)
    try:
        patch_path.write_text(diff, encoding="utf-8")

        # Fase 1: comprobar que aplica (sin modificar el árbol).
        check_result = subprocess.run(
            ["git", "apply", "--check", str(patch_path)],
            cwd=path,
            env=clean_git_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        if check_result.returncode != 0:
            reason = (check_result.stderr or check_result.stdout).strip()[:300]
            return Evidence(
                verdict=Verdict.FAIL,
                reason=reason or "git apply --check falló",
                verifier_ids=("worktree_validate",),
            )

        # Fase 2: aplicar de verdad (sobre el worktree desechable).
        apply_result = subprocess.run(
            ["git", "apply", str(patch_path)],
            cwd=path,
            env=clean_git_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        if apply_result.returncode != 0:
            reason = (apply_result.stderr or apply_result.stdout).strip()[:300]
            return Evidence(
                verdict=Verdict.FAIL,
                reason=reason or "git apply falló",
                verifier_ids=("worktree_validate",),
            )

        # Fase 3: AST parse de cada .py tocado.
        for rel_path in _touched_py_paths(diff):
            file_path = path / rel_path
            if not file_path.exists():
                continue  # fichero nuevo aun no existe (patch lo creará; ok)
            try:
                source = file_path.read_text(encoding="utf-8", errors="replace")
                ast.parse(source)
            except SyntaxError as exc:
                return Evidence(
                    verdict=Verdict.FAIL,
                    reason=f"rompe AST: {rel_path}: {exc}",
                    verifier_ids=("worktree_validate",),
                )

    finally:
        patch_path.unlink(missing_ok=True)

    return Evidence(
        verdict=Verdict.PASS,
        checks=(
            Check("git_apply", True, cost=CostTier.STATIC),
            Check("ast_parse", True, cost=CostTier.SHAPE),
        ),
        total_cost=CostTier.SHAPE,
        verifier_ids=("worktree_validate",),
        reason="aplica y parsea",
    )
