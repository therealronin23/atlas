"""Fail-closed quality gate for deduplicated MCP discovery candidates."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable

from atlas.core.self_maintenance.research_digest import CandidateSuggestion
from atlas.mcp.catalog import CatalogEntry


@dataclass(frozen=True)
class JudgeContext:
    seed: str
    capability_summary: str


@dataclass(frozen=True)
class QualityVerdict:
    real_mantenido: bool
    relevante_al_seed: bool
    cubre_hueco_real: bool
    motivo: str = ""


JudgeFn = Callable[[CandidateSuggestion, JudgeContext], QualityVerdict]


def summarize_catalog_capabilities(catalog: list[CatalogEntry]) -> str:
    counts = Counter(entry.sector for entry in catalog if entry.status in {"instalado", "verificado"})
    return "; ".join(f"{sector}: {count}" for sector, count in sorted(counts.items())) or "sin capacidades catalogadas"


def build_llm_judge_fn(hub: Any) -> JudgeFn:
    """Build the production judge; malformed/failed LLM replies raise."""
    def judge(candidate: CandidateSuggestion, context: JudgeContext) -> QualityVerdict:
        from atlas.core.inference_hub import InferenceRequest
        prompt = (
            "Responde exactamente REAL: SI|NO, RELEVANTE: SI|NO y HUECO: SI|NO, "
            "una por línea. Candidato: {name} {url}. Seed: {seed}. Capacidades: {caps}."
        ).format(name=candidate.name, url=candidate.url, seed=context.seed or "sin seed", caps=context.capability_summary)
        response = hub.infer(InferenceRequest(prompt=prompt))
        if not response.success or not response.text.strip():
            raise RuntimeError("quality judge unavailable")
        flags: dict[str, bool] = {}
        for line in response.text.upper().splitlines():
            for label in ("REAL", "RELEVANTE", "HUECO"):
                if line.strip().startswith(f"{label}:"):
                    value = line.split(":", 1)[1].strip()
                    if value not in {"SI", "NO"}:
                        raise RuntimeError("malformed quality judge response")
                    flags[label] = value == "SI"
        if set(flags) != {"REAL", "RELEVANTE", "HUECO"}:
            raise RuntimeError("incomplete quality judge response")
        return QualityVerdict(flags["REAL"], flags["RELEVANTE"], flags["HUECO"], response.text.strip())
    return judge


def run_quality_gate(suggestions: list[CandidateSuggestion], *, capability_summary: str, judge_fn: JudgeFn) -> list[CandidateSuggestion]:
    """Keep only real, seed-relevant candidates; any judge error excludes."""
    kept: list[CandidateSuggestion] = []
    for candidate in suggestions:
        try:
            verdict = judge_fn(candidate, JudgeContext(candidate.seeds[0] if candidate.seeds else "", capability_summary))
        except Exception:  # noqa: BLE001 - gate must fail closed per candidate
            continue
        if verdict.real_mantenido and verdict.relevante_al_seed:
            kept.append(candidate)
    return kept
