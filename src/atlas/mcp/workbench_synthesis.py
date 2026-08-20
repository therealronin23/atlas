"""Síntesis Gemini de la mesa de trabajo (diseño 2026-07-25).

La primera vez que una sesión ve stale ``workbench://manifest`` (ver
``workbench_compliance.is_synthesis_due``), en vez de solo avisar, se hace
UNA llamada real a ``gemini_free`` -- proveedor dedicado y gratuito, sin
caminar la cadena de fallback de pago -- que lee el manifiesto completo y
devuelve un briefing curado sobre el objetivo declarado. Fail-soft en cada
punto: cualquier fallo (sin clave, rate-limit, timeout, manifiesto
inconstruible) cae a ``None`` para que quien llama use el aviso de texto
plano existente. Nunca lanza.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_MAX_BRIEFING_TOKENS = 400
_SYNTHESIS_TIMEOUT_S = 20.0


def build_synthesis_prompt(manifest_json: str, goal: str) -> str:
    return (
        "Eres el curador de la mesa de trabajo de Atlas. Con este "
        "manifiesto (catálogo+lecciones+backlog+memoria, JSON) y el "
        "objetivo declarado, escribe un briefing de máximo 6 líneas en "
        "español: qué capacidad relevante ya existe, qué falta, y una "
        f"recomendación concreta de por dónde empezar.\n\nObjetivo: {goal}"
        f"\n\nManifiesto:\n{manifest_json}"
    )


def synthesize_workbench_briefing(
    manifest_json: str,
    goal: str,
    *,
    infer_fn: Callable[[str], str | None],
) -> str | None:
    """Fail-soft: cualquier excepción de ``infer_fn``, o texto vacío, -> None."""
    if not manifest_json.strip():
        return None
    prompt = build_synthesis_prompt(manifest_json, goal)
    try:
        result = infer_fn(prompt)
    except Exception:  # noqa: BLE001 — nunca debe romper al llamador
        return None
    if not result or not result.strip():
        return None
    return result.strip()


def gemini_probe_infer_fn(hub: Any) -> Callable[[str], str | None]:
    """Adaptador real: ``gemini_free`` EN SOLITARIO vía
    ``InferenceHub.probe_provider`` -- nunca camina la cadena de fallback de
    pago, así que un fallo aquí jamás gasta presupuesto de otro proveedor."""
    from atlas.core.inference_hub import DEFAULT_PROVIDERS, InferenceRequest

    gemini = next((p for p in DEFAULT_PROVIDERS if p.name in {"gemini_free", "groq_gpt_oss_120b"}), None)

    def _call(prompt: str) -> str | None:
        if gemini is None:
            return None
        request = InferenceRequest(
            prompt=prompt,
            level=gemini.level,
            max_tokens=_MAX_BRIEFING_TOKENS,
            timeout_s=_SYNTHESIS_TIMEOUT_S,
        )
        response = hub.probe_provider(gemini, request)
        if not response.success:
            return None
        return str(response.text)

    return _call


def build_workbench_synth_fn(
    hub: Any, manifest_json_fn: Callable[[], str]
) -> Callable[[str], str | None]:
    """Compone la construcción perezosa del manifiesto (solo cuando hace
    falta) con la llamada a Gemini, en el ``synth_fn(goal)`` que espera
    ``workbench_compliance.check_and_maybe_synthesize``."""
    infer_fn = gemini_probe_infer_fn(hub)

    def _synth(goal: str) -> str | None:
        try:
            manifest_json = manifest_json_fn()
        except Exception:  # noqa: BLE001 — manifiesto inconstruible = fail-soft
            return None
        return synthesize_workbench_briefing(manifest_json, goal, infer_fn=infer_fn)

    return _synth
