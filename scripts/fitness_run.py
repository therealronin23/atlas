"""Puntúa los dos solvers contra el banco congelado y publica la comparación.

Uso (las claves entran como DATOS, nunca con `source .env`):

    PYTHONPATH=src .venv/bin/python scripts/safe_dotenv.py .env -- \
        .venv/bin/python scripts/fitness_run.py --limit 3

La diferencia entre los dos números es el resultado: mide lo que aporta el
harness de Atlas frente a un modelo desnudo sobre el MISMO banco.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from atlas.core.self_maintenance.fitness import FitnessScorer  # noqa: E402
from atlas.core.self_maintenance.fitness_solvers import (  # noqa: E402
    AtlasSolver,
    DirectModelSolver,
)


def run_tests(worktree: Path, targets: tuple[str, ...]) -> int:
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "PYTHONPATH": str(worktree / "src"),
        "HOME": "/tmp",
        "ATLAS_NESTED_TEST_RUN": "1",
        "ATLAS_HOME": "/tmp/atlas-fitness-home",
    }
    try:
        return subprocess.run(
            [sys.executable, "-m", "pytest", *targets, "-q", "--tb=no",
             "-p", "no:cacheprovider", "-p", "no:randomly", "-x"],
            cwd=worktree, env=env, capture_output=True, text=True, timeout=300,
        ).returncode
    except subprocess.TimeoutExpired:
        return 124


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="0 = todos")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    corpus = root / "docs" / "fixtures" / "fitness" / "frozen_defects.jsonl"
    scorer = FitnessScorer(root, corpus, run_tests=run_tests)

    if args.limit:
        # Subconjunto reproducible: los N primeros del corpus, no una muestra
        # aleatoria — dos tiradas distintas tienen que ser comparables.
        recorte = root / "docs" / "fixtures" / "fitness" / f".subset-{args.limit}.jsonl"
        lineas = corpus.read_text(encoding="utf-8").splitlines()[: args.limit]
        recorte.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        scorer = FitnessScorer(root, recorte, run_tests=run_tests)

    total = len(scorer.defects())
    print(f"banco: {total} defectos verificados", flush=True)

    resultados = {}
    for nombre, solver in (
        ("baseline_sin_solver", None),
        ("atlas_toolcoder", AtlasSolver()),
        ("modelo_desnudo", DirectModelSolver()),
    ):
        t0 = time.monotonic()
        score = scorer.score(solve=solver)
        dt = time.monotonic() - t0
        resultados[nombre] = {**score.to_dict(), "seconds": round(dt, 1)}
        print(
            f"  {nombre:22s} {score.solved}/{score.total} = {score.ratio:.1%}"
            f"   ({dt / 60:.1f} min)",
            flush=True,
        )

    a = resultados["atlas_toolcoder"]["ratio"]
    d = resultados["modelo_desnudo"]["ratio"]
    print()
    print(f"APORTE DEL HARNESS: {a:.1%} (Atlas) - {d:.1%} (desnudo) = {a - d:+.1%}")
    if args.out:
        args.out.write_text(json.dumps(resultados, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
