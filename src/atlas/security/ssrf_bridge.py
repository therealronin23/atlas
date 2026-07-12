"""
Atlas Core — SSRF Bridge
Punto unico de salida a internet desde el sandbox local.
Solo el SSRF Bridge puede hacer requests HTTP/S desde codigo en sandbox.
Hermes-VPS tiene su propio modelo de egress (mas permisivo).

El SSRF Bridge es un control de Atlas Core, NO de Hermes-VPS.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.parse
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Allowlist de dominios permitidos desde el sandbox
# ---------------------------------------------------------------------------

DEFAULT_ALLOWED_DOMAINS: frozenset[str] = frozenset({
    "api.github.com",
    "raw.githubusercontent.com",
    "registry.modelcontextprotocol.io",    # ADR-039: registro MCP oficial (Scout autoritativo)
    "hn.algolia.com",                       # ADR-039 slice 5: foro community (HN search API) — contenido NO confiable
    "pypi.org",
    "files.pythonhosted.org",
    "api.groq.com",
    "openrouter.ai",
    "api-inference.huggingface.co",
    "colab.research.google.com",
    "kaggle.com",
    "api.runpod.io",
    "generativelanguage.googleapis.com",   # Gemini free tier
    "api.together.xyz",                     # Together AI
    "api.mistral.ai",
    "api.osv.dev",                           # ADR-049 T4: OSV.dev vulnerabilities API
    "api.apis.guru",                         # directorio OpenAPI (seeder de APIs, mcp trunk C)
    "api.open-meteo.com",                     # clima sin auth (knowledge-src, mcp trunk C)
    "api.frankfurter.app",                    # tipos de cambio sin auth (knowledge-src)
    "integrate.api.nvidia.com",               # NVIDIA NIM frontier, inference_hub
    "export.arxiv.org",                       # arXiv API (PanoramaScout; OK explícito del operador 2026-07-10)
    # 2026-07-02: allowlist ampliada para scraping/browsing de propósito general
    # (CrawlerTool/web_crawl, BrowserTool) — sitios de referencia técnica de uso
    # habitual, curados uno a uno (decisión del usuario: "allowlist curada más
    # amplia" sobre aprobación por dominio caso a caso).
    "github.com",
    "huggingface.co",
    "en.wikipedia.org",
    "stackoverflow.com",
    "arxiv.org",
    "docs.python.org",
    "readthedocs.io",
    # 2026-07-04: ampliación para PanoramaScout (descubrimiento por tema del
    # ecosistema entero, no de una lista fija de fuentes conocidas — el
    # usuario: "puede ser un paper, un lenguaje nuevo, un SaaS sin nombre
    # todavía"). Curados uno a uno, mismo criterio que la ampliación anterior.
    "export.arxiv.org",          # API real de arXiv (arxiv.org es solo la web)
    "paperswithcode.com",        # papers de ML con código asociado
    "lobste.rs",                 # foro tech tipo HN, comunidad distinta
    "news.ycombinator.com",      # HN directo (complementa hn.algolia.com, que es solo la API)
    "dev.to",                    # blog/comunidad de desarrolladores, API pública
    "www.reddit.com",            # subreddits técnicos (solo lectura JSON público)
    "producthunt.com",           # lanzamientos de producto/SaaS nuevos, sin nombre aún
    "registry.npmjs.org",        # ecosistema JS/TS
    "crates.io",                 # ecosistema Rust
    "pkg.go.dev",                # ecosistema Go
    "gitlab.com",                # host de código alternativo a GitHub
    "medium.com",                # posts técnicos largos (harnesses, arquitecturas)
    "techcrunch.com",            # noticias de producto/startups
})

# Dominios absolutamente bloqueados (aunque esten en allowed)
BLOCKED_DOMAINS: frozenset[str] = frozenset({
    "169.254.169.254",    # AWS metadata
    "metadata.google.internal",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
})

LOCAL_PRIVATE_DOMAINS: frozenset[str] = frozenset({
    "localhost",
    "127.0.0.1",
    "::1",
})


@dataclass(frozen=True)
class BridgeDecision:
    allowed: bool
    url: str
    reason: str
    domain: str
    # IP resuelta en check() — usar para conectar y evitar 2ª resolución DNS (TOCTOU).
    # None cuando el host ya es una IP literal o cuando la decisión es blocked.
    pinned_ip: str | None = None


class SSRFBridge:
    """
    Proxy de egress para codigo en sandbox.
    Evalua URLs antes de permitir requests.
    El codigo en sandbox llama a SSRFBridge.check() antes de hacer
    cualquier request HTTP.
    """

    def __init__(
        self,
        extra_allowed: set[str] | None = None,
        *,
        allow_private_network: bool = False,
    ) -> None:
        self._allowed = DEFAULT_ALLOWED_DOMAINS | (extra_allowed or set())
        self._allow_private_network = allow_private_network

    def check(self, url: str) -> BridgeDecision:
        """
        Evalua si una URL puede ser accedida desde el sandbox.
        Retorna BridgeDecision con allowed=True si esta permitida.

        Orden de evaluacion (defensa en profundidad):
          1. Esquema HTTP/HTTPS obligatorio.
          2. Blocklist de dominios absolutos (BLOCKED_DOMAINS).
          3. IP privada/loopback/link-local/reservada en la parte host.
          4. Resolucion DNS: todos los A/AAAA deben ser IPs publicas.
          5. Allowlist exacta de dominios.
        """
        try:
            parsed = urllib.parse.urlparse(url)
        except Exception as e:
            return BridgeDecision(
                allowed=False,
                url=url,
                reason=f"URL malformada: {e}",
                domain="",
            )

        # Solo HTTP/HTTPS
        if parsed.scheme not in ("http", "https"):
            return BridgeDecision(
                allowed=False,
                url=url,
                reason=f"Esquema no permitido: {parsed.scheme}. Solo http/https.",
                domain=parsed.netloc,
            )

        domain = (parsed.hostname or parsed.netloc).lower()

        if (
            self._allow_private_network
            and domain in LOCAL_PRIVATE_DOMAINS
            and self._is_allowed(domain)
        ):
            return BridgeDecision(
                allowed=True,
                url=url,
                reason=f"Red privada permitida explícitamente: {domain}",
                domain=domain,
            )

        # 1. Blocklist absoluta PRIMERO — no puede ser anulada por la allowlist
        if domain in BLOCKED_DOMAINS:
            return BridgeDecision(
                allowed=False,
                url=url,
                reason=f"Dominio bloqueado absolutamente: {domain} (SSRF protection).",
                domain=domain,
            )

        # 2. IP privada/loopback/link-local/reservada en el host literal
        if self._is_private_ip(domain):
            return BridgeDecision(
                allowed=False,
                url=url,
                reason=f"IP privada/reservada bloqueada: {domain} (SSRF protection).",
                domain=domain,
            )

        # 3. Resolucion DNS — todos los A/AAAA deben ser publicos.
        #    Fail-closed: si DNS falla la solicitud se rechaza.
        #    Se devuelve también la primera IP resuelta para fijarla (evitar TOCTOU).
        dns_block, pinned_ip = self._check_resolved_ips(domain)
        if dns_block is not None:
            return BridgeDecision(
                allowed=False,
                url=url,
                reason=dns_block,
                domain=domain,
            )

        # 4. Allowlist exacta
        if self._is_allowed(domain):
            return BridgeDecision(
                allowed=True,
                url=url,
                reason=f"Dominio en allowlist: {domain}",
                domain=domain,
                pinned_ip=pinned_ip,
            )

        return BridgeDecision(
            allowed=False,
            url=url,
            reason=f"Dominio no esta en la allowlist: {domain}",
            domain=domain,
        )

    def add_domain(self, domain: str) -> None:
        """Anade un dominio a la allowlist en runtime (requiere APPROVE)."""
        self._allowed = self._allowed | {domain.lower()}

    @property
    def allowed_domains(self) -> frozenset[str]:
        return frozenset(self._allowed)

    # ------------------------------------------------------------------
    # Privado
    # ------------------------------------------------------------------

    def _is_allowed(self, domain: str) -> bool:
        """Match exacto: 'evil.allowed.com' NO pasa si solo 'allowed.com' en allowlist."""
        return domain in self._allowed

    def _is_private_ip(self, host: str) -> bool:
        """Detecta IPs privadas / loopback / link-local / reservadas usando ipaddress.

        Soporta notacion decimal, octal (0177.0.0.1) y hexadecimal (0x7f.1)
        a traves del modulo ipaddress que normaliza antes de clasificar.
        Retorna False para hostnames (no IPs) — se verifican via DNS en otro paso.
        """
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            # host es un nombre de dominio, no una IP literal — no privado aqui
            return False
        return (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_unspecified
        )

    def _check_resolved_ips(self, host: str) -> tuple[str | None, str | None]:
        """Resuelve el hostname y comprueba que TODOS los A/AAAA sean publicos.

        Retorna (None, pinned_ip) si OK, o (mensaje_error, None) si hay problema.

        Fail-CLOSED: si la resolucion DNS falla (gaierror / OSError) se bloquea
        la solicitud — no se permite pasar solo porque no hay red, ya que eso
        abriría una ventana de bypass. Los tests sin red deben mockear getaddrinfo.

        El pinned_ip retornado es la primera IP publica resuelta; el caller debe
        usarla para conectar directamente y evitar una segunda resolución (TOCTOU
        DNS-rebinding).
        """
        try:
            infos = socket.getaddrinfo(host, None)
        except (socket.gaierror, OSError) as exc:
            # Fail-closed: DNS no disponible o dominio desconocido => bloquear.
            return (
                f"Resolución DNS fallida para {host}: {exc} (SSRF protection, fail-closed).",
                None,
            )
        first_public_ip: str | None = None
        for _family, _type, _proto, _canonname, sockaddr in infos:
            ip_str = str(sockaddr[0])
            try:
                addr = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_unspecified:
                return (
                    f"DNS rebinding bloqueado: {host} resuelve a IP privada/reservada "
                    f"{ip_str} (SSRF protection).",
                    None,
                )
            if first_public_ip is None:
                first_public_ip = ip_str
        return None, first_public_ip
