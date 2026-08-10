"""Cuando la cadena entera falla, tiene que decir QUÉ dijo cada proveedor.

Medido el 2026-08-10, y costó horas de diagnóstico. El banco congelado dio
`atlas_toolcoder 0/5` en tres tiradas, 83,9 minutos, con una única causa
registrada quince veces:

    TimeoutError: hard timeout tras 300.0s (litellm no devolvió a tiempo)

Ese mensaje es cierto del ÚLTIMO proveedor de la cadena y **falso de lo que
realmente pasó**. Preguntando al proveedor directamente, sin el hub:

    RateLimitError: Rate limit reached for model `qwen/qwen3.6-27b` ...
    on tokens per day (TPD)                              ← en 0,1 segundos

El primer proveedor contestaba al instante y con un diagnóstico perfecto —cuota
diaria agotada—, se marcaba rate-limited, la cadena pasaba al siguiente, ése se
colgaba, y el `all_failed` propagaba SÓLO el error del último. La causa
accionable ("hoy ya no hay tokens de este modelo") quedaba tapada por una
inaccionable ("litellm no devolvió a tiempo"), que además culpa a la librería
que sí había respondido.

Es la familia de defecto que más veces ha salido en esta auditoría —un error
disfrazado de otra cosa— en el peor sitio posible: la ruta de inferencia del
lazo de autoconstrucción, donde nadie está mirando en directo.
"""

from __future__ import annotations

from typing import Any

import pytest

from atlas.core.inference_hub import (
    InferenceHub,
    InferenceLevel,
    InferenceRequest,
    InferenceResponse,
)


def _hub_con_fallos(monkeypatch: pytest.MonkeyPatch, fallos: dict[str, str]) -> InferenceHub:
    """Hub real cuyos proveedores fallan con el error que se le indique."""
    hub = InferenceHub(mode="stub")

    def _falso(provider: Any, request: Any) -> InferenceResponse:
        return InferenceResponse(
            text="", provider=provider.name, model=provider.model_id,
            level=request.level, latency_ms=0, success=False,
            error=fallos.get(provider.name, "fallo genérico"),
        )

    monkeypatch.setattr(hub, "_call_provider", _falso)
    return hub


def _peticion() -> InferenceRequest:
    return InferenceRequest(prompt="hola", level=InferenceLevel.L1, task_id="t")


def test_el_error_agregado_nombra_a_cada_proveedor(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = InferenceHub(mode="stub")
    nombres = [p.name for p in hub._providers][:2]
    if len(nombres) < 2:
        pytest.skip("catálogo con menos de dos proveedores")

    hub = _hub_con_fallos(monkeypatch, {
        nombres[0]: "RateLimitError: tokens per day (TPD) agotados",
        nombres[1]: "TimeoutError: hard timeout tras 300.0s",
    })

    respuesta = hub._walk_chain(_peticion())

    assert not respuesta.success
    assert respuesta.provider == "all_failed"
    assert nombres[0] in (respuesta.error or ""), respuesta.error
    assert "TPD" in (respuesta.error or ""), (
        "la causa accionable del PRIMER proveedor sigue tapada por la del último"
    )


def test_las_causas_viajan_estructuradas(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un string agregado sirve para leerlo; para decidir hace falta la lista.
    `FitnessScorer` y el lazo agrupan por causa, y no pueden parsear prosa."""
    hub = InferenceHub(mode="stub")
    nombres = [p.name for p in hub._providers][:2]
    if len(nombres) < 2:
        pytest.skip("catálogo con menos de dos proveedores")

    hub = _hub_con_fallos(monkeypatch, {nombres[0]: "RateLimitError: TPD"})

    respuesta = hub._walk_chain(_peticion())

    causas = dict(respuesta.chain_failures)
    assert causas.get(nombres[0], "").startswith("RateLimitError")
    assert len(respuesta.chain_failures) >= 2, "sólo registró un proveedor"


def test_el_agregado_no_crece_sin_freno(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con un catálogo de 14 proveedores, volcarlos todos con su traza haría el
    error ilegible y llenaría el ledger."""
    hub = _hub_con_fallos(monkeypatch, {})

    respuesta = hub._walk_chain(_peticion())

    assert len(respuesta.error or "") < 700, "el error agregado se desmadra"


def test_un_exito_no_arrastra_causas(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = InferenceHub(mode="stub")

    def _ok(provider: Any, request: Any) -> InferenceResponse:
        return InferenceResponse(
            text="listo", provider=provider.name, model=provider.model_id,
            level=request.level, latency_ms=1, success=True,
        )

    monkeypatch.setattr(hub, "_call_provider", _ok)

    respuesta = hub._walk_chain(_peticion())

    assert respuesta.success
    assert respuesta.chain_failures == ()


def test_la_clasificacion_del_ultimo_sigue_intacta(monkeypatch: pytest.MonkeyPatch) -> None:
    """El agregado AÑADE contexto; no puede quitar lo que ya se propagaba
    (`error_kind`, `retry_after_s`, `retryable`), de lo que dependen los
    reintentos."""
    hub = InferenceHub(mode="stub")

    def _falso(provider: Any, request: Any) -> InferenceResponse:
        return InferenceResponse(
            text="", provider=provider.name, model=provider.model_id,
            level=request.level, latency_ms=0, success=False,
            error="rate limited", error_kind="rate_limit", retry_after_s=42.0,
            retryable=True,
        )

    monkeypatch.setattr(hub, "_call_provider", _falso)

    respuesta = hub._walk_chain(_peticion())

    assert respuesta.error_kind == "rate_limit"
    assert respuesta.retry_after_s == 42.0
    assert respuesta.retryable is True
