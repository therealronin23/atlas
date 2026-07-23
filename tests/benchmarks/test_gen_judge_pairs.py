"""
tests/benchmarks/test_gen_judge_pairs.py

Tests TDD para el generador determinista de pares (texto, etiqueta) del paso 1
de f2-6b (docs/backlog.yaml: f2-6b-1-gen-judge-pairs).

Garantías verificadas:
  1. Determinismo: misma seed produce exactamente los mismos pares (dos corridas).
  2. Formato: cada par es un dict con claves EXACTAS {"text", "label"}, text es str
     no vacío, label pertenece a {"factual", "personal"}.
  3. Proporción de clases: personal_ratio configurable se respeta dentro de la
     tolerancia de redondeo entero de n * ratio.
  4. Variedad léxica real: no todos los textos de una misma clase son idénticos
     (descarta un generador find/replace trivial sobre una única plantilla).
  5. Semillas distintas producen corpora distintos (no es una constante fija).
  6. CLI: escribe JSON válido a fichero con la lista de pares.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.benchmarks.gen_judge_pairs import generate_pairs


class TestDeterminism:
    def test_same_seed_same_pairs(self) -> None:
        a = generate_pairs(40, seed=7)
        b = generate_pairs(40, seed=7)
        assert a == b

    def test_different_seed_different_pairs(self) -> None:
        a = generate_pairs(40, seed=7)
        b = generate_pairs(40, seed=8)
        assert a != b


class TestFormat:
    def test_correct_keys_and_count(self) -> None:
        pairs = generate_pairs(20, seed=1)
        assert len(pairs) == 20
        for p in pairs:
            assert set(p.keys()) == {"text", "label"}

    def test_label_values_valid(self) -> None:
        pairs = generate_pairs(30, seed=2)
        for p in pairs:
            assert p["label"] in ("factual", "personal")

    def test_text_is_nonempty_string(self) -> None:
        pairs = generate_pairs(30, seed=3)
        for p in pairs:
            assert isinstance(p["text"], str)
            assert p["text"].strip() != ""


class TestClassProportion:
    def test_default_ratio_roughly_balanced(self) -> None:
        pairs = generate_pairs(100, seed=4)
        personal = sum(1 for p in pairs if p["label"] == "personal")
        # Default ~50/50, tolerancia de redondeo.
        assert 45 <= personal <= 55

    def test_custom_ratio_respected(self) -> None:
        pairs = generate_pairs(100, seed=5, personal_ratio=0.2)
        personal = sum(1 for p in pairs if p["label"] == "personal")
        # 20% de 100 = 20, tolerancia +-2 por redondeo.
        assert 18 <= personal <= 22

    def test_ratio_zero_yields_only_factual(self) -> None:
        pairs = generate_pairs(50, seed=6, personal_ratio=0.0)
        assert all(p["label"] == "factual" for p in pairs)

    def test_ratio_one_yields_only_personal(self) -> None:
        pairs = generate_pairs(50, seed=6, personal_ratio=1.0)
        assert all(p["label"] == "personal" for p in pairs)


class TestLexicalVariety:
    def test_no_trivial_repetition_within_class(self) -> None:
        pairs = generate_pairs(60, seed=9)
        factual_texts = {p["text"] for p in pairs if p["label"] == "factual"}
        personal_texts = {p["text"] for p in pairs if p["label"] == "personal"}
        # Con variedad léxica real, la mayoría de los textos de cada clase
        # deben ser distintos entre sí (no una única plantilla repetida).
        factual_count = sum(1 for p in pairs if p["label"] == "factual")
        personal_count = sum(1 for p in pairs if p["label"] == "personal")
        if factual_count:
            assert len(factual_texts) / factual_count > 0.6
        if personal_count:
            assert len(personal_texts) / personal_count > 0.6

    def test_texts_are_not_all_identical_length_pattern(self) -> None:
        # Descarta un generador que solo cambie una palabra en una plantilla
        # fija (mismo largo, misma estructura siempre).
        pairs = generate_pairs(40, seed=10)
        lengths = {len(p["text"]) for p in pairs}
        assert len(lengths) > 5


class TestCli:
    def test_cli_writes_json_file(self, tmp_path: Path) -> None:
        out = tmp_path / "pairs.json"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.benchmarks.gen_judge_pairs",
                "--n",
                "10",
                "--seed",
                "42",
                "--out",
                str(out),
            ],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 10
        for p in data:
            assert set(p.keys()) == {"text", "label"}

    def test_cli_deterministic_across_invocations(self, tmp_path: Path) -> None:
        out1 = tmp_path / "a.json"
        out2 = tmp_path / "b.json"
        repo_root = Path(__file__).resolve().parents[2]
        for out in (out1, out2):
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tests.benchmarks.gen_judge_pairs",
                    "--n",
                    "15",
                    "--seed",
                    "99",
                    "--out",
                    str(out),
                ],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")
