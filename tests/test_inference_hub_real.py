"""
Tests del InferenceHub en modo "live" con litellm.completion mockeado.
Comprueba clasificacion de errores, fallback chain y cooldown.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import litellm  # type: ignore

from atlas.core.inference_hub import (
    DEFAULT_PROVIDERS,
    InferenceHub,
    InferenceLevel,
    InferenceRequest,
    Provider,
    ProviderStatus,
    RATE_LIMIT_COOLDOWN_S,
)
from atlas.logging.merkle_logger import MerkleLogger


def test_default_gemini_provider_uses_stable_model_id() -> None:
    gemini = next(p for p in DEFAULT_PROVIDERS if p.name == "gemini_free")
    assert gemini.model_id == "gemini-3.5-flash"
    assert gemini.litellm_model == "gemini/gemini-3.5-flash"
    assert not gemini.model_id.endswith("-latest")


def _ok_completion(text: str = "hola", tokens: int = 7) -> MagicMock:
    """Construye un mock de respuesta tipo ChatCompletion."""
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    usage = MagicMock()
    usage.total_tokens = tokens
    completion = MagicMock()
    completion.choices = [choice]
    completion.usage = usage
    return completion


def _providers_with_keys(monkeypatch: pytest.MonkeyPatch) -> list[Provider]:
    """Dos proveedores L1 que sí tienen sus keys en entorno."""
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-or")
    return [
        Provider(
            name="groq_test",
            level=InferenceLevel.L1,
            base_url="https://api.groq.com",
            model_id="llama-3.3-70b-versatile",
            litellm_model="groq/llama-3.3-70b-versatile",
            api_key_env="GROQ_API_KEY",
            context_tokens=32768,
        ),
        Provider(
            name="openrouter_test",
            level=InferenceLevel.L1,
            base_url="https://openrouter.ai/api/v1",
            model_id="meta-llama/llama-3.1-8b-instruct:free",
            litellm_model="openrouter/meta-llama/llama-3.1-8b-instruct:free",
            api_key_env="OPENROUTER_API_KEY",
            context_tokens=8192,
        ),
    ]


class TestLiveMode:

    def test_live_mode_calls_litellm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        providers = _providers_with_keys(monkeypatch)
        captured: dict[str, Any] = {}

        def fake_completion(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return _ok_completion(text="respuesta real")

        monkeypatch.setattr(litellm, "completion", fake_completion)
        hub = InferenceHub(providers=providers, mode="live")
        resp = hub.infer(InferenceRequest(prompt="hola", level=InferenceLevel.L1))

        assert resp.success is True
        assert resp.text == "respuesta real"
        assert resp.mode == "live"
        assert resp.tokens_used == 7
        assert captured["model"].startswith("groq/")
        assert captured["api_key"] == "test-groq"

    def test_live_mode_logs_model_calls_to_merkle(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        providers = _providers_with_keys(monkeypatch)

        def fake_completion(**kwargs: Any) -> Any:
            return _ok_completion(text="respuesta real")

        monkeypatch.setattr(litellm, "completion", fake_completion)
        merkle = MerkleLogger(tmp_path / "merkle")
        hub = InferenceHub(providers=providers, mode="live", merkle=merkle)
        resp = hub.infer(InferenceRequest(prompt="hola", level=InferenceLevel.L1))

        assert resp.success is True
        records = merkle.read_all()
        assert any(
            r.action == "model.called" and r.result == "success"
            and r.payload["provider"] == "groq_test"
            for r in records
        )

    def test_live_mode_logs_failures_to_merkle(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        providers = _providers_with_keys(monkeypatch)

        def fail_completion(**kwargs: Any) -> Any:
            raise RuntimeError("kaboom")

        monkeypatch.setattr(litellm, "completion", fail_completion)
        merkle = MerkleLogger(tmp_path / "merkle")
        hub = InferenceHub(providers=providers, mode="live", merkle=merkle)
        resp = hub.infer(InferenceRequest(prompt="hola", level=InferenceLevel.L1))

        assert resp.success is False
        records = merkle.read_all()
        assert any(
            r.action == "model.called" and r.result == "failed"
            and "error" in r.payload
            for r in records
        )

    def test_stub_mode_ignores_keys(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        providers = _providers_with_keys(monkeypatch)

        def boom(**kwargs: Any) -> Any:  # pragma: no cover — no debe llamarse
            raise AssertionError("litellm.completion no debe llamarse en stub")

        monkeypatch.setattr(litellm, "completion", boom)
        hub = InferenceHub(providers=providers, mode="stub")
        resp = hub.infer(InferenceRequest(prompt="hola", level=InferenceLevel.L1))

        assert resp.success is True
        assert resp.mode == "stub"
        assert "stub" in resp.text.lower()

    def test_auto_mode_in_pytest_falls_to_stub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        providers = _providers_with_keys(monkeypatch)
        monkeypatch.delenv("ATLAS_INFERENCE_MODE", raising=False)
        hub = InferenceHub(providers=providers, mode="auto")
        resp = hub.infer(InferenceRequest(prompt="x", level=InferenceLevel.L1))
        assert resp.mode == "stub"

    def test_auto_mode_outside_pytest_uses_live_when_key_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        providers = _providers_with_keys(monkeypatch)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        captured: dict[str, Any] = {}

        def fake_completion(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return _ok_completion(text="live auto")

        monkeypatch.setattr(litellm, "completion", fake_completion)
        hub = InferenceHub(providers=providers, mode="auto")
        resp = hub.infer(InferenceRequest(prompt="x", level=InferenceLevel.L1))

        assert resp.mode == "live"
        assert resp.success is True
        assert resp.text == "live auto"
        assert captured.get("api_key") == "test-groq"

    def test_auto_mode_outside_pytest_skips_without_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        providers = [
            Provider(
                name="groq_test",
                level=InferenceLevel.L1,
                base_url="https://api.groq.com",
                model_id="llama-3.3-70b-versatile",
                litellm_model="groq/llama-3.3-70b-versatile",
                api_key_env="GROQ_API_KEY",
                context_tokens=32768,
            )
        ]
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)

        hub = InferenceHub(providers=providers, mode="auto")
        resp = hub.infer(InferenceRequest(prompt="x", level=InferenceLevel.L1))

        assert resp.success is False
        assert resp.mode == "auto-skip"
        assert "sin key configurada" in (resp.error or "").lower()


class TestErrorClassification:

    def test_rate_limit_marks_provider_and_sets_cooldown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        providers = _providers_with_keys(monkeypatch)

        def always_rate_limit(**kwargs: Any) -> Any:
            raise litellm.RateLimitError(
                "rate limit hit", llm_provider="groq",
                model="llama-3.3-70b-versatile",
            )

        monkeypatch.setattr(litellm, "completion", always_rate_limit)
        hub = InferenceHub(providers=providers, mode="live")
        resp = hub.infer(InferenceRequest(prompt="x", level=InferenceLevel.L1))

        # Ambos proveedores rate-limited -> all_failed
        assert resp.success is False
        groq = next(p for p in hub._providers if p.name == "groq_test")
        assert groq.status == ProviderStatus.RATELIMITED
        cooldown = hub._rate_limited_until[groq.name]
        assert cooldown > 0
        # Cooldown del orden de RATE_LIMIT_COOLDOWN_S
        assert 0 < (cooldown - __import__("time").time()) <= RATE_LIMIT_COOLDOWN_S + 1

    def test_rate_limit_falls_back_to_next_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        providers = _providers_with_keys(monkeypatch)
        calls: list[str] = []

        def conditional(**kwargs: Any) -> Any:
            calls.append(kwargs["model"])
            if "groq" in kwargs["model"]:
                raise litellm.RateLimitError(
                    "rate", llm_provider="groq", model="x",
                )
            return _ok_completion(text="from openrouter")

        monkeypatch.setattr(litellm, "completion", conditional)
        hub = InferenceHub(providers=providers, mode="live")
        resp = hub.infer(InferenceRequest(prompt="x", level=InferenceLevel.L1))

        assert resp.success is True
        assert resp.provider == "openrouter_test"
        assert resp.text == "from openrouter"
        assert any("groq" in m for m in calls)
        assert any("openrouter" in m for m in calls)

    def test_auth_error_marks_provider_down(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        providers = _providers_with_keys(monkeypatch)

        def auth_fail(**kwargs: Any) -> Any:
            raise litellm.AuthenticationError(
                "bad key", llm_provider="groq", model="x",
            )

        monkeypatch.setattr(litellm, "completion", auth_fail)
        hub = InferenceHub(providers=providers[:1], mode="live")
        resp = hub.infer(InferenceRequest(prompt="x", level=InferenceLevel.L1))

        assert resp.success is False
        assert hub._providers[0].status == ProviderStatus.DOWN

    def test_generic_error_marks_provider_degraded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        providers = _providers_with_keys(monkeypatch)

        def fail(**kwargs: Any) -> Any:
            raise RuntimeError("kaboom")

        monkeypatch.setattr(litellm, "completion", fail)
        hub = InferenceHub(providers=providers[:1], mode="live")
        resp = hub.infer(InferenceRequest(prompt="x", level=InferenceLevel.L1))

        assert resp.success is False
        assert hub._providers[0].status == ProviderStatus.DEGRADED
        assert hub._providers[0].error_count >= 1


class TestRecovery:

    def test_success_resets_degraded_status(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        providers = _providers_with_keys(monkeypatch)
        providers[0].status = ProviderStatus.DEGRADED
        providers[0].error_count = 3

        monkeypatch.setattr(
            litellm, "completion",
            lambda **kw: _ok_completion(text="ok again"),
        )
        hub = InferenceHub(providers=providers[:1], mode="live")
        resp = hub.infer(InferenceRequest(prompt="x", level=InferenceLevel.L1))

        assert resp.success is True
        assert hub._providers[0].status == ProviderStatus.OK
        assert hub._providers[0].error_count == 0

    def test_providers_status_reports_rate_limit_seconds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        providers = _providers_with_keys(monkeypatch)
        monkeypatch.setattr(
            litellm, "completion",
            lambda **kw: (_ for _ in ()).throw(
                litellm.RateLimitError("rl", llm_provider="x", model="y")
            ),
        )
        hub = InferenceHub(providers=providers[:1], mode="live")
        hub.infer(InferenceRequest(prompt="x", level=InferenceLevel.L1))

        statuses = hub.providers_status()
        assert statuses[0]["status"] == "rate_limited"
        assert statuses[0]["rate_limited_for_s"] > 0

    def test_providers_status_reports_last_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        providers = _providers_with_keys(monkeypatch)

        monkeypatch.setattr(
            litellm, "completion",
            lambda **kw: _ok_completion(text="ok again"),
        )
        hub = InferenceHub(providers=providers[:1], mode="live")
        hub.infer(InferenceRequest(prompt="x", level=InferenceLevel.L1))

        statuses = hub.providers_status()
        assert statuses[0]["last_used"] is not None
        assert statuses[0]["last_used"] != ""


# ===========================================================================
# L0 Ollama real — FU-4
# ===========================================================================


def _ollama_provider() -> Provider:
    from atlas.core.inference_hub import InferenceLevel
    return Provider(
        name="ollama_local",
        level=InferenceLevel.L0,
        base_url="http://localhost:11434",
        model_id="qwen2.5-coder:7b",
        litellm_model="ollama/qwen2.5-coder:7b",
        api_key_env=None,
        rpm_limit=999,
        context_tokens=8192,
    )


class TestOllamaL0:
    """FU-4 — L0 Ollama HTTP: comportamiento sin API key, api_base, fallback."""

    def test_resolve_live_for_ollama_returns_true_outside_pytest(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sin api_key_env, _resolve_live_for debe devolver True fuera de pytest."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        hub = InferenceHub(providers=[_ollama_provider()], mode="auto")
        assert hub._resolve_live_for(_ollama_provider()) is True

    def test_resolve_live_for_ollama_returns_false_in_pytest(self) -> None:
        """Dentro de pytest (PYTEST_CURRENT_TEST set), siempre stub."""
        hub = InferenceHub(providers=[_ollama_provider()], mode="auto")
        # PYTEST_CURRENT_TEST esta seteado porque estamos en pytest
        assert hub._resolve_live_for(_ollama_provider()) is False

    def test_ollama_passes_api_base_to_litellm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_call_provider_real debe pasar api_base=base_url y api_key='ollama'."""
        captured: dict = {}

        def fake_completion(**kw: Any) -> Any:
            captured.update(kw)
            return _ok_completion("respuesta local")

        monkeypatch.setattr(litellm, "completion", fake_completion)
        hub = InferenceHub(providers=[_ollama_provider()], mode="live")
        hub.infer(InferenceRequest(prompt="test", level=InferenceLevel.L0))

        assert captured.get("api_base") == "http://localhost:11434"
        assert captured.get("api_key") == "ollama"
        assert captured.get("model") == "ollama/qwen2.5-coder:7b"

    def test_ollama_connection_refused_marks_provider_degraded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Si Ollama no responde, el provider queda DEGRADED y infer devuelve error."""
        import urllib.error

        def fail_completion(**kw: Any) -> Any:
            raise ConnectionRefusedError("Connection refused localhost:11434")

        monkeypatch.setattr(litellm, "completion", fail_completion)
        provider = _ollama_provider()
        hub = InferenceHub(providers=[provider], mode="live")
        resp = hub.infer(InferenceRequest(prompt="test", level=InferenceLevel.L0))

        assert resp.success is False
        assert provider.status == ProviderStatus.DEGRADED

    def test_l1_fallback_uses_l0_when_all_l1_fail(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """infer(L1) con L1 caidos debe intentar L0 (Ollama) como ultimo recurso."""
        from atlas.core.inference_hub import InferenceLevel
        call_counts: dict[str, int] = {}

        def selective_completion(**kw: Any) -> Any:
            model = kw.get("model", "")
            call_counts[model] = call_counts.get(model, 0) + 1
            if "ollama" in model:
                return _ok_completion("respuesta L0")
            raise ConnectionRefusedError("L1 no disponible")

        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setattr(litellm, "completion", selective_completion)
        l1_provider = Provider(
            name="groq_test", level=InferenceLevel.L1,
            base_url="https://api.groq.com", model_id="llama",
            litellm_model="groq/llama", api_key_env="GROQ_API_KEY",
        )
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        hub = InferenceHub(providers=[l1_provider, _ollama_provider()], mode="auto")
        resp = hub.infer(InferenceRequest(prompt="test", level=InferenceLevel.L1))

        assert resp.success is True
        assert resp.provider == "ollama_local"
        assert resp.text == "respuesta L0"


# ---------------------------------------------------------------------------
# Tests NVIDIA NIM frontier (L2)
# ---------------------------------------------------------------------------

class TestNvidiaNimProvider:

    def test_nvidia_provider_in_default_providers(self) -> None:
        """nvidia_llama_large debe estar en DEFAULT_PROVIDERS con campos correctos."""
        nvidia = next((p for p in DEFAULT_PROVIDERS if p.name == "nvidia_llama_large"), None)
        assert nvidia is not None, "nvidia_llama_large no encontrado en DEFAULT_PROVIDERS"
        assert nvidia.level == InferenceLevel.L2
        assert nvidia.litellm_model == "nvidia_nim/meta/llama-3.1-405b-instruct"
        assert nvidia.model_id == "meta/llama-3.1-405b-instruct"
        assert nvidia.base_url == "https://integrate.api.nvidia.com/v1"
        assert nvidia.api_key_env == "NVIDIA_API_KEY"
        assert nvidia.account_pool == ["NVIDIA_API_KEY", "NVIDIA_API_KEY_2"]
        assert len(nvidia.account_pool) == 2

    def test_nvidia_resolve_live_with_primary_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Hub considera NVIDIA disponible cuando NVIDIA_API_KEY está en entorno."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("NVIDIA_API_KEY", "test-nvidia-key")
        nvidia = next(p for p in DEFAULT_PROVIDERS if p.name == "nvidia_llama_large")
        # Clonar para no mutar el singleton
        import copy
        prov = copy.copy(nvidia)
        hub = InferenceHub(providers=[prov], mode="auto")
        assert hub._resolve_live_for(prov) is True

    def test_nvidia_resolve_live_with_secondary_key_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Hub considera NVIDIA disponible cuando solo NVIDIA_API_KEY_2 está en entorno."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        monkeypatch.setenv("NVIDIA_API_KEY_2", "test-nvidia-key-2")
        nvidia = next(p for p in DEFAULT_PROVIDERS if p.name == "nvidia_llama_large")
        import copy
        prov = copy.copy(nvidia)
        hub = InferenceHub(providers=[prov], mode="auto")
        assert hub._resolve_live_for(prov) is True

    def test_nvidia_resolve_live_false_without_keys(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Hub no activa NVIDIA si ninguna clave del pool está en entorno."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        monkeypatch.delenv("NVIDIA_API_KEY_2", raising=False)
        nvidia = next(p for p in DEFAULT_PROVIDERS if p.name == "nvidia_llama_large")
        import copy
        prov = copy.copy(nvidia)
        hub = InferenceHub(providers=[prov], mode="auto")
        assert hub._resolve_live_for(prov) is False

    def test_nvidia_uses_primary_key_in_litellm_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cuando NVIDIA_API_KEY está seteada, se pasa al litellm.completion."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("NVIDIA_API_KEY", "primary-nvidia-key")
        monkeypatch.delenv("NVIDIA_API_KEY_2", raising=False)

        captured: dict[str, Any] = {}

        def mock_completion(**kw: Any) -> Any:
            captured.update(kw)
            return _ok_completion("nvidia response")

        monkeypatch.setattr(litellm, "completion", mock_completion)

        nvidia = next(p for p in DEFAULT_PROVIDERS if p.name == "nvidia_llama_large")
        import copy
        prov = copy.copy(nvidia)
        hub = InferenceHub(providers=[prov], mode="auto")
        resp = hub.infer(InferenceRequest(prompt="hello", level=InferenceLevel.L2))

        assert resp.success is True
        assert captured.get("api_key") == "primary-nvidia-key"

    def test_nvidia_uses_secondary_key_when_primary_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cuando solo NVIDIA_API_KEY_2 existe, se usa esa clave en litellm."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        monkeypatch.setenv("NVIDIA_API_KEY_2", "secondary-nvidia-key")

        captured: dict[str, Any] = {}

        def mock_completion(**kw: Any) -> Any:
            captured.update(kw)
            return _ok_completion("nvidia secondary response")

        monkeypatch.setattr(litellm, "completion", mock_completion)

        nvidia = next(p for p in DEFAULT_PROVIDERS if p.name == "nvidia_llama_large")
        import copy
        prov = copy.copy(nvidia)
        hub = InferenceHub(providers=[prov], mode="auto")
        resp = hub.infer(InferenceRequest(prompt="hello", level=InferenceLevel.L2))

        assert resp.success is True
        assert captured.get("api_key") == "secondary-nvidia-key"
