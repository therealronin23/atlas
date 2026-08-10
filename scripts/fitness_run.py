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
    OracleSolver,
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


def muestra_uniforme(lineas: list[str], n: int) -> list[str]:
    """N defectos repartidos por todo el corpus, conservando el orden.

    NO la cabeza. El corpus va del arreglo más reciente al más antiguo, y
    medido el 2026-08-10 los primeros son justo los más grandes: en `--limit 5`
    caían los dos de mayor parche (18.035 y 10.530 bytes) y el único con cinco
    ficheros de test. Un `[:N]` no es "un subconjunto", es "los N más
    difíciles", y publicar su resultado como el del banco subreporta por
    construcción.

    La zancada conserva lo que hacía falta —determinista, dos tiradas
    comparables— sin el sesgo. No es estable si el corpus crece, y por eso quien
    la usa imprime y guarda los ids: un número sin su muestra no se relee.
    """
    if n <= 0 or n >= len(lineas):
        return list(lineas)
    if n == 1:
        return [lineas[0]]
    paso = (len(lineas) - 1) / (n - 1)
    idx = sorted({round(i * paso) for i in range(n)})
    return [lineas[i] for i in idx]


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
        lineas = [x for x in corpus.read_text(encoding="utf-8").splitlines() if x.strip()]
        elegidas = muestra_uniforme(lineas, args.limit)
        recorte = (
            root / "docs" / "fixtures" / "fitness" / f".subset-{len(elegidas)}.jsonl"
        )
        recorte.write_text("\n".join(elegidas) + "\n", encoding="utf-8")
        scorer = FitnessScorer(root, recorte, run_tests=run_tests)

    defectos = scorer.defects()
    total = len(defectos)
    muestra = [d.id for d in defectos]
    print(f"banco: {total} defectos verificados", flush=True)
    if args.limit:
        print(f"  muestra (zancada uniforme): {', '.join(muestra)}", flush=True)

    # CONTROL, antes de cualquier solver. Medido el 2026-08-10: baseline y
    # atlas sacaron ambos 0/5, y un cero admite dos lecturas incompatibles —
    # "los solvers no pueden" o "el banco es imposible". El oráculo aplica el
    # arreglo real y elige entre las dos. Cuesta segundos y no gasta un token:
    # no hay razón para dejarlo detrás de un flag que nadie recordaría poner.
    techo = scorer.score(solve=OracleSolver(root, scorer.defects()))
    print(f"  {'CONTROL (arreglo real)':22s} {techo.solved}/{techo.total} "
          f"= techo del banco", flush=True)
    if techo.solved < techo.total:
        fallidos = [o["defect_id"] for o in techo.outcomes if not o["solved"]]
        print(f"  AVISO: {len(fallidos)} defecto(s) NO los resuelve ni su propio "
              f"arreglo: {', '.join(map(str, fallidos))}")
        print("  El banco está roto en esa parte; lee los números de abajo "
              f"contra {techo.solved}, no contra {techo.total}.")

    # UNA TIRADA NO ES UNA MEDICIÓN. Medido el 2026-08-09: el mismo banco, con
    # `AtlasSolver` sin tocar entre ejecuciones, dio 2/3 y luego 0/3. El solver
    # es estocástico (temperatura, enrutado de proveedor, cadena de fallback),
    # así que un número suelto no distingue capacidad de suerte.
    #
    # Aquí está además la corrección de un razonamiento propio: el 06-ago se
    # descartó PACE (arXiv:2606.08106) por "varianza que una suite determinista
    # no tiene". Cierto de la PUERTA (pytest pasa o no pasa), FALSO de la
    # MÉTRICA. Los tests secuenciales anytime-valid pertenecen aquí.
    resultados: dict[str, dict[str, object]] = {
        "_muestra": {
            "defect_ids": muestra,
            "total_corpus": len(
                [x for x in corpus.read_text(encoding="utf-8").splitlines() if x.strip()]
            ),
            "seleccion": "zancada uniforme" if args.limit else "corpus completo",
            "techo_control": {"solved": techo.solved, "total": techo.total},
        }
    }
    for nombre, hacer_solver in (
        ("baseline_sin_solver", lambda: None),
        ("atlas_toolcoder", AtlasSolver),
        ("modelo_desnudo", DirectModelSolver),
    ):
        tiradas: list[float] = []
        resueltos: list[int] = []
        intentos: list[dict[str, object]] = []
        t0 = time.monotonic()
        for i in range(args.repeats):
            solver = hacer_solver()
            score = scorer.score(solve=solver)
            tiradas.append(score.ratio)
            resueltos.append(score.solved)
            intentos.extend(a.to_dict() for a in getattr(solver, "attempts", []))
            if args.repeats > 1:
                print(f"    {nombre:20s} tirada {i + 1}/{args.repeats}: "
                      f"{score.solved}/{score.total}", flush=True)
        dt = time.monotonic() - t0
        media = sum(tiradas) / len(tiradas)
        resultados[nombre] = {
            "ratios": tiradas, "solved": resueltos, "mean": round(media, 4),
            "min": min(tiradas), "max": max(tiradas),
            "repeats": args.repeats, "seconds": round(dt, 1),
            "attempts": intentos,
        }
        # Un cero sin causa no es accionable. Se agrupan las razones para
        # separar "no supo" de "no llegó a contestar" o "el comando no existía":
        # tres diagnósticos con tres arreglos distintos.
        causas: dict[str, int] = {}
        for intento in intentos:
            if not intento["ok"]:
                causas[str(intento["detail"])[:60] or "(sin detalle)"] = (
                    causas.get(str(intento["detail"])[:60] or "(sin detalle)", 0) + 1
                )
        for causa, veces in sorted(causas.items(), key=lambda kv: -kv[1])[:4]:
            print(f"      x{veces}  {causa}", flush=True)
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
