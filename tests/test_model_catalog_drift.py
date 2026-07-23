"""Tests de ModelCatalogDrift -- deriva lista-fija vs catálogo servido.

Contexto (plan 2026-07-23-t5-provider-discovery-plan.md, T4): DEFAULT_PROVIDERS
fija `model_id` a mano; ModelCatalogDrift cruza ese id configurado contra el
catálogo que el proveedor sirve AHORA (vía `discover_available_models`, T3)
para predecir un futuro 404/410 (modelo decomisionado/renombrado) ANTES de
gastarlo en una llamada real de inferencia -- exactamente la clase de fallo
que ya mordió a la cadena (qwen3-coder 410, kimi 404, deepseek decomisionado,
ver comentarios en DEFAULT_PROVIDERS).

`discover` es inyectable a propósito (mismo patrón `http_get` de T3): ningún
test de este fichero toca red real ni importa litellm.
"""

from __future__ import annotations

from atlas.core.inference_hub import InferenceLevel, Provider
from atlas.core.provider_discovery import DiscoveryResult
from atlas.core.self_maintenance.model_catalog_drift import (
    CatalogDriftResult,
    ModelCatalogDrift,
)


def _provider(
    name: str = "p1",
    model_id: str = "llama-3.3-70b-versatile",
) -> Provider:
    return Provider(
        name=name,
        level=InferenceLevel.L1,
        base_url="https://example.invalid",
        model_id=model_id,
        litellm_model=f"prov/{model_id}",
        api_key_env="X_API_KEY",
    )


def _ok_discovery(provider_name: str, model_ids: list[str]) -> DiscoveryResult:
    return DiscoveryResult(
        provider_name=provider_name,
        outcome="ok",
        model_ids=model_ids,
        reason="",
    )


def _skipped_discovery(provider_name: str, reason: str = "X_API_KEY no configurada") -> DiscoveryResult:
    return DiscoveryResult(
        provider_name=provider_name,
        outcome="skipped",
        model_ids=[],
        reason=reason,
    )


# --- present -------------------------------------------------------------


def test_run_marks_present_when_configured_model_is_in_served_catalog() -> None:
    provider = _provider(model_id="llama-3.3-70b-versatile")

    def discover(p: Provider) -> DiscoveryResult:
        return _ok_discovery(p.name, ["llama-3.3-70b-versatile", "other-model"])

    drift = ModelCatalogDrift(providers=[provider], discover=discover)
    results = drift.run()

    assert len(results) == 1
    result = results[0]
    assert isinstance(result, CatalogDriftResult)
    assert result.provider_name == "p1"
    assert result.configured_model == "llama-3.3-70b-versatile"
    assert result.outcome == "present"
    assert result.present is True


# --- missing ---------------------------------------------------------------


def test_run_marks_missing_when_configured_model_absent_from_served_catalog() -> None:
    provider = _provider(name="dead_model_provider", model_id="deepseek-r1-distill-llama-70b")

    def discover(p: Provider) -> DiscoveryResult:
        return _ok_discovery(p.name, ["llama-3.3-70b-versatile", "some-other-model"])

    drift = ModelCatalogDrift(providers=[provider], discover=discover)
    results = drift.run()

    assert len(results) == 1
    result = results[0]
    assert result.outcome == "missing"
    assert result.present is False
    assert "deepseek-r1-distill-llama-70b" in result.reason


def test_fixture_with_one_absent_model_produces_exactly_one_missing() -> None:
    """Fixture con 3 proveedores: 2 presentes, 1 ausente a propósito -> el
    drift debe producir EXACTAMENTE un 'missing', ni más ni menos."""
    alive_a = _provider(name="alive_a", model_id="model-a")
    alive_b = _provider(name="alive_b", model_id="model-b")
    dead = _provider(name="dead_one", model_id="model-decommissioned")

    catalogs = {
        "alive_a": ["model-a", "model-x"],
        "alive_b": ["model-b", "model-y"],
        "dead_one": ["model-z"],  # model-decommissioned ya no está
    }

    def discover(p: Provider) -> DiscoveryResult:
        return _ok_discovery(p.name, catalogs[p.name])

    drift = ModelCatalogDrift(providers=[alive_a, alive_b, dead], discover=discover)
    results = drift.run()

    missing = [r for r in results if r.outcome == "missing"]
    present = [r for r in results if r.outcome == "present"]
    assert len(results) == 3
    assert len(missing) == 1
    assert missing[0].provider_name == "dead_one"
    assert len(present) == 2


# --- skipped (discovery no comprobable) -------------------------------------


def test_run_marks_skipped_when_discovery_is_skipped() -> None:
    provider = _provider(name="no_key_provider")

    def discover(p: Provider) -> DiscoveryResult:
        return _skipped_discovery(p.name)

    drift = ModelCatalogDrift(providers=[provider], discover=discover)
    results = drift.run()

    assert len(results) == 1
    result = results[0]
    assert result.outcome == "skipped"
    assert result.present is None
    assert result.reason  # trae explicación, nunca vacío


def test_run_marks_skipped_when_discovery_is_unreachable() -> None:
    provider = _provider(name="down_provider")

    def discover(p: Provider) -> DiscoveryResult:
        return DiscoveryResult(
            provider_name=p.name,
            outcome="unreachable",
            model_ids=[],
            reason="timed out",
        )

    drift = ModelCatalogDrift(providers=[provider], discover=discover)
    results = drift.run()

    assert results[0].outcome == "skipped"
    assert results[0].present is None


def test_run_marks_skipped_when_discovery_is_auth_failed() -> None:
    provider = _provider(name="bad_key_provider")

    def discover(p: Provider) -> DiscoveryResult:
        return DiscoveryResult(
            provider_name=p.name,
            outcome="auth_failed",
            model_ids=[],
            reason="HTTP 401",
        )

    drift = ModelCatalogDrift(providers=[provider], discover=discover)
    results = drift.run()

    assert results[0].outcome == "skipped"
    assert results[0].present is None


# --- normalización de sufijos cosméticos (':free' de OpenRouter) -----------


def test_run_normalizes_openrouter_free_suffix_present_when_served_without_suffix() -> None:
    """DEFAULT_PROVIDERS real fija model_id con ':free' (ej.
    'nvidia/nemotron-nano-12b-v2-vl:free') pero el catálogo servido por
    OpenRouter puede listar el id sin el sufijo -- no debe ser falso 'missing'."""
    provider = _provider(
        name="openrouter_nemotron",
        model_id="nvidia/nemotron-nano-12b-v2-vl:free",
    )

    def discover(p: Provider) -> DiscoveryResult:
        return _ok_discovery(p.name, ["nvidia/nemotron-nano-12b-v2-vl"])

    drift = ModelCatalogDrift(providers=[provider], discover=discover)
    results = drift.run()

    assert results[0].outcome == "present"
    assert results[0].present is True


def test_run_normalizes_openrouter_free_suffix_present_when_served_with_suffix() -> None:
    provider = _provider(
        name="openrouter_nemotron_ultra",
        model_id="nvidia/nemotron-3-ultra-550b-a55b:free",
    )

    def discover(p: Provider) -> DiscoveryResult:
        return _ok_discovery(p.name, ["nvidia/nemotron-3-ultra-550b-a55b:free"])

    drift = ModelCatalogDrift(providers=[provider], discover=discover)
    results = drift.run()

    assert results[0].outcome == "present"


def test_run_does_not_strip_ollama_tag_colon() -> None:
    """Ollama usa ':' para el tag real de versión (ej. 'qwen2.5-coder:7b'),
    NO es un sufijo cosmético -- normalizar no debe fusionarlo con otro tag
    del mismo modelo base."""
    provider = _provider(name="ollama_local", model_id="qwen2.5-coder:7b")

    def discover(p: Provider) -> DiscoveryResult:
        # el catálogo solo sirve otro tag del mismo modelo base -- debe seguir
        # siendo 'missing' porque ':7b' no es cosmético como ':free'.
        return _ok_discovery(p.name, ["qwen2.5-coder:14b"])

    drift = ModelCatalogDrift(providers=[provider], discover=discover)
    results = drift.run()

    assert results[0].outcome == "missing"


# --- default providers / discover -------------------------------------------


def test_default_providers_is_default_providers_list() -> None:
    from atlas.core.inference_hub import DEFAULT_PROVIDERS

    drift = ModelCatalogDrift(discover=lambda p: _ok_discovery(p.name, [p.model_id]))
    results = drift.run()

    assert len(results) == len(DEFAULT_PROVIDERS)


def test_discover_default_is_discover_available_models() -> None:
    import inspect

    from atlas.core.provider_discovery import discover_available_models

    sig = inspect.signature(ModelCatalogDrift.__init__)
    assert sig.parameters["discover"].default is discover_available_models
