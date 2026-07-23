"""Primera soul ejecutable de Atlas: devil_advocate (Foundry Fase C, ADR-069).

`schemas/soul_manifest.schema.json` definía SOLO el contrato hasta ahora —
ninguna soul se ejecutaba (verificado: grep de 'devil_advocate'/'SoulManifest'
en src/atlas/ no devolvía nada antes de este cambio). Este test cubre el
runtime de la primera soul concreta: manifiesto real conforme al contrato,
invocación vía InferenceHub (rol, no modelo fijo — ADR-016), salida
estructurada conforme a su propio output_schema_ref, y honestidad ante fallo
(nunca finge 'sin objeción' cuando no pudo evaluar).

La integración con la ruta dorada (dónde se engancha, qué pasa con el
veredicto) vive en tests/test_golden_route_soul_review.py — aquí solo la
unidad de la soul."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from atlas.core.inference_hub import InferenceLevel, InferenceRequest, InferenceResponse
from atlas.missions.souls.devil_advocate import (
    DevilAdvocateVerdict,
    load_manifest,
    review_mission,
)

REPO = Path(__file__).resolve().parents[1]


def _mission(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "mission_id": "msn_abc123",
        "intent": "Actualizar cryptography a la última versión",
        "state": "awaiting_human_approval",
        "risk": "high",
        "origin": "auto",
        "artifacts": ["pyproject.toml"],
        "evidence_bundle": {"validation": {"pytest_exit": 0, "mypy_exit": 0}, "refs": ["ledger:abc123"]},
    }
    base.update(overrides)
    return base


class _FakeHub:
    """Doble de InferenceHub: captura la request y devuelve un texto fijo,
    sin llamar a ningún proveedor real (mismo patrón que _RunnerLike/
    _SubprocessRunner en golden_route.py / test_self_construction_golden_route.py)."""

    def __init__(self, text: str = "", *, success: bool = True, error: str | None = None) -> None:
        self._text = text
        self._success = success
        self._error = error
        self.calls: list[tuple[str, InferenceRequest]] = []

    def infer_for_role(self, role: str, request: InferenceRequest) -> InferenceResponse:
        self.calls.append((role, request))
        return InferenceResponse(
            text=self._text,
            provider="fake",
            model="fake-model",
            level=request.level,
            latency_ms=1,
            success=self._success,
            error=self._error,
        )


# --------------------------------------------------------------- manifiesto

def test_manifest_conforms_to_soul_manifest_schema() -> None:
    schema = json.loads((REPO / "schemas" / "soul_manifest.schema.json").read_text())
    validator = Draft202012Validator(schema)
    manifest = load_manifest()
    errors = list(validator.iter_errors(manifest))
    assert not errors, [e.message for e in errors]


def test_manifest_forbids_all_tools() -> None:
    manifest = load_manifest()
    assert manifest["tools_allowed"] == []
    assert manifest["soul_id"] == "soul_devil_advocate"


def test_manifest_memory_scope_is_empty() -> None:
    # invariante: la soul no lee ni escribe memoria (v0)
    assert load_manifest()["memory_scope"] == []


# ------------------------------------------------------------- review_mission

def test_review_mission_never_requests_tools() -> None:
    """tools_allowed=[] en el manifiesto: la request al hub jamás lleva `tools`."""
    hub = _FakeHub(json.dumps({"verdict": "no_objection", "reasoning": "ok", "confidence": 0.9}))
    review_mission(_mission(), hub=hub)
    assert len(hub.calls) == 1
    _, request = hub.calls[0]
    assert request.tools is None


def test_review_mission_uses_preferred_model_role() -> None:
    hub = _FakeHub(json.dumps({"verdict": "no_objection", "reasoning": "ok", "confidence": 0.9}))
    review_mission(_mission(), hub=hub)
    role, _ = hub.calls[0]
    assert role == load_manifest()["preferred_model_role"]


def test_review_mission_parses_objection_verdict() -> None:
    hub = _FakeHub(json.dumps({
        "verdict": "objection",
        "reasoning": "Riesgo declarado high sin validación ejecutada.",
        "confidence": 0.8,
    }))
    verdict = review_mission(_mission(risk="high", evidence_bundle={"validation": None, "refs": []}), hub=hub)
    assert isinstance(verdict, DevilAdvocateVerdict)
    assert verdict.verdict == "objection"
    assert verdict.objection is True
    assert verdict.mission_id == "msn_abc123"
    assert verdict.soul_id == "soul_devil_advocate"
    assert "validación" in verdict.reasoning or verdict.reasoning


def test_review_mission_parses_no_objection_verdict() -> None:
    hub = _FakeHub(json.dumps({
        "verdict": "no_objection",
        "reasoning": "Validación pasó y el intent es acotado.",
        "confidence": 0.7,
    }))
    verdict = review_mission(_mission(), hub=hub)
    assert verdict.verdict == "no_objection"
    assert verdict.objection is False


def test_review_mission_tolerates_prose_around_json() -> None:
    hub = _FakeHub(
        'Aquí está mi análisis:\n{"verdict": "objection", "reasoning": "riesgo alto", "confidence": 0.6}\nFin.'
    )
    verdict = review_mission(_mission(), hub=hub)
    assert verdict.verdict == "objection"


def test_review_mission_fails_open_to_unknown_on_provider_failure() -> None:
    """El modelo no respondió: nunca se finge 'sin objeción' — se declara
    'unknown' con honestidad (mismo patrón que RootCauseClassifier)."""
    hub = _FakeHub("", success=False, error="RateLimitError: 429")
    verdict = review_mission(_mission(), hub=hub)
    assert verdict.verdict == "unknown"
    assert verdict.objection is False
    assert "429" in verdict.reasoning or "RateLimitError" in verdict.reasoning


def test_review_mission_fails_open_to_unknown_on_unparseable_output() -> None:
    hub = _FakeHub("esto no es JSON en absoluto")
    verdict = review_mission(_mission(), hub=hub)
    assert verdict.verdict == "unknown"


def test_review_mission_fails_open_to_unknown_on_out_of_vocabulary_verdict() -> None:
    hub = _FakeHub(json.dumps({"verdict": "yes", "reasoning": "x", "confidence": 0.5}))
    verdict = review_mission(_mission(), hub=hub)
    assert verdict.verdict == "unknown"


def test_review_mission_clamps_confidence_to_unit_interval() -> None:
    hub = _FakeHub(json.dumps({"verdict": "no_objection", "reasoning": "ok", "confidence": 5.0}))
    verdict = review_mission(_mission(), hub=hub)
    assert 0.0 <= verdict.confidence <= 1.0


def test_review_mission_survives_hub_exception() -> None:
    class _ExplodingHub:
        def infer_for_role(self, role: str, request: InferenceRequest) -> InferenceResponse:
            raise RuntimeError("boom")

    verdict = review_mission(_mission(), hub=_ExplodingHub())
    assert verdict.verdict == "unknown"


# --------------------------------------------------------- output schema

def test_verdict_output_conforms_to_own_schema() -> None:
    schema = json.loads((REPO / "schemas" / "devil_advocate_verdict.schema.json").read_text())
    validator = Draft202012Validator(schema)
    hub = _FakeHub(json.dumps({"verdict": "objection", "reasoning": "x", "confidence": 0.4}))
    verdict = review_mission(_mission(), hub=hub)
    errors = list(validator.iter_errors(verdict.to_dict()))
    assert not errors, [e.message for e in errors]
