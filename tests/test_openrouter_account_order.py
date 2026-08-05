"""
OpenRouter pasa a la cuenta 2 (2026-08-05, decisión del operador).

La cuenta 1 se quedó sin crédito: el lazo de autoconstrucción falló con
`402 - "You requested up to 4096 tokens, but can only afford 3767"`. El
operador tiene otra cuenta y pidió usarla.

**Cómo elige el hub, medido en el código**: `account_pool` se recorre en orden
y se toma **la primera variable que EXISTA en el entorno**, sin reintentar con
la siguiente si la llamada falla (`inference_hub.py`, ~línea 931). Con el orden
viejo —`["OPENROUTER_API_KEY", "OPENROUTER_API_KEY_2"]`— la clave 2 no se usaba
nunca mientras la 1 estuviera definida, por agotada que estuviese. Invertir el
orden es todo el cambio.

**Límite que esto NO arregla y conviene no olvidar**: como el pool no rota ante
un fallo, cuando la cuenta 2 se agote tampoco caerá a la 1. Sigue habiendo un
único punto de fallo por proveedor; lo que cambia es cuál.
"""

from __future__ import annotations

import pytest

from atlas.core.inference_hub import DEFAULT_PROVIDERS

OPENROUTER = [p for p in DEFAULT_PROVIDERS if p.name.startswith("openrouter")]


def test_there_are_openrouter_providers_to_check() -> None:
    """Si algún día no quedara ninguno, los tests de abajo pasarían vacíos."""
    assert OPENROUTER


@pytest.mark.parametrize("provider", OPENROUTER, ids=lambda p: p.name)
def test_account_two_is_tried_first(provider) -> None:  # noqa: ANN001
    assert provider.account_pool[0] == "OPENROUTER_API_KEY_2", (
        f"{provider.name} sigue prefiriendo la cuenta 1, que está sin crédito"
    )


@pytest.mark.parametrize("provider", OPENROUTER, ids=lambda p: p.name)
def test_account_one_is_kept_as_fallback(provider) -> None:
    """No se borra: si la 2 falta del entorno, la 1 sigue sirviendo. Quitarla
    convertiría un cambio de preferencia en una pérdida de capacidad."""
    assert "OPENROUTER_API_KEY" in provider.account_pool


class TestTheKeyActuallyReachesLitellm:
    def test_the_second_account_key_is_the_one_sent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prueba del MECANISMO, no del orden de una lista: sin esto, alguien
        podría reordenar el pool y que el hub siguiera mandando otra clave."""
        import litellm

        from atlas.core.inference_hub import (
            InferenceHub,
            InferenceLevel,
            InferenceRequest,
        )

        # Mismo patrón que los tests de rotación de NVIDIA: el hub mira
        # `PYTEST_CURRENT_TEST` para decidir live/stub, así que probar el
        # camino real exige quitarlo.
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "clave-cuenta-1-agotada")
        monkeypatch.setenv("OPENROUTER_API_KEY_2", "clave-cuenta-2")
        captured: dict[str, object] = {}

        def spy(**kwargs):  # noqa: ANN003, ANN202
            captured.update(kwargs)
            msg = type("M", (), {"content": "ok"})()
            choice = type("C", (), {"message": msg})()
            return type("R", (), {"choices": [choice], "usage": None})()

        monkeypatch.setattr(litellm, "completion", spy)

        provider = next(p for p in OPENROUTER if p.name == "openrouter_hermes4_70b")
        InferenceHub([provider], mode="live").infer(
            InferenceRequest(prompt="hola", level=provider.level, max_tokens=8)
        )

        assert captured.get("api_key") == "clave-cuenta-2"

    def test_falls_back_to_account_one_when_two_is_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import litellm

        from atlas.core.inference_hub import (
            InferenceHub,
            InferenceLevel,
            InferenceRequest,
        )

        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "clave-cuenta-1")
        monkeypatch.delenv("OPENROUTER_API_KEY_2", raising=False)
        captured: dict[str, object] = {}

        def spy(**kwargs):  # noqa: ANN003, ANN202
            captured.update(kwargs)
            msg = type("M", (), {"content": "ok"})()
            choice = type("C", (), {"message": msg})()
            return type("R", (), {"choices": [choice], "usage": None})()

        monkeypatch.setattr(litellm, "completion", spy)

        provider = next(p for p in OPENROUTER if p.name == "openrouter_hermes4_70b")
        InferenceHub([provider], mode="live").infer(
            InferenceRequest(prompt="hola", level=provider.level, max_tokens=8)
        )

        assert captured.get("api_key") == "clave-cuenta-1"
