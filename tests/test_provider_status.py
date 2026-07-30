"""Tests de provider_status -- páginas de estado públicas de cada proveedor.

Contexto (2026-07-30, pedido directo del operador: "deberíamos estar
sincronizados... con la URL de estado de la red por si reportan caídas, es
una llamada rápida y barata"). Complementa a `provider_discovery.py` (qué
modelos sirve) con "¿el proveedor mismo reporta una incidencia ahora?" --
mismo principio: cero inferencia, http_get inyectable, ningún test toca red
real. URLs verificadas EN VIVO el 2026-07-30 antes de escribir este módulo
(nunca adivinadas): groqstatus.com/api/v1/summary (incident.io),
status.together.ai/index.json (Betterstack JSON:API), status.cloud.google.com
/incidents.json (feed propio de Google). OpenRouter (SPA tras reto
Cloudflare) y NVIDIA NIM (sin página de estado dedicada) no tienen endpoint
público fiable -- se declaran, no se omiten en silencio.
"""

from __future__ import annotations

from typing import Any

import pytest

from atlas.core.inference_hub import InferenceLevel, Provider
from atlas.core.provider_status import (
    StatusResult,
    check_provider_status,
    status_vendor,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload

    @property
    def text(self) -> str:
        return self._payload if isinstance(self._payload, str) else ""


def _groq_provider(name: str = "groq_llama_70b") -> Provider:
    return Provider(
        name=name,
        level=InferenceLevel.L1,
        base_url="https://api.groq.com",
        model_id="llama-3.3-70b-versatile",
        litellm_model="groq/llama-3.3-70b-versatile",
        api_key_env="GROQ_API_KEY",
    )


def _together_provider() -> Provider:
    return Provider(
        name="together_free",
        level=InferenceLevel.L1,
        base_url="https://api.together.xyz/v1",
        model_id="meta-llama/Llama-3-8b-chat-hf",
        litellm_model="together_ai/meta-llama/Llama-3-8b-chat-hf",
        api_key_env="TOGETHERAI_API_KEY",
    )


def _gemini_provider() -> Provider:
    return Provider(
        name="gemini_free",
        level=InferenceLevel.L0,
        base_url="https://generativelanguage.googleapis.com",
        model_id="gemini-2.5-flash",
        litellm_model="gemini/gemini-2.5-flash",
        api_key_env="GEMINI_API_KEY",
    )


def _openrouter_provider() -> Provider:
    return Provider(
        name="openrouter_nemotron",
        level=InferenceLevel.L1,
        base_url="https://openrouter.ai/api/v1",
        model_id="nvidia/nemotron-nano-12b-v2-vl:free",
        litellm_model="openrouter/nvidia/nemotron-nano-12b-v2-vl:free",
        api_key_env="OPENROUTER_API_KEY",
    )


def _nvidia_provider() -> Provider:
    return Provider(
        name="nvidia_llama_large",
        level=InferenceLevel.L2,
        base_url="https://integrate.api.nvidia.com/v1",
        model_id="meta/llama-3.3-70b-instruct",
        litellm_model="nvidia_nim/meta/llama-3.3-70b-instruct",
        api_key_env="NVIDIA_API_KEY",
    )


def _ollama_provider() -> Provider:
    return Provider(
        name="ollama_local",
        level=InferenceLevel.L0,
        base_url="http://127.0.0.1:11434",
        model_id="qwen2.5-coder:7b",
        litellm_model="ollama/qwen2.5-coder:7b",
        api_key_env=None,
    )


# --- status_vendor -----------------------------------------------------


def test_status_vendor_groq() -> None:
    assert status_vendor(_groq_provider()) == "groq"


def test_status_vendor_together() -> None:
    assert status_vendor(_together_provider()) == "together"


def test_status_vendor_google() -> None:
    assert status_vendor(_gemini_provider()) == "google"


def test_status_vendor_openrouter_is_recognized() -> None:
    assert status_vendor(_openrouter_provider()) == "openrouter"


def test_status_vendor_nvidia_is_recognized_but_unmonitored() -> None:
    """Sin página de estado dedicada encontrada para NIM/build.nvidia.com."""
    assert status_vendor(_nvidia_provider()) == "nvidia"


def test_status_vendor_ollama_is_local_not_external() -> None:
    assert status_vendor(_ollama_provider()) is None


# --- check_provider_status: dedupe por vendor ---------------------------


def test_dedupes_same_vendor_across_multiple_providers() -> None:
    """3 providers Groq (mismo vendor) -> UNA sola llamada HTTP, no 3."""
    calls: list[str] = []

    def fake_http_get(url: str, **_: Any) -> _FakeResponse:
        calls.append(url)
        return _FakeResponse(200, {"ongoing_incidents": [], "in_progress_maintenances": []})

    providers = [_groq_provider("groq_llama_70b"), _groq_provider("groq_compound"), _groq_provider("groq_qwen3")]
    results = check_provider_status(providers, http_get=fake_http_get)

    assert len(calls) == 1
    assert len([r for r in results if r.vendor == "groq"]) == 1


def test_nvidia_is_declared_not_silently_skipped() -> None:
    """NVIDIA sigue sin página de estado dedicada tras dos búsquedas
    (2026-07-30) -- se declara, no se omite en silencio."""
    providers = [_nvidia_provider(), _ollama_provider()]
    results = check_provider_status(
        providers,
        http_get=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debería llamar a red")),
        rss_get=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debería llamar a red")),
    )

    outcomes = {r.vendor: r.outcome for r in results}
    assert outcomes["nvidia"] == "no_public_status_page"
    assert "ollama" not in outcomes  # local, ni siquiera se declara como "no monitorizado"


# --- OpenRouter (feed RSS de suscripción, status.openrouter.ai/incidents.rss) ----
# 2026-07-30: la página web es una SPA tras reto de Cloudflare, sin JSON. Su
# MECANISMO DE SUSCRIPCIÓN documentado (RSS) sí responde limpio, sin reto,
# verificado en vivo con curl real -- esto es usar el endpoint que la propia
# página ofrece para monitorización programática, no sortear el bot-detection.

_OPENROUTER_RESOLVED_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item><title>Erroneous outage status</title>
<description><![CDATA[<p><small>Jul 23, 9:17 PM UTC</small><br/><strong>RESOLVED</strong> - <p>Todo bien.</p></p>]]></description>
<pubDate>Thu, 23 Jul 2026 21:17:36 GMT</pubDate></item>
</channel></rss>"""

_OPENROUTER_OPEN_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item><title>Elevated error rates</title>
<description><![CDATA[<p><small>Jul 30, 2:00 PM UTC</small><br/><strong>INVESTIGATING</strong> - <p>Estamos investigando.</p></p>]]></description>
<pubDate>Thu, 30 Jul 2026 14:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_openrouter_operational_when_latest_incident_resolved() -> None:
    def fake_rss_get(url: str, **_: Any) -> _FakeResponse:
        assert url == "https://status.openrouter.ai/incidents.rss"
        return _FakeResponse(200, _OPENROUTER_RESOLVED_RSS)

    [result] = check_provider_status([_openrouter_provider()], rss_get=fake_rss_get)
    assert result.outcome == "ok"
    assert result.state == "operational"


def test_openrouter_degraded_when_latest_incident_open() -> None:
    def fake_rss_get(url: str, **_: Any) -> _FakeResponse:
        return _FakeResponse(200, _OPENROUTER_OPEN_RSS)

    [result] = check_provider_status([_openrouter_provider()], rss_get=fake_rss_get)
    assert result.state == "degraded"
    assert "INVESTIGATING" in result.reason or "Elevated error rates" in result.reason


def test_openrouter_operational_when_feed_empty() -> None:
    empty = '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'

    def fake_rss_get(url: str, **_: Any) -> _FakeResponse:
        return _FakeResponse(200, empty)

    [result] = check_provider_status([_openrouter_provider()], rss_get=fake_rss_get)
    assert result.state == "operational"


def test_openrouter_unreachable_never_raises() -> None:
    def fake_rss_get(url: str, **_: Any) -> Any:
        raise TimeoutError("boom")

    [result] = check_provider_status([_openrouter_provider()], rss_get=fake_rss_get)
    assert result.outcome == "unreachable"


def test_openrouter_malformed_xml_never_raises() -> None:
    def fake_rss_get(url: str, **_: Any) -> _FakeResponse:
        return _FakeResponse(200, "no es xml")

    [result] = check_provider_status([_openrouter_provider()], rss_get=fake_rss_get)
    assert result.outcome == "unreachable"


# --- Groq (incident.io) --------------------------------------------------


def test_groq_operational_when_no_ongoing_incidents(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_http_get(url: str, **_: Any) -> _FakeResponse:
        assert url == "https://groqstatus.com/api/v1/summary"
        return _FakeResponse(200, {"ongoing_incidents": [], "in_progress_maintenances": []})

    [result] = check_provider_status([_groq_provider()], http_get=fake_http_get)
    assert result.outcome == "ok"
    assert result.state == "operational"


def test_groq_degraded_when_ongoing_incident_present() -> None:
    def fake_http_get(url: str, **_: Any) -> _FakeResponse:
        return _FakeResponse(
            200,
            {
                "ongoing_incidents": [
                    {"name": "Elevated error rates on llama-3.3-70b", "status": "identified"}
                ],
                "in_progress_maintenances": [],
            },
        )

    [result] = check_provider_status([_groq_provider()], http_get=fake_http_get)
    assert result.outcome == "ok"
    assert result.state == "degraded"
    assert "Elevated error rates" in result.reason


# --- Together (Betterstack JSON:API) -------------------------------------


def test_together_operational(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_http_get(url: str, **_: Any) -> _FakeResponse:
        assert url == "https://status.together.ai/index.json"
        return _FakeResponse(200, {"data": {"attributes": {"aggregate_state": "operational"}}})

    [result] = check_provider_status([_together_provider()], http_get=fake_http_get)
    assert result.outcome == "ok"
    assert result.state == "operational"


def test_together_degraded_state_passthrough() -> None:
    def fake_http_get(url: str, **_: Any) -> _FakeResponse:
        return _FakeResponse(200, {"data": {"attributes": {"aggregate_state": "degraded"}}})

    [result] = check_provider_status([_together_provider()], http_get=fake_http_get)
    assert result.state == "degraded"


# --- Google AI Studio / Gemini API status (aistudio.google.com/status) ----
# 2026-07-30: status.cloud.google.com/incidents.json SOLO confirmaba "Vertex
# Gemini API" (producto de pago), nunca generativelanguage.googleapis.com
# (tier gratis que usa gemini_free) -- reemplazado por la página de estado
# REAL de AI Studio/Gemini API, verificada en vivo con browser real (incluye
# incidentes de "ListModels", claves de API, límites de modelo -- la
# superficie correcta). Esa página no tiene JSON: requiere JS, así que se lee
# vía navegador (browser_fetch inyectable, igual que http_get -- ningún test
# de este bloque levanta un navegador real).


def test_google_operational_when_page_says_all_systems_operational() -> None:
    def fake_browser_fetch(url: str) -> str:
        assert url == "https://aistudio.google.com/status"
        return "Google AI Studio and the Gemini API Status\ncheck\nAll Systems Operational\nAPI\n30 days"

    [result] = check_provider_status([_gemini_provider()], browser_fetch=fake_browser_fetch)
    assert result.outcome == "ok"
    assert result.state == "operational"


def test_google_degraded_when_page_does_not_say_all_systems_operational() -> None:
    def fake_browser_fetch(url: str) -> str:
        return "Google AI Studio and the Gemini API Status\ncheck\nPartial System Outage\nAPI\n30 days"

    [result] = check_provider_status([_gemini_provider()], browser_fetch=fake_browser_fetch)
    assert result.state == "degraded"
    assert "Partial System Outage" in result.reason


def test_google_unrecognized_page_shape_is_unreachable_not_operational() -> None:
    """Si el texto no trae NI 'Operational' NI un indicador de degradación
    reconocido, no se asume 'todo bien' -- unknown > mentir."""

    def fake_browser_fetch(url: str) -> str:
        return "<html>algo cambió en el maquetado y esto ya no es lo que esperábamos</html>"

    [result] = check_provider_status([_gemini_provider()], browser_fetch=fake_browser_fetch)
    assert result.outcome == "unreachable"


def test_google_browser_fetch_exception_never_raises() -> None:
    def fake_browser_fetch(url: str) -> str:
        raise RuntimeError("playwright boom")

    [result] = check_provider_status([_gemini_provider()], browser_fetch=fake_browser_fetch)
    assert result.outcome == "unreachable"
    assert "playwright boom" in result.reason


def test_google_never_uses_http_get() -> None:
    """El vendor google ahora es 100% vía navegador; http_get no debe
    llamarse para él aunque se inyecte uno que fallaría si lo hiciera."""

    def fake_http_get(url: str, **_: Any) -> Any:
        raise AssertionError("no debería llamar a http_get para google")

    def fake_browser_fetch(url: str) -> str:
        return "All Systems Operational"

    [result] = check_provider_status(
        [_gemini_provider()], http_get=fake_http_get, browser_fetch=fake_browser_fetch
    )
    assert result.outcome == "ok"


# --- nunca lanza -----------------------------------------------------------


def test_unreachable_never_raises() -> None:
    def fake_http_get(url: str, **_: Any) -> Any:
        raise TimeoutError("boom")

    [result] = check_provider_status([_groq_provider()], http_get=fake_http_get)
    assert result.outcome == "unreachable"
    assert result.state == "unknown"


def test_malformed_json_never_raises() -> None:
    def fake_http_get(url: str, **_: Any) -> _FakeResponse:
        return _FakeResponse(200, ["not", "the", "expected", "shape"])

    [result] = check_provider_status([_groq_provider()], http_get=fake_http_get)
    assert result.outcome == "unreachable"


def test_http_error_status_never_raises() -> None:
    def fake_http_get(url: str, **_: Any) -> _FakeResponse:
        return _FakeResponse(503, {})

    [result] = check_provider_status([_groq_provider()], http_get=fake_http_get)
    assert result.outcome == "unreachable"
    assert "503" in result.reason


def test_result_to_dict_roundtrip() -> None:
    result = StatusResult(vendor="groq", outcome="ok", state="operational", reason="")
    d = result.to_dict()
    assert d["vendor"] == "groq"
    assert d["state"] == "operational"
    assert "checked_at" in d
