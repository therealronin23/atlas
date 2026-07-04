"""``TopicExpander`` -- amplia INTERESES amplios en consultas de busqueda
CONCRETAS y VARIADAS para ``PanoramaScout.discover()``.

Correccion del usuario, misma sesion que ``panorama_scout.py``: hoy
``PanoramaScout`` recibe una lista FIJA y literal de ``topics: list[str]`` --
"amplia tambien los patrones o terminos de busqueda para que no solo busque
una lista acotada de palabras, sino bastante mas libre". El ecosistema no es
una lista conocida -- puede ser un paper, un lenguaje nuevo, un SaaS sin
nombre todavia. Si ``PanoramaScout`` siempre busca las mismas 5-10 palabras
literales, nunca encuentra nada fuera de ese carril.

``TopicExpander`` resuelve esto con un paso previo: a partir de unos pocos
INTERESES AMPLIOS (ej. "memoria de agentes de IA", "orquestacion local",
"auditoria verificable de IA"), un LLM barato genera cada vez una lista de
consultas concretas y variadas -- angulos distintos, terminos adyacentes,
sinonimos tecnicos, nombres de tecnicas relacionadas -- para que
``PanoramaScout.discover()`` reciba topics distintos en cada ciclo, no
siempre los mismos.

Diferencia deliberada respecto a ``MaintenanceAnalyst`` (mismo estilo que
``DepAnalyst``, lease igual): aqui no hay prosa NO CONFIABLE que extraer de
una fuente externa -- es generacion creativa acotada por un contrato JSON
tipado. Un solo LLM de control basta, sin processing-LLM previo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from atlas.core.inference_hub import InferenceLevel, InferenceRequest

_EXPAND_INSTRUCTION_TEMPLATE = (
    "Genera EXACTAMENTE {n} consultas de búsqueda cortas y variadas "
    "relacionadas con el interés dado, explorando ángulos distintos, "
    "técnicas adyacentes, y términos técnicos relacionados -- NO repitas el "
    "mismo interés con sinónimos triviales. Responde SOLO un array JSON de "
    "strings, sin prosa."
)


@dataclass
class TopicExpansion:
    """Resultado de expandir UN seed concreto -- para auditoria/inspeccion
    via ``expand_detailed()``, no para el uso combinado normal."""

    seed: str
    queries: list[str] = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "queries": list(self.queries),
            "generated_at": self.generated_at,
        }


class TopicExpander:
    """Convierte intereses AMPLIOS en consultas de búsqueda CONCRETAS y
    VARIADAS, para que el descubrimiento (PanoramaScout) no repita siempre
    las mismas palabras literales — el ecosistema puede no tener nombre
    todavía, y una lista fija de topics nunca lo encontraría. Un solo LLM
    barato (no dual: no hay prosa no confiable que extraer, solo generación
    creativa acotada por JSON tipado)."""

    AGENT = "self_maintenance.topic_expander"

    def __init__(self, *, hub: Any, merkle: Any | None = None) -> None:
        self._hub = hub
        self._merkle = merkle

    def expand(self, seed_interests: list[str], *, queries_per_seed: int = 5) -> list[str]:
        """Por cada interés amplio en seed_interests, pide al LLM
        queries_per_seed consultas concretas y variadas (ángulos distintos,
        términos técnicos adyacentes, no sinónimos triviales del mismo
        string). Fail-open POR SEED: si el LLM falla o no parsea para un
        seed concreto, usa el propio seed como única query de ese seed (así
        el descubrimiento nunca se queda sin nada que buscar). Devuelve la
        lista COMBINADA y sin duplicados (preservando orden de aparición)
        de todas las queries de todos los seeds -- lista plana de str,
        compatible directa con PanoramaScout(topics=...)."""
        all_queries: list[str] = []
        seen: set[str] = set()
        for seed in seed_interests:
            expansion = self._expand_one(seed, queries_per_seed)
            for q in expansion.queries:
                if q not in seen:
                    seen.add(q)
                    all_queries.append(q)
        return all_queries

    def expand_detailed(self, seed_interests: list[str], *, queries_per_seed: int = 5) -> list[TopicExpansion]:
        """Como expand(), pero devuelve el detalle por seed (para auditoría/
        inspección), no solo la lista plana combinada."""
        return [self._expand_one(seed, queries_per_seed) for seed in seed_interests]

    def _expand_one(self, seed: str, queries_per_seed: int) -> TopicExpansion:
        request = InferenceRequest(
            prompt=seed,
            messages=[
                {"role": "system", "content": _EXPAND_INSTRUCTION_TEMPLATE.format(n=queries_per_seed)},
                {"role": "user", "content": seed},
            ],
            level=InferenceLevel.L1,
            task_id="topic_expander.expand",
        )
        try:
            response = self._hub.infer(request)
            queries = self._parse_json_array(response.text) if response.success else None
        except Exception:  # noqa: BLE001 -- fail-open: el seed mismo sigue siendo una query valida
            queries = None
        if not queries:
            queries = [seed]
        return TopicExpansion(seed=seed, queries=queries)

    def _parse_json_array(self, text: str) -> list[str] | None:
        """Extrae el primer array JSON del texto del modelo. Tolerante a
        prosa alrededor (igual que dep_analyst.py con objetos). Devuelve
        None si no hay array parseable o si los elementos no son todos
        str."""
        if not text:
            return None
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end < start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(parsed, list) or not parsed:
            return None
        if not all(isinstance(item, str) for item in parsed):
            return None
        return parsed
