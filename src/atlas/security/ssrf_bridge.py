"""
Atlas Core — SSRF Bridge
Punto unico de salida a internet desde el sandbox local.
Solo el SSRF Bridge puede hacer requests HTTP/S desde codigo en sandbox.
Hermes-VPS tiene su propio modelo de egress (mas permisivo).

El SSRF Bridge es un control de Atlas Core, NO de Hermes-VPS.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from typing import Any


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


@dataclass(frozen=True)
class BridgeDecision:
    allowed: bool
    url: str
    reason: str
    domain: str


class SSRFBridge:
    """
    Proxy de egress para codigo en sandbox.
    Evalua URLs antes de permitir requests.
    El codigo en sandbox llama a SSRFBridge.check() antes de hacer
    cualquier request HTTP.
    """

    def __init__(self, extra_allowed: set[str] | None = None) -> None:
        self._allowed = DEFAULT_ALLOWED_DOMAINS | (extra_allowed or set())

    def check(self, url: str) -> BridgeDecision:
        """
        Evalua si una URL puede ser accedida desde el sandbox.
        Retorna BridgeDecision con allowed=True si esta permitida.
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

        domain = parsed.netloc.lower()
        # Eliminar puerto si existe
        domain = domain.split(":")[0]

        # Verificar allowlist PRIMERO (dominios anadidos explicitamente via
        # extra_allowed o add_domain tienen prioridad sobre BLOCKED_DOMAINS).
        # Esto permite a tests y al operador desbloquear localhost cuando sea
        # necesario (ej: servidor HTTP local de test).
        if self._is_allowed(domain):
            return BridgeDecision(
                allowed=True,
                url=url,
                reason=f"Dominio en allowlist: {domain}",
                domain=domain,
            )

        # Bloquear dominios internos/privados absolutos
        if domain in BLOCKED_DOMAINS:
            return BridgeDecision(
                allowed=False,
                url=url,
                reason=f"Dominio bloqueado absolutamente: {domain} (SSRF protection).",
                domain=domain,
            )

        # Bloquear IPs privadas
        if self._is_private_ip(domain):
            return BridgeDecision(
                allowed=False,
                url=url,
                reason=f"IP privada bloqueada: {domain} (SSRF protection).",
                domain=domain,
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
        if domain in self._allowed:
            return True
        # Comprobar subdominio: api.github.com → github.com
        parts = domain.split(".")
        for i in range(1, len(parts)):
            parent = ".".join(parts[i:])
            if parent in self._allowed:
                return True
        return False

    def _is_private_ip(self, host: str) -> bool:
        """Detecta IPs privadas / loopback / link-local."""
        private_patterns = [
            r"^10\.",
            r"^172\.(1[6-9]|2\d|3[01])\.",
            r"^192\.168\.",
            r"^127\.",
            r"^0\.",
            r"^169\.254\.",
            r"^::1$",
            r"^fc",
            r"^fd",
        ]
        return any(re.match(p, host) for p in private_patterns)
