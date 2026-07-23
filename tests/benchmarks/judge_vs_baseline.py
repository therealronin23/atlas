"""
tests/benchmarks/judge_vs_baseline.py — paso 2 de f2-6b (docs/backlog.yaml:
f2-6b-2-judge-vs-baseline-runner): evalúa un clasificador LLM (juez, en
producción InferenceHub nivel L1) contra un baseline determinista (regla por
keywords) sobre los pares factual/personal generados por el paso 1
(tests/benchmarks/gen_judge_pairs.py), emitiendo accuracy total y por clase
para ambos.

Diseño:
    `evaluate(pairs, judge, baseline)` es puro respecto a CÓMO se clasifica:
    `judge` y `baseline` son callables `str -> "factual"|"personal"`
    inyectables. En tests, `judge` es un fake con respuestas fijadas (CERO
    red). En producción, `make_inference_hub_judge(hub)` envuelve un
    InferenceHub real (nivel L1, prompt de clasificación de una palabra).

    `baseline_classify` es la regla determinista real (no un fake): dos bancos
    de keywords fijos (factual/personal), con precedencia "personal primero"
    — un texto que menciona cualquier palabra del banco personal se clasifica
    "personal" incluso si también contiene keywords factuales (falso-positivo
    conocido y deliberado: sirve para que el paso 3 mida si el juez LLM
    realmente mejora sobre esta regla ingenua, no solo sobre una tautología).

Uso CLI:
    python -m tests.benchmarks.judge_vs_baseline --pairs pairs.json --out results.json

    El judge de la CLI envuelve un InferenceHub real vía
    make_inference_hub_judge(). Para forzar modo sin red (tests/CI), usar la
    variable de entorno ya soportada por InferenceHub: ATLAS_INFERENCE_MODE=stub.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

from atlas.core.inference_hub import InferenceHub, InferenceLevel, InferenceRequest
from tests.benchmarks.gen_judge_pairs import Pair

# ---------------------------------------------------------------------------
# Baseline determinista por keywords
# ---------------------------------------------------------------------------

# Keywords que delatan una preferencia/manía/decisión del operador (no
# verificable como hecho del mundo). Tomadas del banco léxico real de
# gen_judge_pairs._PERSONAL_SUBJECTS/_PERSONAL_PREDICATES + sinónimos comunes.
_PERSONAL_KEYWORDS: tuple[str, ...] = (
    "operador",
    "usuario",
    "prefiere",
    "manía",
    "mania",
    "insiste",
    "evita",
    "molesta",
    "quiere que",
    "emojis",
    "commits",
    "delegue",
    "cure",
    "investigue",
    "verifique",
    "generalice",
    "hable",
    "marque",
    "worktree",
    "sonnet",
    "haiku",
    "opus",
    "claude",
)

# Keywords que delatan un hecho verificable sobre software/infra (versión,
# comportamiento de una API, benchmark). Tomadas del banco léxico real de
# gen_judge_pairs._FACTUAL_SUBJECTS/_FACTUAL_PREDICATES.
_FACTUAL_KEYWORDS: tuple[str, ...] = (
    "versión",
    "version",
    "librería",
    "libreria",
    "api",
    "excepción",
    "excepcion",
    "runtime",
    "benchmark",
    "latencia",
    " ms",
    "ram",
    " mb",
    "flag",
    "parámetro",
    "parametro",
    "variable de entorno",
    "compilador",
    "driver",
    "índice",
    "indice",
    "modelo",
    "kubernetes",
    "redis",
    "postgres",
    "yaml",
    "stripe",
    "node",
    "mypy",
    "requests",
)


def baseline_classify(text: str) -> str:
    """Regla determinista: "personal" si aparece cualquier keyword del banco
    personal (precedencia — ver docstring del módulo), si no "factual" si
    aparece cualquier keyword del banco factual, si no "factual" por defecto
    (empate cero-cero: no hay señal, se prefiere no sobre-etiquetar como
    personal)."""
    lowered = text.lower()
    if any(keyword in lowered for keyword in _PERSONAL_KEYWORDS):
        return "personal"
    if any(keyword in lowered for keyword in _FACTUAL_KEYWORDS):
        return "factual"
    return "factual"


# ---------------------------------------------------------------------------
# Judge de producción: envuelve InferenceHub (nivel L1)
# ---------------------------------------------------------------------------

_CLASSIFICATION_PROMPT_TEMPLATE = (
    "Clasifica el siguiente texto en EXACTAMENTE una de dos categorías: "
    "'factual' (un hecho verificable sobre el mundo, independiente de quién lo "
    "reporta: versiones de librerías, comportamiento de una API, resultado de "
    "un benchmark, un bug y su causa raíz) o 'personal' (una preferencia, "
    "manía o decisión del operador/usuario que no es verificable como hecho "
    "del mundo: gustos, hábitos de trabajo, cómo quiere que se le hable).\n\n"
    "Texto: {text}\n\n"
    "Responde con una única palabra, sin explicación: factual o personal."
)


def make_inference_hub_judge(
    hub: InferenceHub, level: InferenceLevel = InferenceLevel.L1
) -> Callable[[str], str]:
    """Envuelve un InferenceHub real como judge(text) -> "factual"|"personal".

    Construye un InferenceRequest de clasificación de una sola palabra
    (max_tokens bajo, temperature=0.0 para respuesta estable), llama a
    hub.infer_for_role("chat", ...) en el nivel pedido (L1 por defecto: barato,
    rate-limit gratis) y parsea la primera etiqueta reconocida en el texto de
    respuesta.

    Degradación: si el proveedor no devuelve ninguna de las dos palabras
    esperadas (fallo de formato, o modo stub sin red — ver ATLAS_INFERENCE_MODE
    en InferenceHub), o devuelve ambas, se resuelve por la que aparece primero
    en el texto; si no aparece ninguna, se degrada a "factual" — decisión
    explícita: un fallo de parseo no debe reventar el runner, y "factual" es
    el fallback más seguro para HITL (preferible no perder una lección
    factual antes que etiquetar de más como personal).
    """

    def judge(text: str) -> str:
        request = InferenceRequest(
            prompt=_CLASSIFICATION_PROMPT_TEMPLATE.format(text=text),
            level=level,
            max_tokens=8,
            temperature=0.0,
        )
        response = hub.infer_for_role("chat", request)
        lowered = response.text.lower()
        has_personal = "personal" in lowered
        has_factual = "factual" in lowered
        if has_personal and not has_factual:
            return "personal"
        if has_factual and not has_personal:
            return "factual"
        if has_personal and has_factual:
            return "personal" if lowered.index("personal") < lowered.index("factual") else "factual"
        return "factual"

    return judge


# ---------------------------------------------------------------------------
# Evaluación: accuracy total + por clase, para judge y baseline
# ---------------------------------------------------------------------------

class ClassifierScore(TypedDict):
    accuracy: float
    by_class: dict[str, float]


class EvaluationResult(TypedDict):
    n: int
    judge: ClassifierScore
    baseline: ClassifierScore


def _score(correct_by_class: dict[str, int], total_by_class: dict[str, int], n: int) -> ClassifierScore:
    total_correct = sum(correct_by_class.values())
    return {
        "accuracy": (total_correct / n) if n else 0.0,
        "by_class": {
            label: (correct_by_class.get(label, 0) / total_by_class[label])
            for label in total_by_class
        },
    }


def evaluate(
    pairs: list[Pair],
    judge: Callable[[str], str],
    baseline: Callable[[str], str],
) -> EvaluationResult:
    """Evalúa `judge` y `baseline` sobre `pairs`, devolviendo accuracy total y
    por clase para ambos.

    Args:
        pairs: pares {"text", "label"} de verdad-fundamental (paso 1).
        judge: callable text -> "factual"|"personal" (fake en tests, wrapper
            de InferenceHub en producción — ver make_inference_hub_judge).
        baseline: callable text -> "factual"|"personal" (baseline_classify en
            producción y en tests).

    Returns:
        {"n": int, "judge": {"accuracy": float, "by_class": {label: float}},
         "baseline": {...}}. Con pairs vacío, accuracy=0.0 y by_class={} (sin
        división por cero).
    """
    n = len(pairs)
    judge_correct: dict[str, int] = {}
    judge_total: dict[str, int] = {}
    baseline_correct: dict[str, int] = {}
    baseline_total: dict[str, int] = {}

    for pair in pairs:
        text = pair["text"]
        label = pair["label"]

        judge_total[label] = judge_total.get(label, 0) + 1
        baseline_total[label] = baseline_total.get(label, 0) + 1

        if judge(text) == label:
            judge_correct[label] = judge_correct.get(label, 0) + 1
        if baseline(text) == label:
            baseline_correct[label] = baseline_correct.get(label, 0) + 1

    return {
        "n": n,
        "judge": _score(judge_correct, judge_total, n),
        "baseline": _score(baseline_correct, baseline_total, n),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evalúa un juez LLM (InferenceHub nivel L1) vs baseline determinista "
            "por keywords sobre los pares de f2-6b paso 1."
        )
    )
    parser.add_argument("--pairs", type=str, required=True, help="ruta al JSON de pares (salida del paso 1)")
    parser.add_argument("--out", type=str, required=True, help="ruta de salida del JSON de resultados")
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    pairs_path = Path(args.pairs)
    pairs: list[Pair] = json.loads(pairs_path.read_text(encoding="utf-8"))

    hub = InferenceHub(mode="auto")
    judge = make_inference_hub_judge(hub)

    results = evaluate(pairs, judge, baseline_classify)

    out_path = Path(args.out)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
