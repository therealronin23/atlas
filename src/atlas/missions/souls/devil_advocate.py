"""Primera soul ejecutable de Atlas: devil_advocate (Foundry Fase C, ADR-069).

`schemas/soul_manifest.schema.json` definía SOLO el contrato — "ninguna soul
se ejecuta todavía". Este módulo cierra ese hueco con la primera soul real:
revisa una misión de riesgo alto/crítico de la ruta dorada y devuelve un
veredicto estructurado (objeción razonada, sin objeción, o `unknown` si no
pudo evaluar). Invariante D2 intacta en TODO momento: la soul solo informa,
nunca aprueba/rechaza/aplica — eso lo sigue haciendo un humano vía
`GoldenRouteSession.approve()`.

Usa InferenceHub.infer_for_role() (ADR-016 + lazo 4 de roles) — la soul fija
un ROL (`preferred_model_role` del manifiesto), nunca un modelo concreto; el
Model Fabric/fallback chain resuelve. No usa `tools` (contrato:
`tools_allowed=[]`) ni escribe memoria (`memory_scope=[]`): es una consulta
de solo-lectura sobre los metadatos YA proyectados por
`atlas.api.missions.proposal_to_mission` — nunca el diff completo, coherente
con `privacy_boundary=EXTERNAL_REDACTED` del manifiesto.

Fail-open honesto (mismo patrón que
`atlas.core.self_maintenance.root_cause_classifier`): si el modelo no
responde o su salida no parsea/valida, el veredicto es `unknown`, JAMÁS se
disfraza de `no_objection` — fingir "sin objeción" ante un fallo real sería
peor que no tener soul."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from jsonschema import Draft202012Validator

from atlas.core.inference_hub import InferenceLevel, InferenceRequest, InferenceResponse

__all__ = [
    "DevilAdvocateVerdict",
    "load_manifest",
    "review_mission",
]

_PACKAGE_DIR = Path(__file__).resolve().parent
_MANIFEST_PATH = _PACKAGE_DIR / "devil_advocate_manifest.json"
_SYSTEM_PROMPT_PATH = _PACKAGE_DIR / "devil_advocate_system_prompt.md"

_VALID_VERDICTS = {"objection", "no_objection", "unknown"}

_manifest_cache: dict[str, Any] | None = None
_system_prompt_cache: str | None = None
_output_schema_cache: dict[str, Any] | None = None


def _find_repo_root() -> Path | None:
    """Localiza la raíz del repo buscando `schemas/` hacia arriba desde este
    fichero — robusto a dónde se ejecute pytest, sin depender de un número
    fijo de `.parent` (mismo problema que ATLAS_CORE_ROOT resuelve en
    Orchestrator, pero aquí no hace falta variable de entorno: el schema de
    salida vive siempre junto al código, no en el repo del usuario)."""
    for candidate in (_PACKAGE_DIR, *_PACKAGE_DIR.parents):
        if (candidate / "schemas" / "soul_manifest.schema.json").is_file():
            return candidate
    return None


def load_manifest() -> dict[str, Any]:
    """Manifiesto concreto de devil_advocate, cacheado tras la primera carga."""
    global _manifest_cache
    if _manifest_cache is None:
        _manifest_cache = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    return _manifest_cache


def _load_system_prompt() -> str:
    global _system_prompt_cache
    if _system_prompt_cache is None:
        _system_prompt_cache = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return _system_prompt_cache


def _load_output_schema() -> dict[str, Any] | None:
    """`None` si no se encuentra el repo (entorno raro) — la validación de
    salida es defensa en profundidad, no una dependencia dura: la soul no
    debe romper la ruta dorada por no encontrar el schema en disco."""
    global _output_schema_cache
    if _output_schema_cache is not None:
        return _output_schema_cache
    root = _find_repo_root()
    if root is None:
        return None
    manifest = load_manifest()
    schema_path = root / manifest["output_schema_ref"]
    if not schema_path.is_file():
        return None
    _output_schema_cache = json.loads(schema_path.read_text(encoding="utf-8"))
    return _output_schema_cache


@dataclass
class DevilAdvocateVerdict:
    """Veredicto de una revisión (`schemas/devil_advocate_verdict.schema.json`).
    Un veredicto NUNCA es una decisión — ver invariante D2 en el docstring
    del módulo."""

    soul_id: str
    mission_id: str
    verdict: str  # "objection" | "no_objection" | "unknown"
    reasoning: str
    confidence: float
    generated_at: str

    @property
    def objection(self) -> bool:
        return self.verdict == "objection"

    def to_dict(self) -> dict[str, Any]:
        return {
            "soul_id": self.soul_id,
            "mission_id": self.mission_id,
            "verdict": self.verdict,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "generated_at": self.generated_at,
        }


class _HubLike(Protocol):
    """Lo mínimo que `review_mission` necesita del hub — permite dobles de
    test sin depender de InferenceHub completo (mismo patrón que
    `_RunnerLike` en golden_route.py)."""

    def infer_for_role(self, role: str, request: InferenceRequest) -> InferenceResponse: ...


def _build_prompt(mission: dict[str, Any]) -> str:
    """Solo metadatos de la misión — nunca el diff completo (EXTERNAL_REDACTED)."""
    evidence = mission.get("evidence_bundle") or {}
    validation = evidence.get("validation")
    refs = evidence.get("refs") or []
    artifacts = mission.get("artifacts") or []
    lines = [
        f"intent: {mission.get('intent', '(sin intent)')}",
        f"risk: {mission.get('risk', 'unknown')}",
        f"origin: {mission.get('origin', 'unknown')}",
        f"state: {mission.get('state', 'unknown')}",
        f"artifacts: {', '.join(artifacts) or '(ninguno declarado)'}",
        f"validation: {validation if validation else 'sin validación ejecutada'}",
        f"evidence_refs: {', '.join(refs) or '(ninguna)'}",
    ]
    return "Misión a revisar (metadatos únicamente, sin diff completo):\n" + "\n".join(lines)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """Extrae el primer objeto JSON del texto del modelo. Tolerante a prosa
    alrededor; `None` si no parsea (fail-open aguas arriba, mismo patrón que
    `root_cause_classifier._parse_json_object`)."""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _unknown_verdict(mission: dict[str, Any], manifest: dict[str, Any], generated_at: str, *, reason: str) -> DevilAdvocateVerdict:
    return DevilAdvocateVerdict(
        soul_id=manifest["soul_id"],
        mission_id=str(mission.get("mission_id", "")),
        verdict="unknown",
        reasoning=f"La soul no pudo evaluar la misión: {reason}",
        confidence=0.0,
        generated_at=generated_at,
    )


def review_mission(
    mission: dict[str, Any],
    *,
    hub: _HubLike,
    now: datetime | None = None,
) -> DevilAdvocateVerdict:
    """Invoca devil_advocate sobre una misión ya proyectada (dict con la
    forma de `atlas.api.missions.proposal_to_mission`). Nunca lanza: ante
    cualquier fallo (excepción, error del proveedor, salida no parseable o
    fuera de vocabulario) devuelve un veredicto honesto `unknown` en vez de
    propagar o fingir `no_objection`."""
    manifest = load_manifest()
    generated_at = (now or datetime.now(timezone.utc)).isoformat()

    request = InferenceRequest(
        prompt=_build_prompt(mission),
        context=_load_system_prompt(),
        level=InferenceLevel.L1,
        temperature=0.0,
        max_tokens=400,
        task_id=str(mission.get("mission_id") or None) or None,
    )

    try:
        response = hub.infer_for_role(manifest["preferred_model_role"], request)
    except Exception as exc:  # noqa: BLE001 — la soul jamás crashea la ruta dorada
        return _unknown_verdict(mission, manifest, generated_at, reason=f"excepción al invocar el modelo: {exc}")

    if not response.success:
        return _unknown_verdict(mission, manifest, generated_at, reason=f"el modelo no respondió: {response.error}")

    data = _parse_json_object(response.text)
    if data is None:
        return _unknown_verdict(mission, manifest, generated_at, reason="la salida del modelo no es JSON parseable")

    verdict_value = data.get("verdict")
    if verdict_value not in _VALID_VERDICTS:
        return _unknown_verdict(
            mission, manifest, generated_at,
            reason=f"veredicto fuera de vocabulario: {verdict_value!r}",
        )

    reasoning = str(data.get("reasoning") or "").strip() or "(el modelo no declaró una razón)"
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    result = DevilAdvocateVerdict(
        soul_id=manifest["soul_id"],
        mission_id=str(mission.get("mission_id", "")),
        verdict=str(verdict_value),
        reasoning=reasoning,
        confidence=confidence,
        generated_at=generated_at,
    )

    schema = _load_output_schema()
    if schema is not None:
        errors = list(Draft202012Validator(schema).iter_errors(result.to_dict()))
        if errors:
            return _unknown_verdict(
                mission, manifest, generated_at,
                reason=f"la salida no cumple devil_advocate_verdict.schema.json: {errors[0].message}",
            )

    return result
