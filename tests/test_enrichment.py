"""
Tests para src/atlas/mcp/enrichment.py (Pieza 1 — enriquecimiento del catálogo).

TDD: tests escritos ANTES de la implementación.
Ningún test hace red real; todos inyectan un fetcher fake.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from atlas.mcp.enrichment import (
    Enrichment,
    EnrichmentFetcher,
    GithubEnrichment,
    NpmEnrichment,
    enrich_entry,
)


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------

def _fake_fetcher(enrichment: Enrichment | None):
    """Devuelve un EnrichmentFetcher que siempre retorna el valor dado."""

    class _Fake:
        def fetch(self, source: str, name: str) -> Enrichment | None:
            return enrichment

    return _Fake()


def _fake_http_fetcher(status: int, payload: dict[str, Any]):
    """Fetcher HTTP inyectable que devuelve (status, json_text) sin red."""

    def _fetcher(
        method: str,
        url: str,
        body: bytes | None,
        headers: dict[str, str],
    ) -> tuple[int, str]:
        return status, json.dumps(payload)

    return _fetcher


def _entry(**kwargs: Any) -> dict[str, Any]:
    """Construye una entrada mínima del catálogo."""
    base: dict[str, Any] = {
        "name": "some-tool",
        "kind": "mcp",
        "purpose": "",
        "status": "candidato",
        "tags": [],
        "source": "some-owner/some-repo",
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# enrich_entry — comportamiento principal
# ---------------------------------------------------------------------------


class TestEnrichEntry:
    def test_fills_purpose_signal_leaves_status(self):
        """enrich_entry rellena purpose+purpose_claimed+signal; status inalterado."""
        e = _entry(status="candidato")
        enrichment = Enrichment(purpose_claimed="Does cool things", signal={"stars": 42})
        fetcher = _fake_fetcher(enrichment)

        result = enrich_entry(e, fetcher)

        assert result["purpose"] == "Does cool things"
        assert result["purpose_claimed"] is True
        assert result["signal"] == {"stars": 42}
        assert result["status"] == "candidato"   # invariante crítica

    def test_status_never_changed_when_verificado(self):
        """status='verificado' permanece intacto tras enrich_entry."""
        e = _entry(status="verificado")
        enrichment = Enrichment(purpose_claimed="Desc", signal={"stars": 99})
        fetcher = _fake_fetcher(enrichment)

        result = enrich_entry(e, fetcher)

        assert result["status"] == "verificado"

    def test_does_not_overwrite_existing_purpose(self):
        """Si purpose ya existe, enrich_entry NO lo pisa."""
        e = _entry(purpose="Ya tenemos descripción manual")
        enrichment = Enrichment(purpose_claimed="Nueva descripción", signal={"stars": 5})
        fetcher = _fake_fetcher(enrichment)

        result = enrich_entry(e, fetcher)

        assert result["purpose"] == "Ya tenemos descripción manual"
        # purpose_claimed no debe aparecer (no sobreescribimos nada)
        assert "purpose_claimed" not in result

    def test_fetch_none_leaves_entry_unchanged(self):
        """Si fetch devuelve None, la entrada no cambia (wire-before-claim)."""
        e = _entry(purpose="", status="candidato")
        fetcher = _fake_fetcher(None)

        result = enrich_entry(e, fetcher)

        assert result["purpose"] == ""
        assert "purpose_claimed" not in result
        assert "signal" not in result
        assert result["status"] == "candidato"

    def test_idempotent_double_enrich(self):
        """Enriquecer dos veces produce el mismo resultado que una sola vez."""
        e = _entry()
        enrichment = Enrichment(purpose_claimed="Desc idempotente", signal={"stars": 10})
        fetcher = _fake_fetcher(enrichment)

        result1 = enrich_entry(e, fetcher)
        result2 = enrich_entry(result1, fetcher)

        assert result1 == result2

    def test_signal_merged_even_with_existing_purpose(self):
        """signal se actualiza aunque purpose ya existiera (solo purpose no se pisa)."""
        e = _entry(purpose="Existing purpose")
        enrichment = Enrichment(purpose_claimed="Nueva desc", signal={"stars": 7})
        fetcher = _fake_fetcher(enrichment)

        result = enrich_entry(e, fetcher)

        # purpose sin tocar
        assert result["purpose"] == "Existing purpose"
        # signal sí se escribe (primer enriquecimiento)
        assert result["signal"] == {"stars": 7}


# ---------------------------------------------------------------------------
# GithubEnrichment — parseo de payload GitHub sin red
# ---------------------------------------------------------------------------


class TestGithubEnrichment:
    def _make_fetcher(self, status: int, payload: dict[str, Any]) -> GithubEnrichment:
        return GithubEnrichment(fetcher=_fake_http_fetcher(status, payload))

    def test_parses_description_and_stars(self):
        """GithubEnrichment parsea description+stargazers_count del payload."""
        payload = {
            "description": "A very cool tool",
            "stargazers_count": 1234,
        }
        gh = self._make_fetcher(200, payload)

        result = gh.fetch("some-owner/some-repo", "some-tool")

        assert result is not None
        assert result.purpose_claimed == "A very cool tool"
        assert result.signal == {"stars": 1234}

    def test_returns_none_on_404(self):
        """fetch devuelve None ante 404 (no inventa descripción)."""
        gh = self._make_fetcher(404, {"message": "Not Found"})

        result = gh.fetch("owner/missing-repo", "missing-tool")

        assert result is None

    def test_returns_none_on_empty_description(self):
        """Si description es null/vacío el fetcher devuelve None."""
        payload = {"description": None, "stargazers_count": 5}
        gh = self._make_fetcher(200, payload)

        result = gh.fetch("owner/repo", "tool")

        assert result is None

    def test_no_real_network(self):
        """El fake fetcher no hace red real — se comprueba implícitamente en los
        tests anteriores, pero marcamos explícitamente que no debe llamar a urllib
        sin inyección."""
        calls: list[str] = []

        def recording_fetcher(method, url, body, headers):
            calls.append(url)
            return 200, json.dumps({"description": "ok", "stargazers_count": 1})

        gh = GithubEnrichment(fetcher=recording_fetcher)
        gh.fetch("owner/repo", "tool")

        assert len(calls) == 1
        assert "api.github.com" in calls[0]


# ---------------------------------------------------------------------------
# NpmEnrichment — parseo de payload npm sin red
# ---------------------------------------------------------------------------


class TestNpmEnrichment:
    def _make_npm(self, status: int, payload: dict[str, Any]) -> NpmEnrichment:
        return NpmEnrichment(fetcher=_fake_http_fetcher(status, payload))

    def test_parses_description_and_downloads(self):
        """NpmEnrichment parsea description+downloads del payload."""
        # Simula /registry/<pkg> (description) + /downloads (en signal)
        # NpmEnrichment decide qué URLs llamar; aquí el fake devuelve
        # un payload unificado con ambos campos (o se verifica la lógica interna).
        payload = {
            "description": "An npm utility",
            "downloads": 400_000,
        }
        npm = self._make_npm(200, payload)

        result = npm.fetch("", "some-package")

        assert result is not None
        assert result.purpose_claimed == "An npm utility"
        assert result.signal == {"downloads": 400_000}

    def test_returns_none_on_404(self):
        """fetch devuelve None ante 404."""
        npm = self._make_npm(404, {"error": "Not found"})

        result = npm.fetch("", "nonexistent-package")

        assert result is None

    def test_returns_none_on_empty_description(self):
        """Si description es vacía/null devuelve None."""
        payload = {"description": "", "downloads": 10}
        npm = self._make_npm(200, payload)

        result = npm.fetch("", "pkg")

        assert result is None

    def test_no_real_network(self):
        """El fetcher inyectado captura las URLs llamadas; ninguna debe ir a la red."""
        calls: list[str] = []

        def recording_fetcher(method, url, body, headers):
            calls.append(url)
            return 200, json.dumps({"description": "ok", "downloads": 1})

        npm = NpmEnrichment(fetcher=recording_fetcher)
        npm.fetch("", "lodash")

        assert len(calls) >= 1
        assert all(
            "npmjs.org" in c or "api.npmjs.org" in c for c in calls
        )


# ---------------------------------------------------------------------------
# Verificación de tipos (Protocol)
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_fake_fetcher_satisfies_protocol(self):
        """El fake fetcher cumple el Protocol EnrichmentFetcher."""
        enrichment = Enrichment(purpose_claimed="x", signal={})
        fake = _fake_fetcher(enrichment)
        # Verificación estructural: Protocol no requiere isinstance
        assert hasattr(fake, "fetch")
        assert callable(fake.fetch)

    def test_enrichment_dataclass_fields(self):
        """Enrichment tiene los campos purpose_claimed y signal."""
        e = Enrichment(purpose_claimed="hello", signal={"stars": 1})
        assert e.purpose_claimed == "hello"
        assert e.signal == {"stars": 1}
