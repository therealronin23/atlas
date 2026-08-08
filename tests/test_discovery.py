"""Vigilancia serendípica del ecosistema (T4) — contrato real.

Sustituye al test previo, que era una tautología: mockeaba
`discover_candidates` (lo único que hacía algo) y después verificaba que
`stars > 10` y `stars > 50` funcionaban. Daba 100% de cobertura sobre código
que el propio `sanitation_audit` de Atlas clasificaba como vapor.

Los tres defectos que fija este módulo:

1. **Egress sin control.** `EcosystemScout` recibía un `CrawlerTool` y no lo
   usaba: salía por `urllib.request.urlopen` crudo, saltándose el
   `SSRFBridge` que el resto del repo usa (fan-in 20) exactamente para esto.
2. **Números mágicos disfrazados de verificación.** "Simulamos el cruce de
   señales: si tiene estrellas y está marcado como listo, es válido."
   Cruzar señales no es volver a mirar la misma señal.
3. **Fallos tragados.** `except Exception` con un log y a otra cosa: una
   fuente caída era indistinguible de una fuente sin resultados.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from atlas.discovery.digestion import EcosystemDigestion
from atlas.discovery.pipeline import DissectionPipeline
from atlas.discovery.scout import Candidate, EcosystemScout
from atlas.security.ssrf_bridge import SSRFBridge


class _FakeFetch:
    """Sustituye la salida HTTP. Registra las URLs que se le piden para poder
    afirmar que NINGUNA se pidió sin pasar antes por el bridge."""

    def __init__(self, payloads: dict[str, Any] | None = None, fail: Exception | None = None):
        self.payloads = payloads or {}
        self.fail = fail
        self.urls: list[str] = []

    def __call__(self, url: str, *, timeout: float = 10.0) -> str:
        self.urls.append(url)
        if self.fail is not None:
            raise self.fail
        return json.dumps(self.payloads.get(url, {"items": []}))


def _items(*names: str) -> dict[str, Any]:
    return {
        "items": [
            {
                "name": n,
                "html_url": f"https://github.com/o/{n}",
                "description": f"desc {n}",
                "stargazers_count": 100,
                "archived": False,
                "license": {"spdx_id": "MIT"},
                "pushed_at": "2026-08-01T00:00:00Z",
            }
            for n in names
        ]
    }


# --------------------------------------------------------------------------
# 1. Egress controlado
# --------------------------------------------------------------------------


def test_una_url_bloqueada_por_el_bridge_no_se_pide_jamas() -> None:
    """La invariante que faltaba: si el bridge dice no, no hay request."""
    fetch = _FakeFetch()
    scout = EcosystemScout(
        SSRFBridge(),
        fetch=fetch,
        sources=("http://127.0.0.1:8080/admin", "http://169.254.169.254/latest/meta-data"),
    )

    report = scout.discover()

    assert fetch.urls == []
    assert report.candidates == ()
    assert len(report.failures) == 2


def test_esquema_no_http_se_rechaza_antes_de_salir() -> None:
    fetch = _FakeFetch()
    scout = EcosystemScout(SSRFBridge(), fetch=fetch, sources=("file:///etc/passwd",))

    report = scout.discover()

    assert fetch.urls == []
    assert len(report.failures) == 1


# --------------------------------------------------------------------------
# 2. Fallos con motivo, no tragados
# --------------------------------------------------------------------------


def test_una_fuente_caida_se_declara_no_se_traga() -> None:
    """Antes: `except Exception` + log. Una fuente rota era indistinguible de
    una fuente vacía, y el catálogo quedaba silenciosamente incompleto."""
    url = "https://api.github.com/search/repositories?q=mcp"
    scout = EcosystemScout(
        SSRFBridge(), fetch=_FakeFetch(fail=TimeoutError("timeout")), sources=(url,)
    )

    report = scout.discover()

    assert report.candidates == ()
    assert len(report.failures) == 1
    fallo_url, motivo = report.failures[0]
    assert fallo_url == url
    assert "TimeoutError" in motivo


def test_json_invalido_es_fallo_declarado() -> None:
    class _Basura(_FakeFetch):
        def __call__(self, url: str, *, timeout: float = 10.0) -> str:
            self.urls.append(url)
            return "<html>rate limited</html>"

    url = "https://api.github.com/search/repositories?q=mcp"
    report = EcosystemScout(SSRFBridge(), fetch=_Basura(), sources=(url,)).discover()

    assert report.candidates == ()
    assert len(report.failures) == 1


def test_una_fuente_caida_no_cancela_las_demas() -> None:
    ok = "https://api.github.com/search/repositories?q=ok"

    class _Mixto(_FakeFetch):
        def __call__(self, url: str, *, timeout: float = 10.0) -> str:
            self.urls.append(url)
            if "roto" in url:
                raise OSError("boom")
            return json.dumps(_items("bueno"))

    report = EcosystemScout(
        SSRFBridge(),
        fetch=_Mixto(),
        sources=("https://api.github.com/search/repositories?q=roto", ok),
    ).discover()

    assert [c.name for c in report.candidates] == ["bueno"]
    assert len(report.failures) == 1


# --------------------------------------------------------------------------
# 3. Disección con razones nombradas, no con un número mágico
# --------------------------------------------------------------------------


def _cand(name: str = "x", **kw: Any) -> Candidate:
    base: dict[str, Any] = {
        "name": name,
        "url": f"https://github.com/o/{name}",
        "description": "d",
        "source": "github_search",
        "stars": 100,
        "archived": False,
        "license": "MIT",
        "pushed_at": "2026-08-01T00:00:00Z",
    }
    base.update(kw)
    return Candidate(**base)


def test_un_repo_archivado_se_descarta_con_motivo() -> None:
    d = DissectionPipeline().dissect(_cand(archived=True))

    assert d.eligible is False
    assert "archivado" in d.reasons


def test_sin_licencia_se_descarta_con_motivo() -> None:
    d = DissectionPipeline().dissect(_cand(license=None))

    assert d.eligible is False
    assert "sin_licencia" in d.reasons


def test_las_razones_se_acumulan() -> None:
    d = DissectionPipeline().dissect(_cand(archived=True, license=None))

    assert set(d.reasons) >= {"archivado", "sin_licencia"}


def test_un_repo_sano_es_elegible_y_lo_justifica() -> None:
    d = DissectionPipeline().dissect(_cand())

    assert d.eligible is True
    assert d.reasons == ()


def test_disectar_no_inventa_estado() -> None:
    """El pipeline anterior escribía `status='dissected'` sin diseccionar nada.
    Ahora el veredicto sale de campos reales del candidato."""
    d = DissectionPipeline().dissect(_cand(stars=0))

    assert d.candidate.stars == 0
    assert isinstance(d.eligible, bool)


# --------------------------------------------------------------------------
# 4. Corroboración REAL: fuentes independientes, no la misma señal dos veces
# --------------------------------------------------------------------------


def test_una_sola_fuente_no_es_corroboracion() -> None:
    """El bug conceptual original: `cross_reference_signals` volvía a mirar
    `stars`, que es la MISMA señal que ya había usado el pipeline."""
    d = DissectionPipeline().dissect(_cand("solo"))

    corroborados = EcosystemDigestion().corroborate([d])

    assert corroborados == []


def test_dos_fuentes_independientes_corroboran() -> None:
    a = DissectionPipeline().dissect(_cand("dup", source="github_search"))
    b = DissectionPipeline().dissect(_cand("dup", source="mcp_registry"))

    corroborados = EcosystemDigestion().corroborate([a, b])

    assert len(corroborados) == 1
    assert corroborados[0].name == "dup"
    assert set(corroborados[0].sources) == {"github_search", "mcp_registry"}


def test_la_misma_fuente_dos_veces_no_corrobora() -> None:
    a = DissectionPipeline().dissect(_cand("dup", source="github_search"))
    b = DissectionPipeline().dissect(_cand("dup", source="github_search"))

    assert EcosystemDigestion().corroborate([a, b]) == []


def test_un_inelegible_no_corrobora_aunque_se_repita() -> None:
    a = DissectionPipeline().dissect(_cand("mal", source="github_search", archived=True))
    b = DissectionPipeline().dissect(_cand("mal", source="mcp_registry", archived=True))

    assert EcosystemDigestion().corroborate([a, b]) == []


def test_corroborar_no_muta_la_entrada() -> None:
    a = DissectionPipeline().dissect(_cand("dup", source="github_search"))
    b = DissectionPipeline().dissect(_cand("dup", source="mcp_registry"))

    EcosystemDigestion().corroborate([a, b])

    assert a.eligible is True and a.reasons == ()


# --------------------------------------------------------------------------
# 5. Camino completo, sin red
# --------------------------------------------------------------------------


def test_cadena_completa_scout_pipeline_digestion() -> None:
    u1 = "https://api.github.com/search/repositories?q=a"
    u2 = "https://api.github.com/search/repositories?q=b"
    fetch = _FakeFetch({u1: _items("comun", "solo_a"), u2: _items("comun")})
    report = EcosystemScout(SSRFBridge(), fetch=fetch, sources=(u1, u2)).discover()

    assert len(report.candidates) == 3
    assert report.failures == ()

    pipeline = DissectionPipeline()
    dissections = [pipeline.dissect(c) for c in report.candidates]
    assert all(d.eligible for d in dissections)

    # Sin corroboración cruzada real no pasa nadie: las dos URLs son la MISMA
    # fuente (github_search), así que 'comun' aparece dos veces por el mismo canal.
    assert EcosystemDigestion().corroborate(dissections) == []


def test_el_scout_marca_la_fuente_de_cada_candidato() -> None:
    u = "https://api.github.com/search/repositories?q=a"
    report = EcosystemScout(
        SSRFBridge(), fetch=_FakeFetch({u: _items("x")}), sources=(u,)
    ).discover()

    assert report.candidates[0].source == "github_search"


@pytest.mark.parametrize("bad", ["", "no-es-una-url"])
def test_fuentes_basura_no_revientan(bad: str) -> None:
    report = EcosystemScout(SSRFBridge(), fetch=_FakeFetch(), sources=(bad,)).discover()

    assert report.candidates == ()
    assert len(report.failures) == 1
