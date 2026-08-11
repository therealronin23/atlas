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


#: Peticiones al proveedor por defecto y por tirada, contadas en el código y no
#: estimadas a ojo (2026-08-11):
#:
#:   AtlasSolver     -> ToolCoder: 1 de planificación (tool_coder.py:399) más
#:                      hasta `max_iterations=3` vueltas del bucle (:680) = 4
#:   DirectModelSolver -> un `hub.infer` (fitness_solvers.py:314)          = 1
#:
#: Es la COTA SUPERIOR: si ToolCoder acierta en la primera vuelta gasta menos.
#: Para presupuestar hay que usar la cota, no la media — quedarse corto es
#: exactamente el fallo que este cálculo existe para evitar.
LLAMADAS_ATLAS = 4
LLAMADAS_DESNUDO = 1
LLAMADAS_POR_DEFECTO = LLAMADAS_ATLAS + LLAMADAS_DESNUDO

#: Presupuesto por defecto, en peticiones. Los tiers gratuitos de Groq y
#: OpenRouter conceden decenas al día (`requests per day`,
#: `free-models-per-day`), no cientos. 40 es conservador y cabe.
PRESUPUESTO_POR_DEFECTO = 40


def coste_estimado(defectos: int, repeats: int) -> int:
    """Peticiones al proveedor que va a costar esta configuración.

    Existe porque SONDEAR NO SIRVE. `cadena_no_responde()` gasta una petición y
    responde "¿puedo llamar?" cuando la pregunta es "¿puedo llamar 171 veces?".
    El 2026-08-11 dijo "disponible" minutos antes de que la cadena reventara
    con `requests per day`, y no mentía: medía otra cosa.

    Contra un límite POR NÚMERO DE PETICIONES, lo único que sirve es contarlas
    antes de gastarlas.
    """
    return defectos * repeats * LLAMADAS_POR_DEFECTO


def _libro_de_gasto(root: Path) -> Path:
    return root / "workspace" / "fitness" / "gasto.json"


def gasto_de_hoy(root: Path, *, hoy: str | None = None) -> int:
    """Peticiones que este banco ya gastó HOY, o 0 si el libro es de otro día.

    El presupuesto sabía lo que iba a costar la tirada y no lo que ya se había
    gastado, así que el 2026-08-11 dos tiradas de 40 pasaron la puerta por
    separado contra una cuota diaria que no daba para las dos. Contar el coste
    de una tirada no sirve si la cuota es diaria y el libro no existe.
    """
    import json
    from datetime import datetime, timezone

    hoy = hoy or datetime.now(timezone.utc).date().isoformat()
    libro = _libro_de_gasto(root)
    try:
        datos = json.loads(libro.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if not isinstance(datos, dict) or datos.get("fecha") != hoy:
        return 0
    try:
        return max(0, int(datos.get("peticiones", 0)))
    except (TypeError, ValueError):
        return 0


def registrar_gasto(root: Path, peticiones: int, *, hoy: str | None = None) -> int:
    """Acumula el gasto del día y devuelve el total. Se llama ANTES de gastar:
    una tirada que muere a medias ya consumió lo que consumió."""
    import json
    from datetime import datetime, timezone

    hoy = hoy or datetime.now(timezone.utc).date().isoformat()
    total = gasto_de_hoy(root, hoy=hoy) + max(0, peticiones)
    libro = _libro_de_gasto(root)
    libro.parent.mkdir(parents=True, exist_ok=True)
    libro.write_text(
        json.dumps({"fecha": hoy, "peticiones": total}, indent=2),
        encoding="utf-8",
    )
    return total


def dimensionar_al_presupuesto(defectos: int, presupuesto: int) -> tuple[int, int]:
    """Mayor (muestra, repeticiones) que cabe en `presupuesto` peticiones.

    Prioriza REPETICIONES sobre tamaño de muestra hasta un mínimo de 2: una
    sola tirada no es una medición (el mismo banco dio 2/3 y 0/3 con el mismo
    código el 2026-08-09), así que recortar por ahí produce un número que no
    distingue capacidad de suerte. Recortar la muestra sí es honesto mientras
    se publique cuántos defectos entraron.
    """
    for repeats in (3, 2):
        cabe = presupuesto // (repeats * LLAMADAS_POR_DEFECTO)
        if cabe >= 3:
            return min(cabe, defectos), repeats
    return 0, 0


def cadena_no_responde() -> str:
    """Motivo por el que la cadena no atiende AHORA, o cadena vacía si atiende.

    ANTES SE LLAMABA `cuota_agotada()`, y el nombre prometía lo que no puede
    dar. Es **estructuralmente incapaz** de detectar un límite por número de
    peticiones: gasta UNA y responde "¿puedo llamar?" cuando la pregunta es
    "¿puedo llamar 40 veces?". El 2026-08-11 pasó dos veces — dijo
    "disponible" y la tirada murió con `requests per day` y
    `free-models-per-day`. No mentía: medía otra cosa.

    Para límites por número de peticiones está `coste_estimado()` + el
    presupuesto DIARIO con su libro de gasto (`gasto_de_hoy`). Esta función
    cubre sólo el caso "la cadena no responde en absoluto", que es real y
    mucho más estrecho de lo que su nombre anterior sugería.

    Una petición mínima antes de gastar horas. El 2026-08-10 el banco corrió
    84 minutos para producir quince `hard timeout tras 300.0s` que en realidad
    eran `Rate limit reached ... on tokens per day (TPD)` — la cuota agotada
    por las propias tiradas de esa mañana. **Un banco que consume el recurso
    que mide tiene que comprobarlo antes de empezar**, o acaba publicando
    ceros que no miden nada.

    La sonda PESA lo que pesa el trabajo, y esto no es un detalle: un "ping" de
    ocho tokens pasaba la cuota alegremente mientras el turno real —23.000
    caracteres, tras un solo `read_file`— moría. Se sondea con el tamaño que el
    bucle necesita de verdad; si ese tamaño no entra hoy, el banco no puede
    medir hoy, y eso es justo lo que se quiere saber.

    Nunca bloquea por un fallo del propio sondeo: si la sonda no puede
    ejecutarse, se corre el banco igual y que hablen los datos.
    """
    try:
        from atlas.core.inference_hub import (
            InferenceHub,
            InferenceLevel,
            InferenceRequest,
        )

        # Medido el 2026-08-10: 12k caracteres pasaban en 7,2 s y 23k reventaban
        # la cadena entera. El turno que importa es el segundo, no el primero.
        relleno = ("# comprobación de capacidad del banco de fitness\n" * 460)[:24000]
        respuesta = InferenceHub(mode="auto").infer(
            InferenceRequest(
                prompt="Responde solo OK.\n" + relleno,
                level=InferenceLevel.L1, task_id="fitness_sonda",
                max_tokens=8, temperature=0.0, timeout_s=60.0,
            )
        )
    except Exception as exc:  # noqa: BLE001 — una sonda rota no cancela el pase
        print(f"  (sonda de cuota no pudo ejecutarse: {exc}; se continúa)")
        return ""
    if getattr(respuesta, "success", False):
        return ""
    fallos = getattr(respuesta, "chain_failures", ()) or ()
    limitados = [n for n, e in fallos if "RateLimit" in e or "rate limit" in e.lower()]
    if limitados:
        return f"{len(limitados)} de {len(fallos)} proveedores rate-limitados: " + ", ".join(
            limitados[:4]
        )
    return str(getattr(respuesta, "error", "") or "la cadena no responde")[:300]


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
    parser.add_argument(
        "--sin-sonda", dest="sin_sonda", action="store_true",
        help="salta la comprobación de cuota previa (por defecto se hace: el "
             "banco gasta el mismo recurso que mide y agotarlo produce ceros "
             "que parecen resultados).",
    )
    parser.add_argument(
        "--presupuesto", type=int, default=PRESUPUESTO_POR_DEFECTO,
        help=f"peticiones al proveedor que puede gastar esta tirada "
             f"(por defecto {PRESUPUESTO_POR_DEFECTO}). 0 = sin límite.",
    )
    parser.add_argument(
        "--auto-dimensionar", dest="auto", action="store_true",
        help="recorta muestra y repeticiones para caber en el presupuesto en "
             "vez de abortar.",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    corpus = root / "docs" / "fixtures" / "fitness" / "frozen_defects.jsonl"
    scorer = FitnessScorer(root, corpus, run_tests=run_tests)

    # PRESUPUESTO ANTES DE GASTAR. Medido el 2026-08-11: el corpus completo con
    # 3 tiradas pide ~171 peticiones y los tiers gratuitos conceden decenas al
    # día (`requests per day`, `free-models-per-day`). El banco NUNCA había sido
    # ejecutable así, y cada 0.0% publicado antes estaba midiendo la cuota en
    # vez de a Atlas. Contarlas antes es lo único que funciona contra un límite
    # por número de peticiones — sondear gasta una y no dice cuántas quedan.
    if args.presupuesto:
        en_corpus = len(
            [x for x in corpus.read_text(encoding="utf-8").splitlines() if x.strip()]
        )
        pedidos = args.limit or en_corpus
        coste = coste_estimado(pedidos, args.repeats)
        # El presupuesto es DIARIO, no por tirada. Sin descontar lo ya gastado,
        # dos tiradas de 40 pasan la puerta por separado contra una cuota que
        # no da para las dos — que es exactamente lo que pasó el 2026-08-11.
        gastado = gasto_de_hoy(root)
        disponible = max(0, args.presupuesto - gastado)
        if gastado:
            print(f"gasto de hoy: {gastado} peticiones ya consumidas por este "
                  f"banco; quedan {disponible} de {args.presupuesto}.", flush=True)
        if coste > disponible:
            cabe_muestra, cabe_repeats = dimensionar_al_presupuesto(
                en_corpus, disponible
            )
            args.presupuesto = disponible
            print(
                f"presupuesto: {pedidos} defectos x {args.repeats} tiradas "
                f"= ~{coste} peticiones, y el techo son {args.presupuesto}.",
                flush=True,
            )
            if not args.auto:
                if not cabe_muestra:
                    print(f"  Con {args.presupuesto} peticiones no cabe ninguna "
                          "configuración que sea una medición (mínimo 3 defectos "
                          "x 2 tiradas). Sube --presupuesto o consigue más cuota.")
                    return 2
                print(f"  Cabe: --limit {cabe_muestra} --repeats {cabe_repeats} "
                      f"(~{coste_estimado(cabe_muestra, cabe_repeats)} peticiones).")
                print("  Relanza con eso, o añade --auto-dimensionar. Correr el "
                      "corpus entero contra un tier gratuito NO produce una "
                      "medición: produce ceros de cuota.")
                return 2
            if not cabe_muestra:
                print("  ABORTA: ni con --auto-dimensionar cabe una medición.")
                return 2
            args.limit, args.repeats = cabe_muestra, cabe_repeats  # noqa: F841 — se reasigna abajo
            print(f"  auto-dimensionado a --limit {args.limit} "
                  f"--repeats {args.repeats}.", flush=True)

    # Se apunta ANTES de gastar: una tirada que muere a medias —como la del
    # 2026-08-11, que se comió la cuota y publicó nada— ya consumió lo que
    # consumió, y el libro tiene que reflejarlo para la siguiente.
    if args.presupuesto:
        en_corpus = len(
            [x for x in corpus.read_text(encoding="utf-8").splitlines() if x.strip()]
        )
        registrar_gasto(root, coste_estimado(args.limit or en_corpus, args.repeats))

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

    if not args.sin_sonda:
        motivo = cadena_no_responde()
        if motivo:
            print()
            print("ABORTA: los proveedores no pueden atender el banco ahora mismo.")
            print(f"  {motivo}")
            print("  Correr igualmente produciría 0/N en cada solver y ese cero")
            print("  NO mediría a Atlas. Pasó el 2026-08-10: 84 minutos y quince")
            print('  "hard timeout tras 300.0s" que en realidad eran la cuota')
            print("  diaria agotada por las tiradas de esa misma mañana.")
            print("  Reintenta cuando la cuota se renueve, o `--sin-sonda` para forzar.")
            return 2

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
