"""T4.4 — La junta entre el radar que YA corre y la criba que nadie llamaba.

Medido el 2026-08-10: ``maintenance_research_tick`` corre a diario y produjo
**122 hallazgos** en tres canales (github/hackernews/arxiv) sólo ese día
(``research_tick @ 00:14 findings_count: 122``). Ninguno pasaba por filtro:
entraban crudos al informe de ``docs/inbox/``, sin mirar licencia, archivado ni
abandono, y sin que nada dijera cuál de ellos lo había visto más de un canal.

Mientras tanto ``DissectionPipeline`` y ``EcosystemDigestion`` (este paquete)
llevaban desde el 2026-08-06 escritos y **sin un solo caller** fuera de su
propio test: construido y sin cablear, la familia de defecto que esta auditoría
lleva una semana arrancando. Este módulo los conecta.

Tres decisiones que conviene no deshacer sin leer esto:

**La identidad sale de la URL, no del título.** GitHub titula ``owner/repo``,
HN titula un titular y arXiv el nombre de un paper: agrupar por título no
casaría jamás dos canales, y la corroboración devolvería vacío para siempre
pareciendo que funciona. Un "Show HN" que enlaza a ``github.com/x/y`` es
evidencia sobre el repo ``x/y``, y así se cuenta.

**Se agrupa por REPO, no por avistamiento.** Los metadatos los aporta el canal
que los publique — sólo GitHub lo hace — y los demás avistamientos aportan
canal. Exigir licencia a cada avistamiento por separado descartaría justo la
señal cruzada que hace útil la corroboración.

**"No lo sé" no es "no lo tiene".** Un repo visto sólo por HN no tiene licencia
*conocida*; rechazarlo por ``sin_licencia`` sería inventar un hecho. Va a su
propia cesta, nombrada, ni elegible ni rechazado.

Cribar no adopta nada: es la señal barata de entrada al vetting real
(ADR-075/076), que sigue decidiendo en sandbox y con consentimiento.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

from atlas.core.self_maintenance.panorama_scout import PanoramaFinding
from atlas.discovery.digestion import MIN_INDEPENDENT_SOURCES
from atlas.discovery.pipeline import MAX_STALE_DAYS, DissectionPipeline
from atlas.discovery.scout import Candidate

logger = logging.getLogger(__name__)

_GITHUB_HOSTS = frozenset({"github.com", "www.github.com"})

#: Primeros segmentos de ruta que GitHub reserva para su propio producto. Sin
#: esto, ``github.com/features/copilot`` pasaría por el repo ``features/copilot``
#: — tiene exactamente la misma forma.
_RESERVED_OWNERS = frozenset({
    "features", "orgs", "search", "settings", "topics", "collections",
    "sponsors", "marketplace", "explore", "notifications", "pulls", "issues",
    "codespaces", "apps", "about", "pricing", "login", "join", "new",
    "trending", "events", "readme", "security", "enterprise", "team",
})


def repo_identity(url: str) -> str | None:
    """``owner/repo`` canónico de una URL de GitHub, o ``None`` si no lo es.

    Normaliza a minúsculas porque el host de GitHub no distingue mayúsculas:
    ``Acme/Tool`` y ``acme/tool`` son el mismo repo, y contarlos por separado
    partiría la corroboración justo cuando dos canales escriben distinto.
    """
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    if (parsed.hostname or "").lower() not in _GITHUB_HOSTS:
        return None
    partes = [seg for seg in parsed.path.split("/") if seg]
    if len(partes) < 2:
        # Un perfil (`github.com/acme`) no es un repositorio.
        return None
    owner, repo = partes[0].lower(), partes[1].lower()
    if owner in _RESERVED_OWNERS:
        return None
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    if not owner or not repo:
        return None
    return f"{owner}/{repo}"


@dataclass(frozen=True)
class RepoSightings:
    """Un repositorio y todos los avistamientos que lo señalaron.

    ``reasons`` vacío no implica elegible: un repo sin metadatos conocidos no
    tiene motivos de rechazo Y tampoco es elegible. Los distingue la cesta en
    la que cae, no este campo.
    """

    name: str
    url: str
    sources: tuple[str, ...]
    stars: int
    metadata_known: bool
    reasons: tuple[str, ...] = ()
    sightings: tuple[PanoramaFinding, ...] = ()

    @property
    def canales(self) -> int:
        return len(self.sources)


@dataclass(frozen=True)
class TriageReport:
    """Las cuatro cestas. Cada hallazgo de entrada cae en exactamente una."""

    eligible: tuple[RepoSightings, ...] = ()
    rejected: tuple[RepoSightings, ...] = ()
    sin_metadatos: tuple[RepoSightings, ...] = ()
    no_repo: tuple[PanoramaFinding, ...] = ()
    corroborated: tuple[RepoSightings, ...] = ()
    total_entrada: int = 0

    @property
    def total_clasificado(self) -> int:
        """Avistamientos contabilizados. Si no cuadra con ``total_entrada``, la
        criba está perdiendo hallazgos en silencio — que es peor que no cribar.

        ``corroborated`` NO se suma: es un subconjunto de ``eligible``, no una
        quinta cesta. Sumarlo haría que el invariante cuadrara por accidente.
        """
        de_repos = sum(
            len(repo.sightings)
            for cesta in (self.eligible, self.rejected, self.sin_metadatos)
            for repo in cesta
        )
        return de_repos + len(self.no_repo)


@dataclass
class _Acumulador:
    """Mutable a propósito: se llena recorriendo avistamientos y se congela al
    final en un `RepoSightings`."""

    url: str = ""
    stars: int = 0
    sources: set[str] = field(default_factory=set)
    sightings: list[PanoramaFinding] = field(default_factory=list)
    metadata: PanoramaFinding | None = None


def triage_findings(
    findings: Iterable[PanoramaFinding],
    *,
    now: datetime | None = None,
    max_stale_days: int = MAX_STALE_DAYS,
    min_sources: int = MIN_INDEPENDENT_SOURCES,
) -> TriageReport:
    """Agrupa por repo, criba con motivos nombrados y corrobora entre canales.

    No muta la entrada ni sale a la red: sólo mira campos que los canales ya
    publicaron.
    """
    ahora = now or datetime.now(timezone.utc)
    pipeline = DissectionPipeline(max_stale_days=max_stale_days, now=ahora)

    por_repo: dict[str, _Acumulador] = {}
    no_repo: list[PanoramaFinding] = []

    for finding in findings:
        identidad = repo_identity(finding.url)
        if identidad is None:
            no_repo.append(finding)
            continue
        acc = por_repo.setdefault(identidad, _Acumulador())
        acc.sightings.append(finding)
        acc.sources.add(finding.source)
        acc.stars = max(acc.stars, finding.stars)
        if finding.metadata_known and acc.metadata is None:
            # El primer avistamiento que traiga metadatos manda. Hoy sólo
            # GitHub los publica, así que en la práctica no hay conflicto.
            acc.metadata = finding
        if not acc.url or (finding.metadata_known and finding.source == "github"):
            # Preferimos la URL canónica del repo sobre la de un hilo de HN.
            acc.url = finding.url

    eligible: list[RepoSightings] = []
    rejected: list[RepoSightings] = []
    sin_metadatos: list[RepoSightings] = []

    for nombre, acc in sorted(por_repo.items()):
        base = {
            "name": nombre,
            "url": acc.url,
            "sources": tuple(sorted(acc.sources)),
            "stars": acc.stars,
            "sightings": tuple(acc.sightings),
        }
        if acc.metadata is None:
            sin_metadatos.append(
                RepoSightings(metadata_known=False, **base)  # type: ignore[arg-type]
            )
            continue
        veredicto = pipeline.dissect(
            Candidate(
                name=nombre,
                url=acc.url,
                description=acc.metadata.excerpt,
                source=acc.metadata.source,
                stars=acc.stars,
                archived=acc.metadata.archived,
                license=acc.metadata.license,
                pushed_at=acc.metadata.pushed_at,
            )
        )
        repo = RepoSightings(
            metadata_known=True, reasons=veredicto.reasons, **base  # type: ignore[arg-type]
        )
        (eligible if veredicto.eligible else rejected).append(repo)

    # Corroborar es que fuentes INDEPENDIENTES coincidan sobre algo que ya pasó
    # la criba. Un inelegible avalado por diez canales sigue siendo inelegible:
    # la corroboración confirma existencia, no arregla defectos.
    corroborated = tuple(
        sorted(
            (repo for repo in eligible if repo.canales >= min_sources),
            key=lambda repo: (-repo.canales, -repo.stars, repo.name),
        )
    )
    for repo in corroborated:
        logger.info(
            "repo corroborado por %d canales (%s): %s",
            repo.canales,
            ", ".join(repo.sources),
            repo.name,
        )

    return TriageReport(
        eligible=tuple(eligible),
        rejected=tuple(rejected),
        sin_metadatos=tuple(sin_metadatos),
        no_repo=tuple(no_repo),
        corroborated=corroborated,
        total_entrada=len(no_repo) + sum(len(a.sightings) for a in por_repo.values()),
    )


def render_triage_section(report: TriageReport, *, max_listado: int = 20) -> Sequence[str]:
    """Sección del informe de investigación. Números primero, listas después:
    el informe lo lee un humano que decide si mirar, no un parser.
    """
    lines = [
        "## Criba",
        "",
        f"- avistamientos: {report.total_entrada}",
        f"- repos elegibles: {len(report.eligible)}",
        f"- repos descartados: {len(report.rejected)}",
        f"- repos sin metadatos (canal que no publica licencia): {len(report.sin_metadatos)}",
        f"- hallazgos que no son repos (papers, hilos): {len(report.no_repo)}",
        "",
    ]
    if report.corroborated:
        lines.append(f"### Corroborados por {MIN_INDEPENDENT_SOURCES}+ canales")
        lines.append("")
        for repo in report.corroborated[:max_listado]:
            lines.append(
                f"- **{repo.name}** ({', '.join(repo.sources)}; {repo.stars}★) — {repo.url}"
            )
        lines.append("")
    else:
        lines.append(
            "Ningún repo avalado por dos canales independientes esta pasada. "
            "No es un fallo: hoy casi todos los repos entran sólo por GitHub."
        )
        lines.append("")
    if report.rejected:
        lines.append("### Descartados, con motivo")
        lines.append("")
        for repo in report.rejected[:max_listado]:
            lines.append(f"- {repo.name} — {', '.join(repo.reasons)}")
        lines.append("")
    return lines
