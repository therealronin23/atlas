"""
tests/benchmarks/gen_judge_pairs.py — paso 1 de f2-6b (docs/backlog.yaml:
f2-6b-1-gen-judge-pairs): generador determinista de pares (texto, etiqueta)
sintéticos que sirven de verdad-fundamental para el paso 2 (juez LLM vs
baseline determinista).

Etiquetas:
    "factual"  — una lección/hecho verificable sobre el mundo, independiente
                 de quién lo reporta (versiones de librerías, comportamiento de
                 una API, resultado de un benchmark, un bug y su causa raíz).
    "personal" — una preferencia, manía o decisión del operador/usuario que no
                 es verificable como hecho del mundo (gustos, hábitos de
                 trabajo, cómo quiere que se le hable, prioridades propias).

DISEÑO — variedad léxica real (no find/replace trivial):
    Cada texto se construye combinando, vía random.Random(seed) DEDICADO por
    índice, una PLANTILLA de entre varias por clase con SLOTS rellenados desde
    bancos de palabras independientes (sujeto, acción/detalle, dominio,
    calificador). La combinatoria plantilla x slots hace que dos pares de la
    misma clase casi nunca compartan estructura Y contenido a la vez — no es
    "cambiar una palabra en una frase fija": cambia la plantilla, el orden de
    cláusulas y el vocabulario simultáneamente. Esto se verifica en
    tests/benchmarks/test_gen_judge_pairs.py (TestLexicalVariety).

Determinismo: toda la aleatoriedad pasa por random.Random(seed) instanciado
una vez en generate_pairs; no se usa el módulo random global ni relojes/UUIDs.

Uso CLI:
    python -m tests.benchmarks.gen_judge_pairs --n 200 --seed 42 --out pairs.json
    python -m tests.benchmarks.gen_judge_pairs --n 200 --seed 42 \
        --personal-ratio 0.3 --out pairs.json
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import TypedDict


class Pair(TypedDict):
    text: str
    label: str


# ---------------------------------------------------------------------------
# Bancos léxicos (fijos, sin red, sin relojes) — la variedad viene de la
# combinatoria plantilla x slot, no de una lista de frases completas.
# ---------------------------------------------------------------------------

_FACTUAL_SUBJECTS = [
    "la librería requests",
    "el runtime de Node 20",
    "el índice SqliteMemoryIndex",
    "el modelo Kimi-K2",
    "la API de Stripe",
    "el parser de YAML",
    "el driver de Postgres",
    "el scheduler de Kubernetes",
    "la caché de Redis",
    "el compilador de mypy",
]

_FACTUAL_PREDICATES = [
    "cambió su comportamiento por defecto en la versión {ver}",
    "lanza una excepción {excname} cuando el input supera {n} elementos",
    "consume {n} MB de RAM en el caso peor bajo carga sostenida",
    "requiere el flag --{flag} para activar el modo estricto",
    "no soporta {feature} antes de la versión {ver}",
    "reporta latencia p99 de {n} ms en el benchmark local",
    "deprecó el parámetro {flag} a favor de {feature}",
    "falla silenciosamente si falta la variable de entorno {flag_upper}",
]

_FACTUAL_VER = ["1.2", "3.0", "0.9", "12.4", "2.1", "7.6"]
_FACTUAL_EXC = ["ValueError", "TimeoutError", "ConnectionResetError", "KeyError"]
_FACTUAL_FLAG = ["strict-mode", "verbose", "no-cache", "legacy-parser"]
_FACTUAL_FEATURE = ["streaming", "async batching", "TLS 1.3", "connection pooling"]

_PERSONAL_SUBJECTS = [
    "el operador",
    "el usuario",
    "prefiere que",
    "tiene la manía de",
    "quiere que Claude",
    "le molesta cuando",
    "insiste en que",
    "evita",
]

_PERSONAL_PREDICATES = [
    "los commits se hagan solo cuando lo pida explícitamente",
    "las respuestas eviten emojis salvo que se pidan",
    "se delegue en Sonnet/Haiku antes que gastar Opus en tareas mecánicas",
    "los docs de la raíz los cure él mismo, no un agente",
    "se investigue el estado del arte antes de decidir arquitectura",
    "se verifique con evidencia real antes de declarar algo terminado",
    "no se generalice una aprobación puntual a acciones futuras",
    "se le hable de forma directa y sin relleno",
    "se marque un ítem como dormido y se decida explícitamente si arreglarlo",
    "se use el worktree efímero real en vez de mutar el árbol vivo",
]

_QUALIFIERS = ["siempre", "de forma consistente", "en la última sesión", "por norma", ""]


def _render_factual(rng: random.Random) -> str:
    subject = rng.choice(_FACTUAL_SUBJECTS)
    predicate = rng.choice(_FACTUAL_PREDICATES)
    filled = predicate.format(
        ver=rng.choice(_FACTUAL_VER),
        excname=rng.choice(_FACTUAL_EXC),
        n=rng.choice([50, 100, 256, 1000, 4096, 8, 12]),
        flag=rng.choice(_FACTUAL_FLAG),
        flag_upper=rng.choice(_FACTUAL_FLAG).upper().replace("-", "_"),
        feature=rng.choice(_FACTUAL_FEATURE),
    )
    qualifier = rng.choice(_QUALIFIERS)
    text = f"{subject} {filled}"
    if qualifier:
        text = f"{text} ({qualifier})"
    return text[0].upper() + text[1:] + "."


def _render_personal(rng: random.Random) -> str:
    subject = rng.choice(_PERSONAL_SUBJECTS)
    predicate = rng.choice(_PERSONAL_PREDICATES)
    qualifier = rng.choice(_QUALIFIERS)
    text = f"{subject} {predicate}"
    if qualifier:
        text = f"{text}, {qualifier}"
    return text[0].upper() + text[1:] + "."


def generate_pairs(n: int, seed: int, personal_ratio: float = 0.5) -> list[Pair]:
    """Genera n pares (text, label) deterministas para una seed dada.

    Args:
        n: número total de pares a generar.
        seed: semilla determinista; misma (n, seed, personal_ratio) => mismos pares.
        personal_ratio: proporción objetivo de pares etiquetados "personal"
            (0.0 = solo factual, 1.0 = solo personal). Se redondea a entero
            de pares personales sobre n.

    Returns:
        Lista de dicts {"text": str, "label": "factual"|"personal"}, longitud n.
    """
    if n < 0:
        raise ValueError("n debe ser >= 0")
    if not 0.0 <= personal_ratio <= 1.0:
        raise ValueError("personal_ratio debe estar en [0.0, 1.0]")

    rng = random.Random(seed)
    n_personal = round(n * personal_ratio)
    labels = ["personal"] * n_personal + ["factual"] * (n - n_personal)
    rng.shuffle(labels)

    pairs: list[Pair] = []
    for label in labels:
        if label == "factual":
            text = _render_factual(rng)
        else:
            text = _render_personal(rng)
        pairs.append({"text": text, "label": label})
    return pairs


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Genera pares deterministas (texto, etiqueta) factual/personal para f2-6b paso 1."
    )
    parser.add_argument("--n", type=int, default=200, help="número de pares a generar")
    parser.add_argument("--seed", type=int, default=42, help="semilla determinista")
    parser.add_argument(
        "--personal-ratio",
        type=float,
        default=0.5,
        dest="personal_ratio",
        help="proporción objetivo de pares 'personal' en [0.0, 1.0]",
    )
    parser.add_argument("--out", type=str, required=True, help="ruta de salida del JSON")
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()
    pairs = generate_pairs(args.n, seed=args.seed, personal_ratio=args.personal_ratio)
    out_path = Path(args.out)
    out_path.write_text(json.dumps(pairs, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
