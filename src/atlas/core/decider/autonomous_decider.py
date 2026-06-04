"""``AutonomousDecider`` — invariantes deterministas (ADR-040 slice 4).

Primer decisor que cambia conducta: autoriza o deniega sin humano, por política
fail-safe. NUNCA invoca un LLM en el path de autorización (D2): el juicio LLM es
evadible; aquí solo reglas deterministas. El humano queda on-the-loop vía la
telemetría del slice 3 y retoma lo irreversible en el modo ``hybrid`` (slice 5).

Invariantes (orden; el primer match gana; fail-safe D1):
  1. IOC en ``descriptor``/``reason`` → Deny (siempre).
  2. ``sensitivity == "high"`` → Deny (regla constitucional #4).
  3. acción ``mutating`` sin anclaje léxico en ``sanctioned_intent`` → Deny.
  4. acción ``mutating`` sin camino de undo (``reversible=False``) → Deny.
  5. resto (reversible / bajo riesgo) → Allow.

Invariante 4 (reversibilidad, slice 6): la autonomía solo procede sobre lo que
puede deshacer. ``reversible=True`` lo declara el call-site únicamente cuando hay
una primitiva de undo real registrable (snapshot OMEGA / ``remove_server`` MCP);
por defecto es ``False`` → una mutación irreversible se deniega (fail-safe D1).

Limitación honesta: el anclaje del invariante 3 es léxico (intersección de
tokens). Un descriptor en inglés (``write_file``) frente a una intención en otro
idioma no ancla y se deniega — comportamiento intencional de la postura estricta.
El endurecimiento del verificador con métricas reales es trabajo de slices
posteriores; aquí se fija la estructura del invariante, no su calibración fina.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

from atlas.core.decider.decider import Allow, DecisionAction, Deny, Verdict

_IOC_REGEXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"rm\s+-[rf]{1,2}\b"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+if="),
    re.compile(r":\(\)\s*\{"),                       # fork bomb
    re.compile(r"(curl|wget)\b[^|]*\|\s*(sh|bash|zsh)"),
    re.compile(r">\s*/dev/(sd|nvme|disk|hd)"),
    re.compile(r"\bshred\b"),
    re.compile(r"\bchmod\s+-?[rR]?\s*777\b"),
)

# Keywords de alta señal de credenciales (no incluye "token" por ser ubicuo).
_CREDENTIAL_KW: tuple[str, ...] = (
    "password",
    "secret",
    "api_key",
    "apikey",
    "private_key",
    "id_rsa",
    "ssh_key",
    "credential",
    ".env",
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _fold(text: str) -> str:
    """Minúsculas + sin acentos (robustez ES/EN)."""
    norm = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in norm if not unicodedata.combining(c))


def _tokens(text: str) -> set[str]:
    folded = _fold(text).replace("_", " ")
    return {t for t in _TOKEN_RE.findall(folded) if len(t) >= 3}


class AutonomousDecider:
    """Decisor por invariantes deterministas. Sin humano, sin LLM."""

    def decide(
        self,
        action: DecisionAction,
        sanctioned_intent: str,
        context: Mapping[str, object],
    ) -> Verdict:
        surface = _fold(f"{action.descriptor} {action.reason}")

        # 1. IOC — patrón peligroso o credenciales en la superficie de la acción.
        for rx in _IOC_REGEXES:
            if rx.search(surface):
                return Deny(reason="IOC: patrón peligroso en la acción")
        for kw in _CREDENTIAL_KW:
            if kw in surface:
                return Deny(reason="IOC: la acción toca credenciales")

        # 2. Constitucional — high siempre se deniega en modo autónomo.
        if action.sensitivity == "high":
            return Deny(reason="sensitivity=high (regla constitucional #4)")

        # 3. Coherencia — una mutación debe estar anclada en la intención.
        if action.mutating:
            desc_tokens = _tokens(action.descriptor)
            if not desc_tokens or desc_tokens.isdisjoint(_tokens(sanctioned_intent)):
                return Deny(reason="mutación no anclada en la intención sancionada")

        # 4. Reversibilidad — una mutación sin camino de undo se deniega.
        if action.mutating and not action.reversible:
            return Deny(reason="mutación irreversible: sin camino de undo")

        # 5. Default — reversible / bajo riesgo procede.
        return Allow(reason="invariantes ok")
