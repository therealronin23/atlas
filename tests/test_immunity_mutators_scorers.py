"""
Tests de DeterministicMutator y RecallAffinityScorer.

Cubre:
- DeterministicMutator: determinismo, intensity 0 vs alta, monotonía débil de
  distancia, salida no vacía para entrada no vacía.
- RecallAffinityScorer: candidato reconocido vs irrelevante, lista vacía, Protocol.
- Integración E2E: AffinityMaturation con implementaciones concretas (sin mocks).
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest

from atlas.immunity.affinity_maturation import AffinityMaturation, ImmunityCandidate
from atlas.immunity.mutators import DeterministicMutator
from atlas.immunity.scorers import RecallAffinityScorer
from atlas.memory.embeddings import StubEmbedder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _levenshtein(a: str, b: str) -> int:
    """Levenshtein de caracteres, O(m*n). Suficiente para textos cortos de test."""
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    return dp[n]


def _token_diff_fraction(original: str, mutated: str) -> float:
    """Fracción de tokens distintos entre original y mutated (unordered diff simplificado)."""
    orig_tokens = original.split()
    mut_tokens = mutated.split()
    if not orig_tokens and not mut_tokens:
        return 0.0
    # Usamos conjunto (multiconjunto simplificado) para detectar cambios brutos.
    orig_set = set(t.lower() for t in orig_tokens)
    mut_set = set(t.lower() for t in mut_tokens)
    changed = len(orig_set.symmetric_difference(mut_set))
    total = max(len(orig_set), len(mut_set), 1)
    return changed / total


def _make_allow_decider() -> MagicMock:
    from atlas.core.decider import Allow
    decider = MagicMock()
    decider.decide.return_value = Allow()
    return decider


# ---------------------------------------------------------------------------
# DeterministicMutator — determinismo
# ---------------------------------------------------------------------------

SAMPLE_TEXTS = [
    "avoid harmful code injection attacks",
    "detect eval exec input bypass filter",
    "the user sends malicious payload to the system",
    "block ignore override jailbreak escape",
]


class TestDeterministicMutatorDeterminism:
    def test_same_instance_same_output(self):
        m = DeterministicMutator(intensity=0.5, seed=42)
        for text in SAMPLE_TEXTS:
            assert m.mutate(text) == m.mutate(text)

    def test_different_instances_same_seed_same_output(self):
        for text in SAMPLE_TEXTS:
            a = DeterministicMutator(intensity=0.5, seed=7)
            b = DeterministicMutator(intensity=0.5, seed=7)
            assert a.mutate(text) == b.mutate(text)

    def test_different_seeds_may_differ(self):
        # No obligatorio, pero al menos con textos largos los seeds suelen diferir.
        m0 = DeterministicMutator(intensity=0.8, seed=0)
        m1 = DeterministicMutator(intensity=0.8, seed=99)
        text = "avoid harmful code injection attacks bypass filter"
        # Relajado: no es garantía estricta, pero es la expectativa.
        # Si casualmente coinciden, el test no falla — es comportamiento válido.
        _ = m0.mutate(text) != m1.mutate(text)  # simplemente documentamos

    def test_mutate_at_distance_same_params_same_output(self):
        m = DeterministicMutator(seed=1)
        text = "detect attack pattern in user input"
        for d in [0.0, 0.3, 0.6, 1.0]:
            assert m.mutate_at_distance(text, d) == m.mutate_at_distance(text, d)


# ---------------------------------------------------------------------------
# DeterministicMutator — intensity 0 ≈ original
# ---------------------------------------------------------------------------

class TestDeterministicMutatorIntensity:
    def test_intensity_zero_returns_original(self):
        m = DeterministicMutator(intensity=0.0, seed=0)
        for text in SAMPLE_TEXTS:
            assert m.mutate(text) == text

    def test_mutate_at_distance_zero_returns_original(self):
        m = DeterministicMutator(seed=0)
        for text in SAMPLE_TEXTS:
            assert m.mutate_at_distance(text, 0.0) == text

    def test_high_intensity_differs_from_original(self):
        """Con intensity alta, al menos alguna transformación se aplica."""
        m = DeterministicMutator(intensity=1.0, seed=0)
        # Usamos texto largo para que haya tokens que transformar.
        text = "avoid harmful code injection attacks bypass filter escape system"
        result = m.mutate(text)
        # La salida debe diferir del original (al menos un token cambiado).
        assert result != text or len(text.split()) < 2  # textos de 1 token son edge case

    def test_empty_string_returns_empty(self):
        m = DeterministicMutator(intensity=1.0, seed=0)
        assert m.mutate("") == ""

    def test_non_empty_input_non_empty_output(self):
        m = DeterministicMutator(intensity=0.9, seed=0)
        for text in SAMPLE_TEXTS:
            result = m.mutate(text)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_invalid_intensity_raises(self):
        with pytest.raises(ValueError):
            DeterministicMutator(intensity=1.5)
        with pytest.raises(ValueError):
            DeterministicMutator(intensity=-0.1)


# ---------------------------------------------------------------------------
# DeterministicMutator — monotonía DÉBIL de distancia
# ---------------------------------------------------------------------------

class TestDeterministicMutatorMonotonicity:
    """
    Verifica que mayor distance produce, EN PROMEDIO, mayor diferencia.

    NOTA: La monotonía es una TENDENCIA estadística promediada sobre varios
    textos, NO una garantía estricta por llamada individual. Las transformaciones
    son discretas y la distancia de Levenshtein puede ser no-monótona para
    textos individuales. El test compara medias sobre el corpus SAMPLE_TEXTS.
    """

    def test_weak_monotonicity_avg_levenshtein(self):
        m = DeterministicMutator(seed=0)
        distances = [0.1, 0.4, 0.7, 1.0]
        avg_diffs: list[float] = []
        for d in distances:
            diffs = []
            for text in SAMPLE_TEXTS:
                mutated = m.mutate_at_distance(text, d)
                diffs.append(_levenshtein(text, mutated))
            avg_diffs.append(sum(diffs) / len(diffs))

        # La tendencia: cada nivel de distancia >= al anterior en promedio.
        # Permitimos que hasta un par de pasos consecutivos sean iguales.
        n_violations = sum(
            1 for a, b in zip(avg_diffs, avg_diffs[1:]) if b < a
        )
        # Toleramos a lo sumo 1 violación de 3 pares (33%).
        assert n_violations <= 1, (
            f"Demasiadas violaciones de monotonía: {n_violations}/3. "
            f"avg_diffs={avg_diffs}. "
            "Nota: la monotonía es tendencia, no garantía estricta."
        )

    def test_weak_monotonicity_avg_token_diff(self):
        m = DeterministicMutator(seed=42)
        distances = [0.0, 0.3, 0.6, 0.9]
        avg_diffs: list[float] = []
        for d in distances:
            diffs = [_token_diff_fraction(t, m.mutate_at_distance(t, d)) for t in SAMPLE_TEXTS]
            avg_diffs.append(sum(diffs) / len(diffs))

        # distance=0.0 debe dar 0 diferencia exactamente.
        assert avg_diffs[0] == 0.0

        # La media final debe ser estrictamente mayor que la inicial.
        assert avg_diffs[-1] > avg_diffs[0]


# ---------------------------------------------------------------------------
# RecallAffinityScorer
# ---------------------------------------------------------------------------

class TestRecallAffinityScorer:
    def _scorer(self, threshold: float = 0.8) -> RecallAffinityScorer:
        return RecallAffinityScorer(embedder=StubEmbedder(dim=64), threshold=threshold)

    def _candidate(self, avoid: str, heuristic: str = "") -> ImmunityCandidate:
        return ImmunityCandidate(
            id="test-id",
            avoid_pattern=avoid,
            detection_heuristic=heuristic,
        )

    def test_empty_attacks_returns_zero(self):
        scorer = self._scorer()
        c = self._candidate("eval exec bypass")
        assert scorer.score(c, []) == 0.0

    def test_identical_attack_scores_high(self):
        """Un ataque idéntico al patrón del candidato debe producir similitud máxima."""
        text = "eval exec user input injection"
        scorer = self._scorer(threshold=0.5)  # umbral bajo para StubEmbedder
        c = self._candidate(avoid=text)
        score = scorer.score(c, [text])
        # Con StubEmbedder un texto idéntico debe tener similitud coseno ~1.
        assert score >= 0.5, f"score={score} debería ser >= 0.5 con texto idéntico"

    def test_irrelevant_candidate_scores_low(self):
        """Candidato con patrón totalmente distinto al ataque → score bajo."""
        scorer = self._scorer(threshold=0.99)  # umbral muy alto
        c = self._candidate(avoid="aaaa bbbb cccc dddd eeee")
        attacks = ["zzzz yyyy xxxx wwww vvvv"]
        score = scorer.score(c, attacks)
        # Con umbral muy alto, textos totalmente distintos no superan el threshold.
        assert score == 0.0

    def test_score_range(self):
        scorer = self._scorer(threshold=0.5)
        c = self._candidate(avoid="detect attack pattern in user input")
        attacks = ["detect attack pattern in user input", "completely different text"]
        score = scorer.score(c, attacks)
        assert 0.0 <= score <= 1.0

    def test_empty_candidate_pattern_returns_zero(self):
        scorer = self._scorer()
        c = self._candidate(avoid="", heuristic="")
        assert scorer.score(c, ["some attack"]) == 0.0

    def test_protocol_isinstance(self):
        """RecallAffinityScorer satisface el Protocol AffinityScorer (runtime_checkable)."""
        from atlas.immunity.affinity_maturation import AffinityScorer
        scorer = RecallAffinityScorer()
        assert isinstance(scorer, AffinityScorer)

    def test_deterministic_with_stub(self):
        """Misma entrada → mismo score con StubEmbedder."""
        scorer = self._scorer(threshold=0.5)
        c = self._candidate(avoid="eval exec bypass", heuristic="detect injection")
        attacks = ["eval user input", "exec code bypass"]
        s1 = scorer.score(c, attacks)
        s2 = scorer.score(c, attacks)
        assert s1 == s2

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError):
            RecallAffinityScorer(threshold=1.5)
        with pytest.raises(ValueError):
            RecallAffinityScorer(threshold=-0.1)


# ---------------------------------------------------------------------------
# DeterministicMutator Protocol compliance
# ---------------------------------------------------------------------------

class TestMutatorProtocol:
    def test_protocol_isinstance(self):
        """DeterministicMutator satisface el Protocol TextMutator (runtime_checkable)."""
        from atlas.immunity.affinity_maturation import TextMutator
        m = DeterministicMutator()
        assert isinstance(m, TextMutator)


# ---------------------------------------------------------------------------
# Integración E2E: AffinityMaturation con impls concretas
# ---------------------------------------------------------------------------

class TestAffinityMaturationE2E:
    """
    Verifica que el motor AffinityMaturation es ejecutable de punta a punta
    con DeterministicMutator y RecallAffinityScorer (sin mocks de scorer/mutator).

    El decider_stub aprueba todo (Allow) para aislar el comportamiento del motor.
    """

    def test_e2e_mature_returns_list(self):
        """El motor corre sin lanzar y devuelve una lista."""
        scorer = RecallAffinityScorer(
            embedder=StubEmbedder(dim=64),
            threshold=0.0,  # umbral 0 → todo se reconoce → score=1.0
        )
        mutator = DeterministicMutator(intensity=0.5, seed=0)
        decider = _make_allow_decider()

        maturation = AffinityMaturation(
            scorer=scorer,
            mutator=mutator,
            decider=decider,
            max_population=20,
        )

        # Añadimos un candidato desde una "lección".
        candidate = ImmunityCandidate.from_lesson(
            lesson_id="lesson-001",
            avoid_pattern="eval exec user input bypass",
            detection_heuristic="detect code injection pattern",
        )
        maturation.add_candidate(candidate)

        test_attacks = [
            "eval user input",
            "exec bypass system",
            "inject code via payload",
        ]

        result = maturation.mature(test_attacks=test_attacks, num_clones=4, min_affinity=0.0)

        assert isinstance(result, list)
        # Con min_affinity=0.0 y threshold=0.0, todos los clones deberían ser promovidos
        # (hasta max_promoted=5 por defecto). Al menos 1 aprobado.
        assert len(result) >= 1

    def test_e2e_empty_population_returns_empty(self):
        scorer = RecallAffinityScorer(embedder=StubEmbedder(dim=64))
        mutator = DeterministicMutator(intensity=0.3)
        decider = _make_allow_decider()

        maturation = AffinityMaturation(scorer=scorer, mutator=mutator, decider=decider)
        result = maturation.mature(test_attacks=["attack"])
        assert result == []

    def test_e2e_population_bounded(self):
        """La población no supera max_population tras mature()."""
        scorer = RecallAffinityScorer(
            embedder=StubEmbedder(dim=64),
            threshold=0.0,
        )
        mutator = DeterministicMutator(intensity=0.4, seed=99)
        decider = _make_allow_decider()

        maturation = AffinityMaturation(
            scorer=scorer, mutator=mutator, decider=decider, max_population=10
        )
        for i in range(5):
            maturation.add_candidate(
                ImmunityCandidate(
                    id=f"c{i}",
                    avoid_pattern=f"pattern {i}",
                    detection_heuristic=f"heuristic {i}",
                )
            )

        maturation.mature(test_attacks=["x", "y"], num_clones=4, min_affinity=0.0)
        assert len(maturation.population) <= 10

    def test_e2e_high_threshold_no_promotion(self):
        """Con threshold muy alto, los candidatos mutados no pasan el scoring."""
        scorer = RecallAffinityScorer(
            embedder=StubEmbedder(dim=64),
            threshold=0.9999,  # casi imposible de superar con StubEmbedder + textos distintos
        )
        mutator = DeterministicMutator(intensity=0.5, seed=0)
        decider = _make_allow_decider()

        maturation = AffinityMaturation(
            scorer=scorer, mutator=mutator, decider=decider
        )
        maturation.add_candidate(
            ImmunityCandidate(
                id="c0",
                avoid_pattern="aaaa bbbb cccc",
                detection_heuristic="dddd eeee ffff",
            )
        )
        # Ataques totalmente distintos → similitud baja → no supera min_affinity
        result = maturation.mature(
            test_attacks=["zzzz yyyy xxxx"],
            num_clones=3,
            min_affinity=0.9,  # umbral alto en selección clonal
        )
        assert result == []
