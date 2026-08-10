"""Criba y corroboración sobre los hallazgos que el radar YA produce.

Contexto medido el 2026-08-10, no supuesto: `maintenance_research_tick` corre
a diario y produjo **122 hallazgos** en tres canales (github/hackernews/arxiv)
sólo hoy — `research_tick @ 00:14 findings_count: 122` en el ledger. Ninguno
pasa por filtro alguno: entran crudos al informe, sin mirar licencia, archivado
ni abandono, y sin que nada diga cuál lo vio más de un canal.

Justo eso es lo que `atlas.discovery` (T4) tenía escrito y **sin un solo
caller** fuera de su propio test. Este módulo es la junta entre ambos.

Tres decisiones de diseño que los tests fijan:

1. **La identidad sale de la URL, no del título.** GitHub da `owner/repo`, HN
   da un titular y arXiv el nombre de un paper: no coinciden jamás. Por eso un
   "Show HN" que enlaza a `github.com/x/y` SÍ corrobora al repo `x/y`.
2. **Se agrupa por REPO, no por hallazgo.** Un avistamiento en HN es evidencia
   sobre el repo aunque no traiga licencia; los metadatos los aporta el
   avistamiento que los tenga.
3. **Un paper no es un repo.** Pasarlo por la criba lo rechazaría por
   `sin_licencia`, que es una mentira sobre un arXiv. Los no-repo se nombran
   aparte, no se descartan en silencio. Y "no sé la licencia" tampoco es "no
   tiene licencia".
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from atlas.core.self_maintenance.panorama_scout import PanoramaFinding
from atlas.discovery.triage import repo_identity, triage_findings

_AHORA = datetime(2026, 8, 10, tzinfo=timezone.utc)


def _gh(
    repo: str = "acme/tool",
    *,
    license: str | None = "MIT",
    archived: bool = False,
    pushed_at: str | None = "2026-08-01T00:00:00Z",
    stars: int = 100,
) -> PanoramaFinding:
    """Hallazgo de GitHub CON metadatos: es el único canal que los publica."""
    return PanoramaFinding(
        topic="memoria de agentes",
        source="github",
        title=repo,
        url=f"https://github.com/{repo}",
        excerpt="d",
        metadata_known=True,
        license=license,
        archived=archived,
        pushed_at=pushed_at,
        stars=stars,
    )


def _hn(url: str, title: str = "Show HN: una cosa") -> PanoramaFinding:
    return PanoramaFinding(
        topic="memoria de agentes", source="hackernews", title=title, url=url, excerpt=""
    )


def _arxiv(ident: str = "2508.01234v1") -> PanoramaFinding:
    return PanoramaFinding(
        topic="memoria de agentes",
        source="arxiv",
        title="Un paper sobre memoria",
        url=f"http://arxiv.org/abs/{ident}",
        excerpt="resumen",
    )


# ---------------------------------------------------------------------------
# 1. Identidad: sale de la URL, no del título
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,esperado",
    [
        ("https://github.com/acme/tool", "acme/tool"),
        ("https://github.com/Acme/Tool", "acme/tool"),
        ("https://github.com/acme/tool.git", "acme/tool"),
        ("https://github.com/acme/tool/", "acme/tool"),
        ("https://github.com/acme/tool/tree/main/src", "acme/tool"),
        ("https://www.github.com/acme/tool", "acme/tool"),
    ],
)
def test_la_identidad_del_repo_se_normaliza(url: str, esperado: str) -> None:
    assert repo_identity(url) == esperado


@pytest.mark.parametrize(
    "url",
    [
        "http://arxiv.org/abs/2508.01234v1",
        "https://news.ycombinator.com/item?id=123",
        "https://github.com/acme",  # un perfil no es un repo
        "https://github.com",
        "https://gitlab.com/acme/tool",  # sólo GitHub: es lo único que sabemos leer
        "",
        "no-es-una-url",
    ],
)
def test_lo_que_no_es_un_repo_de_github_no_tiene_identidad(url: str) -> None:
    assert repo_identity(url) is None


def test_las_rutas_reservadas_de_github_no_son_repos() -> None:
    """`github.com/features/copilot` tiene forma de owner/repo y no lo es."""
    assert repo_identity("https://github.com/features/copilot") is None
    assert repo_identity("https://github.com/orgs/acme/repositories") is None
    assert repo_identity("https://github.com/search?q=mcp") is None


# ---------------------------------------------------------------------------
# 2. La criba, con motivos nombrados
# ---------------------------------------------------------------------------


def test_un_repo_sano_es_elegible() -> None:
    r = triage_findings([_gh()], now=_AHORA)

    assert [repo.name for repo in r.eligible] == ["acme/tool"]
    assert r.rejected == ()


def test_un_repo_archivado_se_rechaza_con_motivo() -> None:
    r = triage_findings([_gh(archived=True)], now=_AHORA)

    assert r.eligible == ()
    assert r.rejected[0].reasons == ("archivado",)


def test_un_repo_sin_licencia_se_rechaza_con_motivo() -> None:
    r = triage_findings([_gh(license=None)], now=_AHORA)

    assert r.eligible == ()
    assert "sin_licencia" in r.rejected[0].reasons


def test_un_repo_abandonado_se_rechaza_con_motivo() -> None:
    r = triage_findings([_gh(pushed_at="2020-01-01T00:00:00Z")], now=_AHORA)

    assert "abandonado" in r.rejected[0].reasons


def test_los_motivos_se_acumulan() -> None:
    r = triage_findings([_gh(archived=True, license=None)], now=_AHORA)

    assert set(r.rejected[0].reasons) >= {"archivado", "sin_licencia"}


def test_desconocer_los_metadatos_no_es_no_tenerlos() -> None:
    """Un repo avistado sólo por un canal que no publica licencia NO puede
    rechazarse por `sin_licencia`: eso convierte 'no lo sé' en 'no la tiene',
    que es el defecto que esta auditoría lleva una semana persiguiendo."""
    r = triage_findings([_hn("https://github.com/acme/tool")], now=_AHORA)

    assert r.eligible == () and r.rejected == ()
    assert [repo.name for repo in r.sin_metadatos] == ["acme/tool"]


# ---------------------------------------------------------------------------
# 3. Un paper no es un repo
# ---------------------------------------------------------------------------


def test_un_paper_de_arxiv_no_pasa_por_la_criba_de_repos() -> None:
    r = triage_findings([_arxiv()], now=_AHORA)

    assert r.eligible == () and r.rejected == ()
    assert [f.source for f in r.no_repo] == ["arxiv"]


def test_un_hilo_de_hn_sin_repo_detras_tampoco() -> None:
    r = triage_findings([_hn("https://news.ycombinator.com/item?id=1")], now=_AHORA)

    assert r.rejected == ()
    assert len(r.no_repo) == 1


# ---------------------------------------------------------------------------
# 4. Corroboración cruzada REAL entre canales
# ---------------------------------------------------------------------------


def test_github_y_un_show_hn_al_mismo_repo_corroboran() -> None:
    """El caso que hace útil la corroboración: dos canales independientes
    apuntando a la misma cosa. HN no trae licencia; la aporta GitHub."""
    r = triage_findings(
        [_gh("acme/tool"), _hn("https://github.com/acme/tool")], now=_AHORA
    )

    assert len(r.corroborated) == 1
    assert r.corroborated[0].name == "acme/tool"
    assert set(r.corroborated[0].sources) == {"github", "hackernews"}


def test_un_solo_canal_no_corrobora_por_mucho_que_se_repita() -> None:
    """Hoy el radar trae los repos casi sólo por github. Que el resultado sea
    vacío es la respuesta HONESTA, no un fallo — y queda fijado para que nadie
    'arregle' la corroboración bajando el listón a un canal."""
    r = triage_findings([_gh("acme/tool"), _gh("acme/tool")], now=_AHORA)

    assert r.corroborated == ()
    assert len(r.eligible) == 1, "deduplicado por identidad, no contado dos veces"


def test_un_repo_inelegible_no_corrobora_aunque_lo_avalen_dos_canales() -> None:
    r = triage_findings(
        [_gh("acme/tool", archived=True), _hn("https://github.com/acme/tool")],
        now=_AHORA,
    )

    assert r.corroborated == ()


def test_un_repo_sin_metadatos_no_corrobora_aunque_lo_vean_dos_canales() -> None:
    """Dos canales que lo ven pero ninguno que diga la licencia: no es
    elegible todavía, así que tampoco corroborado. Sin dato no hay ascenso."""
    r = triage_findings(
        [_hn("https://github.com/acme/tool"), _arxiv()], now=_AHORA
    )

    assert r.corroborated == ()


def test_un_paper_no_corrobora_a_un_repo() -> None:
    r = triage_findings([_gh("acme/tool"), _arxiv()], now=_AHORA)

    assert r.corroborated == ()


def test_la_corroboracion_ordena_por_canales_y_estrellas() -> None:
    """Salida estable: el informe no puede cambiar de orden entre dos tiradas
    con la misma entrada."""
    findings = [
        _gh("acme/uno", stars=10),
        _hn("https://github.com/acme/uno"),
        _gh("acme/dos", stars=900),
        _hn("https://github.com/acme/dos"),
    ]

    nombres = [c.name for c in triage_findings(findings, now=_AHORA).corroborated]

    assert nombres == ["acme/dos", "acme/uno"]


# ---------------------------------------------------------------------------
# 5. La invariante que impide perder hallazgos por el camino
# ---------------------------------------------------------------------------


def test_ningun_hallazgo_desaparece_en_la_criba() -> None:
    """Un filtro que pierde entradas en silencio es peor que no filtrar. Cada
    hallazgo acaba contabilizado en exactamente una cesta."""
    findings = [
        _gh("acme/bueno"),
        _gh("acme/malo", archived=True),
        _hn("https://github.com/acme/bueno"),
        _arxiv(),
        _hn("https://news.ycombinator.com/item?id=9"),
    ]

    r = triage_findings(findings, now=_AHORA)

    assert r.total_entrada == 5
    assert r.total_clasificado == 5


def test_la_criba_no_muta_los_hallazgos_de_entrada() -> None:
    f = _gh()
    triage_findings([f], now=_AHORA)

    assert f.source == "github" and f.url == "https://github.com/acme/tool"
    assert f.metadata_known is True


def test_sin_hallazgos_no_revienta() -> None:
    r = triage_findings([], now=_AHORA)

    assert r.total_entrada == 0
    assert r.total_clasificado == 0
    assert r.eligible == () and r.corroborated == ()
