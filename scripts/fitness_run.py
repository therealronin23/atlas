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
    parser.add_argument(
        "--repeats", type=int, default=3,
        help="tiradas por solver. Una sola NO es una medición: el solver es "
             "estocástico y el mismo banco dio 2/3 y 0/3 en dos ejecuciones.",
    )
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

    # UNA TIRADA NO ES UNA MEDICIÓN. Medido el 2026-08-09: el mismo banco, con
    # `AtlasSolver` sin tocar entre ejecuciones, dio 2/3 y luego 0/3. El solver
    # es estocástico (temperatura, enrutado de proveedor, cadena de fallback),
    # así que un número suelto no distingue capacidad de suerte.
    #
    # Aquí está además la corrección de un razonamiento propio: el 06-ago se
    # descartó PACE (arXiv:2606.08106) por "varianza que una suite determinista
    # no tiene". Cierto de la PUERTA (pytest pasa o no pasa), FALSO de la
    # MÉTRICA. Los tests secuenciales anytime-valid pertenecen aquí.
    resultados: dict[str, dict[str, object]] = {}
    for nombre, hacer_solver in (
        ("baseline_sin_solver", lambda: None),
        ("atlas_toolcoder", AtlasSolver),
        ("modelo_desnudo", DirectModelSolver),
    ):
        tiradas: list[float] = []
        resueltos: list[int] = []
        t0 = time.monotonic()
        for i in range(args.repeats):
            score = scorer.score(solve=hacer_solver())
            tiradas.append(score.ratio)
            resueltos.append(score.solved)
            if args.repeats > 1:
                print(f"    {nombre:20s} tirada {i + 1}/{args.repeats}: "
                      f"{score.solved}/{score.total}", flush=True)
        dt = time.monotonic() - t0
        media = sum(tiradas) / len(tiradas)
        resultados[nombre] = {
            "ratios": tiradas, "solved": resueltos, "mean": round(media, 4),
            "min": min(tiradas), "max": max(tiradas),
            "repeats": args.repeats, "seconds": round(dt, 1),
        }
        dispersion = (
            f"  [min {min(tiradas):.0%} · max {max(tiradas):.0%}]"
            if args.repeats > 1 else ""
        )
        print(f"  {nombre:22s} media {media:.1%}{dispersion}   ({dt / 60:.1f} min)",
              flush=True)

    a = float(resultados["atlas_toolcoder"]["mean"])  # type: ignore[arg-type]
    d = float(resultados["modelo_desnudo"]["mean"])  # type: ignore[arg-type]
    print()
    print(f"APORTE DEL HARNESS: {a:.1%} (Atlas) - {d:.1%} (desnudo) = {a - d:+.1%}")
    if args.repeats < 3:
        print("  AVISO: con menos de 3 tiradas esta diferencia NO es una medición.")
    else:
        solape = (
            float(resultados["atlas_toolcoder"]["min"])  # type: ignore[arg-type]
            <= float(resultados["modelo_desnudo"]["max"])  # type: ignore[arg-type]
        )
        if solape:
            print("  AVISO: los rangos SE SOLAPAN — la diferencia no es concluyente.")
    if args.out:
        args.out.write_text(json.dumps(resultados, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
