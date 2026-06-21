"""
Tests de Afinidad Maduración + LLMScorer.

Cubre:
- Creación y ciclo de ImmunityCandidate
- Hipermutación (estructura, generación, parent_id)
- Ciclo mature() con scorer y decider mockeados
- LLMScorer: scoring correcto + fail-closed en error de hub
- LLMTextMutator: devuelve original en fallo
- _parse_json_response: edge cases exhaustivos de parsing JSON
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from atlas.immunity.affinity_maturation import AffinityMaturation, ImmunityCandidate
from atlas.immunity.llm_scorer import EvaluationResult, LLMScorer, LLMTextMutator, _parse_json_response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_hub(text: str = '{"affinity_score": 0.85, "reasoning": "good"}', success: bool = True) -> MagicMock:
    hub = MagicMock()
    resp = MagicMock()
    resp.text = text
    resp.success = success
    hub.infer.return_value = resp
    return hub


def _make_decider(approved: bool = True) -> MagicMock:
    from atlas.core.decider import Allow, Deny
    decider = MagicMock()
    # decide(action, sanctioned_intent, context) → Allow | Deny
    decider.decide.return_value = Allow() if approved else Deny(reason="test")
    return decider


def _make_mutator(suffix: str = "_v") -> MagicMock:
    mutator = MagicMock()
    mutator.mutate.side_effect = lambda text: text + suffix
    return mutator


def _candidate(id: str = "c0", avoid: str = "block harmful", heuristic: str = "detect attack") -> ImmunityCandidate:
    return ImmunityCandidate(id=id, avoid_pattern=avoid, detection_heuristic=heuristic)


# ---------------------------------------------------------------------------
# ImmunityCandidate
# ---------------------------------------------------------------------------

def test_candidate_defaults():
    c = _candidate()
    assert c.affinity_score == 0.0
    assert c.generation == 0
    assert c.parent_id is None


def test_candidate_from_lesson():
    c = ImmunityCandidate.from_lesson("lesson-1", "block X", "detect X")
    assert c.parent_id == "lesson-1"
    assert c.generation == 0
    assert len(c.id) > 0


# ---------------------------------------------------------------------------
# AffinityMaturation — hipermutación
# ---------------------------------------------------------------------------

def test_hypermutate_count():
    scorer = MagicMock()
    maturation = AffinityMaturation(scorer=scorer, mutator=_make_mutator(), decider=_make_decider())
    clones = maturation.hypermutate(_candidate(), num_clones=6)
    assert len(clones) == 6


def test_hypermutate_increments_generation():
    maturation = AffinityMaturation(scorer=MagicMock(), mutator=_make_mutator(), decider=_make_decider())
    base = _candidate("base")
    clones = maturation.hypermutate(base, num_clones=3)
    assert all(c.generation == 1 for c in clones)
    assert all(c.parent_id == "base" for c in clones)


def test_hypermutate_reduces_mutation_rate():
    maturation = AffinityMaturation(scorer=MagicMock(), mutator=_make_mutator(), decider=_make_decider())
    base = ImmunityCandidate(id="b", avoid_pattern="x", detection_heuristic="y", mutation_rate=0.2)
    clones = maturation.hypermutate(base, num_clones=2)
    assert all(c.mutation_rate < base.mutation_rate for c in clones)


def test_hypermutate_calls_mutator():
    mutator = _make_mutator()
    maturation = AffinityMaturation(scorer=MagicMock(), mutator=mutator, decider=_make_decider())
    maturation.hypermutate(_candidate(), num_clones=4)
    # 4 clones × 2 campos = 8 llamadas
    assert mutator.mutate.call_count == 8


def test_hypermutate_text_differs_from_parent():
    mutator = _make_mutator("_mutated")
    maturation = AffinityMaturation(scorer=MagicMock(), mutator=mutator, decider=_make_decider())
    base = _candidate(avoid="block X")
    clones = maturation.hypermutate(base, num_clones=2)
    assert all(c.avoid_pattern == "block X_mutated" for c in clones)


# ---------------------------------------------------------------------------
# AffinityMaturation — ciclo mature()
# ---------------------------------------------------------------------------

def test_mature_empty_population():
    maturation = AffinityMaturation(scorer=MagicMock(), mutator=_make_mutator(), decider=_make_decider())
    result = maturation.mature(test_attacks=["attack"])
    assert result == []


def test_mature_promotes_high_affinity():
    scorer = MagicMock()
    scorer.score.return_value = 0.9  # supera el umbral por defecto 0.65

    maturation = AffinityMaturation(scorer=scorer, mutator=_make_mutator(), decider=_make_decider(approved=True))
    maturation.add_candidate(_candidate())

    promoted = maturation.mature(test_attacks=["attack"], num_clones=3)
    assert len(promoted) > 0
    assert all(c.affinity_score >= 0.65 for c in promoted)


def test_mature_rejects_low_affinity():
    scorer = MagicMock()
    scorer.score.return_value = 0.2  # por debajo del umbral

    maturation = AffinityMaturation(scorer=scorer, mutator=_make_mutator(), decider=_make_decider(approved=True))
    maturation.add_candidate(_candidate())

    promoted = maturation.mature(test_attacks=["attack"])
    assert promoted == []


def test_mature_decider_deny_blocks_promotion():
    scorer = MagicMock()
    scorer.score.return_value = 0.9

    maturation = AffinityMaturation(scorer=scorer, mutator=_make_mutator(), decider=_make_decider(approved=False))
    maturation.add_candidate(_candidate())

    promoted = maturation.mature(test_attacks=["attack"])
    assert promoted == []


def test_mature_population_capped():
    scorer = MagicMock()
    scorer.score.return_value = 0.9

    maturation = AffinityMaturation(
        scorer=scorer, mutator=_make_mutator(), decider=_make_decider(), max_population=5
    )
    for i in range(10):
        maturation.add_candidate(_candidate(id=f"c{i}"))

    maturation.mature(test_attacks=["attack"], num_clones=2)
    assert len(maturation.population) <= 5


# ---------------------------------------------------------------------------
# LLMScorer
# ---------------------------------------------------------------------------

def test_llm_scorer_valid_response():
    scorer = LLMScorer(hub=_make_hub('{"affinity_score": 0.75, "reasoning": "ok"}'))
    c = _candidate()
    score = scorer.score(c, ["attack 1", "attack 2"])
    assert 0.0 <= score <= 1.0
    assert abs(score - 0.75) < 1e-6


def test_llm_scorer_fail_closed_on_hub_error():
    scorer = LLMScorer(hub=_make_hub(success=False))
    score = scorer.score(_candidate(), ["attack"])
    assert score == 0.35


def test_llm_scorer_empty_attacks():
    scorer = LLMScorer(hub=_make_hub())
    score = scorer.score(_candidate(), [])
    assert score == 0.5
    # El hub no debería haberse llamado
    scorer._hub.infer.assert_not_called()


# ---------------------------------------------------------------------------
# LLMTextMutator
# ---------------------------------------------------------------------------

def test_llm_mutator_returns_rephrased():
    hub = _make_hub()
    hub.infer.return_value = MagicMock(success=True, text="  rephrased text  ")
    mutator = LLMTextMutator(hub=hub)
    result = mutator.mutate("original text")
    assert result == "rephrased text"


def test_llm_mutator_returns_original_on_hub_failure():
    hub = _make_hub(success=False)
    mutator = LLMTextMutator(hub=hub)
    result = mutator.mutate("original text")
    assert result == "original text"


def test_llm_mutator_returns_original_on_empty_response():
    hub = _make_hub(text="   ")
    hub.infer.return_value = MagicMock(success=True, text="   ")
    mutator = LLMTextMutator(hub=hub)
    result = mutator.mutate("original text")
    assert result == "original text"


def test_llm_mutator_skips_empty_input():
    hub = _make_hub()
    mutator = LLMTextMutator(hub=hub)
    result = mutator.mutate("   ")
    assert result == "   "
    hub.infer.assert_not_called()


# ---------------------------------------------------------------------------
# _parse_json_response — edge cases
# ---------------------------------------------------------------------------

def test_parse_valid_json():
    r = _parse_json_response('{"affinity_score": 0.92, "reasoning": "excellent"}')
    assert abs(r.affinity_score - 0.92) < 1e-6
    assert "excellent" in r.reasoning


def test_parse_json_with_surrounding_text():
    r = _parse_json_response('Here is my answer:\n{"affinity_score": 0.67, "reasoning": "ok"}\nEnd.')
    assert abs(r.affinity_score - 0.67) < 1e-6


def test_parse_json_in_markdown_block():
    r = _parse_json_response('```json\n{"affinity_score": 0.55, "reasoning": "fine"}\n```')
    assert abs(r.affinity_score - 0.55) < 1e-6


def test_parse_missing_affinity_score_uses_default():
    r = _parse_json_response('{"reasoning": "no score provided"}')
    assert r.affinity_score == 0.5


def test_parse_score_clamped_above_one():
    r = _parse_json_response('{"affinity_score": 1.8, "reasoning": "too high"}')
    assert r.affinity_score == 1.0


def test_parse_score_clamped_below_zero():
    r = _parse_json_response('{"affinity_score": -0.3, "reasoning": "negative"}')
    assert r.affinity_score == 0.0


def test_parse_invalid_json_returns_fallback():
    r = _parse_json_response("This is not JSON at all!")
    assert r.affinity_score == 0.4
    assert "parse error" in r.reasoning


def test_parse_malformed_json_still_extracts_score():
    # El segundo fallback extrae el número aunque el JSON esté incompleto
    r = _parse_json_response('{"affinity_score": 0.8, "reasoning": "missing closing brace"')
    assert abs(r.affinity_score - 0.8) < 1e-6


def test_parse_no_numeric_value_returns_fallback():
    r = _parse_json_response('{"affinity_score": "bad", "reasoning": "not a number"}')
    # affinity_score no es float → fallback al segundo camino que no encuentra dígitos
    assert r.affinity_score == 0.4


def test_parse_empty_string_returns_fallback():
    r = _parse_json_response("")
    assert r.affinity_score == 0.4


def test_parse_whitespace_only_returns_fallback():
    r = _parse_json_response("   \n\t  ")
    assert r.affinity_score == 0.4


def test_parse_score_extracted_from_key_without_braces():
    # Segundo intento: extrae el número directamente si las llaves no forman JSON válido
    r = _parse_json_response('"affinity_score": 0.71 reasoning: ok')
    assert abs(r.affinity_score - 0.71) < 1e-6
