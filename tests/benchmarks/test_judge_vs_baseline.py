"""
tests/benchmarks/test_judge_vs_baseline.py

Tests TDD para el runner del paso 2 de f2-6b (docs/backlog.yaml:
f2-6b-2-judge-vs-baseline-runner): evalúa un juez (LLM en producción, fake en
test) contra un baseline determinista por keywords, sobre los pares del paso 1
(tests/benchmarks/gen_judge_pairs.py).

Garantías verificadas:
  1. evaluate() calcula accuracy total y por clase para AMBOS (judge y
     baseline) con aritmética verificable a mano sobre pares sintéticos
     pequeños — juez fake con respuestas fijadas, CERO red.
  2. baseline_classify() (la regla real de keywords) acierta en casos
     diseñados para acertar y falla en casos diseñados para fallar (para no
     probar una tautología).
  3. CLI: lee el JSON del paso 1 (formato {"text", "label"}) y escribe un JSON
     de resultados con la misma forma que evaluate().
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.benchmarks.gen_judge_pairs import Pair
from tests.benchmarks.judge_vs_baseline import baseline_classify, evaluate


# ---------------------------------------------------------------------------
# Fixtures pequeñas y verificables a mano
# ---------------------------------------------------------------------------

def _pairs(*labels: str) -> list[Pair]:
    return [{"text": f"texto #{i}", "label": label} for i, label in enumerate(labels)]


class FakeJudge:
    """Juez fake: responde según un mapeo texto -> etiqueta fijado a mano.

    CERO red — no envuelve InferenceHub. Sirve solo para ejercitar la
    aritmética de evaluate() con un comportamiento total y determinísticamente
    conocido de antemano (incluyendo errores deliberados).
    """

    def __init__(self, answers: list[str]) -> None:
        # Las respuestas se consumen en orden de llamada (mismo orden que
        # evaluate() itera `pairs`), no por contenido de texto — así el test
        # no depende de que los textos sean únicos.
        self._answers = list(answers)
        self._i = 0

    def __call__(self, text: str) -> str:
        answer = self._answers[self._i]
        self._i += 1
        return answer


class ConstantBaseline:
    def __init__(self, answer: str) -> None:
        self._answer = answer

    def __call__(self, text: str) -> str:
        return self._answer


class TestEvaluateArithmetic:
    def test_perfect_judge_perfect_baseline(self) -> None:
        pairs = _pairs("factual", "factual", "personal", "personal")
        judge = FakeJudge(["factual", "factual", "personal", "personal"])
        baseline = FakeJudge(["factual", "factual", "personal", "personal"])
        result = evaluate(pairs, judge, baseline)

        assert result["n"] == 4
        assert result["judge"]["accuracy"] == 1.0
        assert result["judge"]["by_class"]["factual"] == 1.0
        assert result["judge"]["by_class"]["personal"] == 1.0
        assert result["baseline"]["accuracy"] == 1.0
        assert result["baseline"]["by_class"]["factual"] == 1.0
        assert result["baseline"]["by_class"]["personal"] == 1.0

    def test_judge_beats_baseline_known_ratio(self) -> None:
        # 4 pares: 2 factual, 2 personal.
        # Juez: acierta las 4 (accuracy 1.0, 1.0/1.0 por clase).
        # Baseline: acierta solo las 2 factual (accuracy 0.5, 1.0 factual / 0.0 personal).
        pairs = _pairs("factual", "factual", "personal", "personal")
        judge = FakeJudge(["factual", "factual", "personal", "personal"])
        baseline = FakeJudge(["factual", "factual", "factual", "factual"])
        result = evaluate(pairs, judge, baseline)

        assert result["judge"]["accuracy"] == 1.0
        assert result["baseline"]["accuracy"] == 0.5
        assert result["baseline"]["by_class"]["factual"] == 1.0
        assert result["baseline"]["by_class"]["personal"] == 0.0

    def test_uneven_class_sizes(self) -> None:
        # 3 factual, 1 personal. Juez falla 1 factual, acierta el resto.
        pairs = _pairs("factual", "factual", "factual", "personal")
        judge = FakeJudge(["factual", "personal", "factual", "personal"])
        baseline = ConstantBaseline("factual")
        result = evaluate(pairs, judge, baseline)

        assert result["n"] == 4
        # Judge: 3/4 correctas -> 0.75; factual 2/3, personal 1/1.
        assert result["judge"]["accuracy"] == 0.75
        assert result["judge"]["by_class"]["factual"] == 2 / 3
        assert result["judge"]["by_class"]["personal"] == 1.0
        # Baseline constante "factual": acierta 3 factual, falla la personal.
        assert result["baseline"]["accuracy"] == 0.75
        assert result["baseline"]["by_class"]["factual"] == 1.0
        assert result["baseline"]["by_class"]["personal"] == 0.0

    def test_empty_pairs_no_division_by_zero(self) -> None:
        result = evaluate([], FakeJudge([]), ConstantBaseline("factual"))
        assert result["n"] == 0
        assert result["judge"]["accuracy"] == 0.0
        assert result["judge"]["by_class"] == {}
        assert result["baseline"]["accuracy"] == 0.0
        assert result["baseline"]["by_class"] == {}


class TestBaselineKeywords:
    """Ejercita la regla REAL (no un fake) — casos donde acierta y casos
    diseñados para que falle (una regla de keywords no es un clasificador
    perfecto; eso es justamente lo que el paso 3 mide contra el juez)."""

    def test_hits_factual_with_version_and_api_keywords(self) -> None:
        text = "La librería requests cambió su comportamiento en la versión 3.0."
        assert baseline_classify(text) == "factual"

    def test_hits_factual_with_latency_and_flag_keywords(self) -> None:
        text = "El runtime reporta latencia p99 de 120 ms y requiere el flag --strict-mode."
        assert baseline_classify(text) == "factual"

    def test_hits_personal_with_operator_and_preference_keywords(self) -> None:
        text = "El operador prefiere que los commits se hagan solo cuando lo pida."
        assert baseline_classify(text) == "personal"

    def test_hits_personal_with_habit_keyword(self) -> None:
        text = "El usuario tiene la manía de verificar con evidencia real antes de declarar algo terminado."
        assert baseline_classify(text) == "personal"

    def test_fails_on_personal_text_without_keyword_overlap(self) -> None:
        # Frase personal sin ninguna de las keywords de la lista personal —
        # la regla determinista no tiene forma de acertar esto: caso
        # DISEÑADO para fallar, no una tautología.
        text = "A quien reporta esto no le gusta el ruido en las respuestas."
        assert baseline_classify(text) == "factual"

    def test_fails_on_factual_text_with_a_personal_keyword(self) -> None:
        # Texto factual que menciona "el usuario" incidentalmente -> la regla
        # por keywords lo clasifica mal como "personal" (falso negativo
        # esperado, sirve para justificar por qué un juez LLM puede mejorar).
        text = "El usuario final de la API de Stripe ve una excepción ValueError."
        assert baseline_classify(text) == "personal"


class TestCli:
    def test_cli_reads_pairs_writes_results(self, tmp_path: Path) -> None:
        pairs_path = tmp_path / "pairs.json"
        results_path = tmp_path / "results.json"
        pairs: list[Pair] = [
            {"text": "La librería requests cambió su comportamiento en la versión 3.0.", "label": "factual"},
            {"text": "El operador prefiere que se verifique con evidencia real.", "label": "personal"},
        ]
        pairs_path.write_text(json.dumps(pairs, ensure_ascii=False), encoding="utf-8")

        repo_root = Path(__file__).resolve().parents[2]
        # ATLAS_INFERENCE_MODE=stub fuerza al InferenceHub real que envuelve la
        # CLI a NO tocar red (mecanismo ya soportado por InferenceHub, ver
        # inference_hub.py) — CERO red en este test, sin necesitar inyectar
        # un fake dentro del propio subproceso.
        env = dict(os.environ, ATLAS_INFERENCE_MODE="stub")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.benchmarks.judge_vs_baseline",
                "--pairs",
                str(pairs_path),
                "--out",
                str(results_path),
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, result.stderr
        assert results_path.exists()
        data = json.loads(results_path.read_text(encoding="utf-8"))
        assert data["n"] == 2
        assert "judge" in data and "baseline" in data
        assert "accuracy" in data["judge"] and "by_class" in data["judge"]
        assert "accuracy" in data["baseline"] and "by_class" in data["baseline"]
