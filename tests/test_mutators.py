"""
Tests de DeterministicMutator (usado por scripts/redteam: transfer/generalization).

Extraído de test_immunity_mutators_scorers al cuarentenar la capa de afinidad
(scorers/affinity_maturation) en F3 (vapor de sistema). mutators SÍ se usa.
"""

from __future__ import annotations

import pytest

from atlas.immunity.mutators import DeterministicMutator


def _levenshtein(a: str, b: str) -> int:
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
    orig_set = set(t.lower() for t in original.split())
    mut_set = set(t.lower() for t in mutated.split())
    if not orig_set and not mut_set:
        return 0.0
    changed = len(orig_set.symmetric_difference(mut_set))
    total = max(len(orig_set), len(mut_set), 1)
    return changed / total


SAMPLE_TEXTS = [
    "avoid harmful code injection attacks",
    "detect eval exec input bypass filter",
    "the user sends malicious payload to the system",
    "block ignore override jailbreak escape",
]


class TestDeterminism:
    def test_same_instance_same_output(self):
        m = DeterministicMutator(intensity=0.5, seed=42)
        for text in SAMPLE_TEXTS:
            assert m.mutate(text) == m.mutate(text)

    def test_different_instances_same_seed_same_output(self):
        for text in SAMPLE_TEXTS:
            a = DeterministicMutator(intensity=0.5, seed=7)
            b = DeterministicMutator(intensity=0.5, seed=7)
            assert a.mutate(text) == b.mutate(text)

    def test_mutate_at_distance_same_params_same_output(self):
        m = DeterministicMutator(seed=1)
        text = "detect attack pattern in user input"
        for d in [0.0, 0.3, 0.6, 1.0]:
            assert m.mutate_at_distance(text, d) == m.mutate_at_distance(text, d)


class TestIntensity:
    def test_intensity_zero_returns_original(self):
        m = DeterministicMutator(intensity=0.0, seed=0)
        for text in SAMPLE_TEXTS:
            assert m.mutate(text) == text

    def test_mutate_at_distance_zero_returns_original(self):
        m = DeterministicMutator(seed=0)
        for text in SAMPLE_TEXTS:
            assert m.mutate_at_distance(text, 0.0) == text

    def test_high_intensity_differs(self):
        m = DeterministicMutator(intensity=1.0, seed=0)
        text = "avoid harmful code injection attacks bypass filter escape system"
        assert m.mutate(text) != text or len(text.split()) < 2

    def test_empty_string_returns_empty(self):
        assert DeterministicMutator(intensity=1.0, seed=0).mutate("") == ""

    def test_non_empty_input_non_empty_output(self):
        m = DeterministicMutator(intensity=0.9, seed=0)
        for text in SAMPLE_TEXTS:
            r = m.mutate(text)
            assert isinstance(r, str) and len(r) > 0

    def test_invalid_intensity_raises(self):
        with pytest.raises(ValueError):
            DeterministicMutator(intensity=1.5)
        with pytest.raises(ValueError):
            DeterministicMutator(intensity=-0.1)


class TestMonotonicity:
    def test_weak_monotonicity_avg_levenshtein(self):
        m = DeterministicMutator(seed=0)
        avg_diffs = []
        for d in [0.1, 0.4, 0.7, 1.0]:
            diffs = [_levenshtein(t, m.mutate_at_distance(t, d)) for t in SAMPLE_TEXTS]
            avg_diffs.append(sum(diffs) / len(diffs))
        n_violations = sum(1 for a, b in zip(avg_diffs, avg_diffs[1:]) if b < a)
        assert n_violations <= 1, f"avg_diffs={avg_diffs}"

    def test_weak_monotonicity_avg_token_diff(self):
        m = DeterministicMutator(seed=42)
        avg_diffs = []
        for d in [0.0, 0.3, 0.6, 0.9]:
            diffs = [_token_diff_fraction(t, m.mutate_at_distance(t, d)) for t in SAMPLE_TEXTS]
            avg_diffs.append(sum(diffs) / len(diffs))
        assert avg_diffs[0] == 0.0
        assert avg_diffs[-1] > avg_diffs[0]
