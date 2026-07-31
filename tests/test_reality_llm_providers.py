"""`atlas reality` subreportaba proveedores LLM (2026-07-31).

Lo destapó el operador preguntando "¿no está NVIDIA?". Estaba: dos claves en
`.env` (`NVIDIA_API_KEY`, `NVIDIA_API_KEY_2`) y funcionando de verdad — el
Cónclave de esa misma tarde usó `nvidia_mistral_large` como una de sus tres
voces. Lo que fallaba era el REPORTE.

`_llm_state()` tenía una lista ESCRITA A MANO de cuatro proveedores (groq,
openrouter, gemini, together) mientras el catálogo real (`DEFAULT_PROVIDERS`)
tiene 14 entradas, cinco de ellas NVIDIA. La lista se quedó atrás y nadie lo
notó.

Segundo defecto en la misma función: comprobaba `TOGETHER_API_KEY`, pero el
catálogo declara `TOGETHERAI_API_KEY`. La entrada de Together no podía dar
positivo nunca.

Es la misma clase de fallo que el `.env` no cargado de esa mañana: **el
comando que AGENTS.md manda usar para afirmar estado, mentía**. Por eso el
arreglo DERIVA del catálogo en vez de añadir "nvidia" a mano — si no, dentro
de dos meses estamos igual con el siguiente proveedor.
"""

from __future__ import annotations

import pytest

from atlas.core.inference_hub import Provider
from atlas.core.reality import _llm_state

_ALL_KEYS = (
    "GROQ_API_KEY", "OPENROUTER_API_KEY", "OPENROUTER_API_KEY_2",
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "TOGETHERAI_API_KEY",
    "TOGETHER_API_KEY", "NVIDIA_API_KEY", "NVIDIA_API_KEY_2",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ALL_KEYS:
        monkeypatch.delenv(key, raising=False)


def _provider(name: str, env: str | None) -> Provider:
    return Provider(
        name=name, level=1, base_url="https://x", model_id="m", api_key_env=env
    )


class TestDerivesFromTheCatalogNotAHardcodedList:
    def test_nvidia_is_reported_when_its_key_is_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """EL caso que lo destapó: 2 claves NVIDIA y `reality` no lo listaba."""
        monkeypatch.setenv("NVIDIA_API_KEY", "x")

        state = _llm_state()

        assert "nvidia" in state["configured_providers"]

    def test_a_new_provider_family_needs_no_change_here(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # La prueba de que se DERIVA: una familia que no existe en ninguna
        # lista escrita a mano debe reportarse igual.
        monkeypatch.setenv("ACME_API_KEY", "x")

        state = _llm_state(providers=[_provider("acme_turbo", "ACME_API_KEY")])

        assert state["configured_providers"] == ["acme"]

    def test_together_uses_the_env_var_the_catalog_declares(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # El catálogo declara TOGETHERAI_API_KEY; la lista vieja miraba
        # TOGETHER_API_KEY, así que nunca daba positivo.
        monkeypatch.setenv("TOGETHERAI_API_KEY", "x")

        assert "together" in _llm_state()["configured_providers"]


class TestAbsentKeysAreNotReported:
    def test_no_keys_means_no_providers(self) -> None:
        state = _llm_state()

        assert state["configured_providers"] == []
        assert state["status"] == "stub_or_local"

    def test_a_provider_without_its_key_is_not_listed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GROQ_API_KEY", "x")

        state = _llm_state()

        assert "groq" in state["configured_providers"]
        assert "nvidia" not in state["configured_providers"]


class TestAccountPools:
    def test_a_secondary_pool_key_alone_still_counts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # `OPENROUTER_API_KEY_2` está en el `account_pool` de 4 proveedores.
        # Si sólo estuviera la secundaria, el proveedor SIGUE usable.
        monkeypatch.setenv("OPENROUTER_API_KEY_2", "x")

        state = _llm_state(
            providers=[
                Provider(
                    name="openrouter_x", level=1, base_url="https://x", model_id="m",
                    api_key_env="OPENROUTER_API_KEY",
                    account_pool=["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_2"],
                )
            ]
        )

        assert state["configured_providers"] == ["openrouter"]


class TestLocalProvidersAreNotKeyed:
    def test_a_provider_without_api_key_env_is_not_a_configured_key(self) -> None:
        # Ollama tiene api_key_env=None: es local, no una credencial ausente.
        state = _llm_state(providers=[_provider("ollama_local", None)])

        assert state["configured_providers"] == []
