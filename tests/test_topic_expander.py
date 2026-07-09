"""TopicExpander -- amplia INTERESES amplios en consultas de busqueda
CONCRETAS y VARIADAS, para que PanoramaScout.discover() no reciba siempre la
misma lista fija y acotada de palabras literales (correccion del usuario: el
ecosistema puede no tener nombre todavia -- una lista fija nunca lo
encuentra). Sigue el patron exacto de test_dep_analyst.py: un solo hub falso
inyectado, sin llamadas reales a ningun LLM."""

from __future__ import annotations

from typing import Any

import pytest

from atlas.core.inference_hub import InferenceLevel, InferenceResponse
from atlas.core.self_maintenance.topic_expander import TopicExpander, TopicExpansion


class FakeHub:
    """Hub de inferencia falso: mapea seed -> texto de respuesta (o excepcion).
    Un solo rol de control, igual que FakeHub en test_dep_analyst.py."""

    def __init__(self, responses: dict[str, str] | None = None, *, raise_for: set[str] | None = None) -> None:
        self._responses = responses or {}
        self._raise_for = raise_for or set()
        self.calls: list[str] = []

    def infer(self, request: Any) -> InferenceResponse:
        # El seed va en el ultimo mensaje "user" del request.
        seed = request.messages[-1]["content"]
        self.calls.append(seed)
        if seed in self._raise_for:
            raise RuntimeError("hub caído")
        text = self._responses.get(seed, "")
        return InferenceResponse(
            text=text, provider="fake", model="fake",
            level=InferenceLevel.L1, latency_ms=1, success=True,
        )


class TestExpandSingleSeed:
    def test_valid_json_array_returns_n_queries(self) -> None:
        hub = FakeHub({"memoria de agentes de IA": '["agent memory decay", "long-term context agents", "memory consolidation llm"]'})
        result = TopicExpander(hub=hub).expand(["memoria de agentes de IA"])
        assert result == ["agent memory decay", "long-term context agents", "memory consolidation llm"]


class TestExpandMultipleSeeds:
    def test_union_deduplicated_preserving_order(self) -> None:
        hub = FakeHub({
            "orquestacion local": '["local orchestration", "on-device agents", "shared query"]',
            "auditoria verificable": '["verifiable audit", "shared query", "tamper evident logs"]',
        })
        result = TopicExpander(hub=hub).expand(["orquestacion local", "auditoria verificable"])
        assert result == [
            "local orchestration", "on-device agents", "shared query",
            "verifiable audit", "tamper evident logs",
        ]


class TestFailOpen:
    def test_unparseable_text_falls_back_to_seed(self) -> None:
        hub = FakeHub({
            "seed roto": "lo siento, no puedo ayudar con eso",
            "seed bueno": '["query buena uno", "query buena dos"]',
        })
        result = TopicExpander(hub=hub).expand(["seed roto", "seed bueno"])
        assert result == ["seed roto", "query buena uno", "query buena dos"]

    def test_hub_exception_falls_back_to_seed(self) -> None:
        hub = FakeHub(raise_for={"seed explota"})
        result = TopicExpander(hub=hub).expand(["seed explota"])
        assert result == ["seed explota"]

    def test_non_string_elements_falls_back_to_seed(self) -> None:
        hub = FakeHub({"seed mixto": '[1, 2, "x"]'})
        result = TopicExpander(hub=hub).expand(["seed mixto"])
        assert result == ["seed mixto"]


class TestExpandDetailed:
    def test_returns_one_expansion_per_seed(self) -> None:
        hub = FakeHub({
            "a": '["a1", "a2"]',
            "b": '["b1"]',
        })
        detailed = TopicExpander(hub=hub).expand_detailed(["a", "b"])
        assert len(detailed) == 2
        assert detailed[0].seed == "a"
        assert detailed[0].queries == ["a1", "a2"]
        assert detailed[1].seed == "b"
        assert detailed[1].queries == ["b1"]


class TestTopicExpansionToDict:
    def test_roundtrip(self) -> None:
        expansion = TopicExpansion(seed="s", queries=["q1", "q2"])
        d = expansion.to_dict()
        assert d["seed"] == "s"
        assert d["queries"] == ["q1", "q2"]
        assert "generated_at" in d


class TestEmptySeeds:
    def test_empty_seed_interests_returns_empty_without_calling_hub(self) -> None:
        hub = FakeHub()
        result = TopicExpander(hub=hub).expand([])
        assert result == []
        assert hub.calls == []


class TestSearchabilityFilter:
    """Curado 2026-07-09: la primera pasada real dio 0 hallazgos — consultas
    en español, frases literales y jerga interna. El prompt pide inglés corto
    y el filtro determinista corta lo que el L1 barato aún emita mal."""

    def test_drops_long_nonenglish_and_internal_identifier_queries(self) -> None:
        hub = FakeHub({"semilla": (
            '["temporal knowledge graph", '
            '"búsqueda de documentos en grafo", '
            '"optimización de consultas en grafos de conocimiento con restricciones", '
            '"run_item git worktree", '
            '"agent memory benchmark"]'
        )})
        result = TopicExpander(hub=hub).expand(["semilla"])
        assert result == ["temporal knowledge graph", "agent memory benchmark"]

    def test_all_filtered_falls_back_to_seed(self) -> None:
        hub = FakeHub({"semilla": '["consulta española acentuada", "otra consulta española ñ"]'})
        result = TopicExpander(hub=hub).expand(["semilla"])
        assert result == ["semilla"]

    def test_prompt_demands_english_github_style_queries(self) -> None:
        from atlas.core.self_maintenance.topic_expander import _EXPAND_INSTRUCTION_TEMPLATE

        rendered = _EXPAND_INSTRUCTION_TEMPLATE.format(n=4)
        assert "INGLÉS" in rendered
        assert "GitHub" in rendered
