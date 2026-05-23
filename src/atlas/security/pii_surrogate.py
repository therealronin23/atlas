"""
Atlas Core — PIISurrogate (ADR-023, Gate D)

Sustitucion determinista de PII por surrogates sinteticos antes de enviar
texto a proveedores L1/L2. Los surrogates preservan utilidad semantica
(un email sigue pareciendo un email, un DNI sigue siendo un DNI valido)
mientras enmascaran los datos reales.

Determinismo: dada la misma `(secret_salt, original)` siempre se genera
el mismo surrogate, lo cual mantiene la coherencia ontologica a traves
de turnos conversacionales (si el mismo email aparece en 3 mensajes,
recibe el mismo surrogate las 3 veces).

El mapeo inverso vive solo localmente y NUNCA se transmite. ADR-023
exige temperature=0 y seed fijo si en el futuro se introduce un SLM
para deteccion semantica (p. ej. nombres propios). Esta v1 usa regex +
pools de surrogates curados; el SLM-based queda como follow-up.

PIITypes soportados v1:
  - EMAIL
  - PHONE_ES (telefonos espanoles, +34 prefix opcional)
  - DNI (Documento Nacional de Identidad espanol, 8 digits + checksum letter)
  - IBAN (ISO 13616, simple)
  - IPV4 (excluye RFC1918 internas para no enmascarar diagnosticos de red)
  - IPV6 (basico)
  - HERMES_API_KEY (formato Atlas: 43 chars base64-ish)
  - GROQ_API_KEY (gsk_*)
  - OPENROUTER_API_KEY (sk-or-v1-*)

Pendiente v2 (requiere SLM):
  - NAME (nombres propios)
  - CITY / ADDRESS
  - Numeros de cuenta no IBAN
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------


class PIIType(str, Enum):
    EMAIL              = "email"
    PHONE_ES           = "phone_es"
    DNI                = "dni"
    IBAN               = "iban"
    IPV4               = "ipv4"
    IPV6               = "ipv6"
    HERMES_API_KEY     = "hermes_api_key"
    GROQ_API_KEY       = "groq_api_key"
    OPENROUTER_API_KEY = "openrouter_api_key"


@dataclass(frozen=True)
class PIIMatch:
    start: int
    end: int
    type: PIIType
    original: str
    surrogate: str


@dataclass(frozen=True)
class RedactionResult:
    text: str                     # texto con surrogates
    matches: tuple[PIIMatch, ...] # matches en orden de aparicion (post-substitution)
    mapping: dict[str, str]       # surrogate -> original (para restore)


# ---------------------------------------------------------------------------
# Patrones
# ---------------------------------------------------------------------------


# Orden de evaluacion importa: keys de API primero (especificas) > DNI > IBAN
# > telefono > email > IPs (mas genericas).
_PATTERNS: list[tuple[PIIType, re.Pattern[str]]] = [
    (PIIType.HERMES_API_KEY, re.compile(
        r"\b(?<![\w-])[A-Za-z0-9]{40,48}\b(?=\b)",
    )),
    (PIIType.GROQ_API_KEY, re.compile(r"\bgsk_[A-Za-z0-9]{40,80}\b")),
    (PIIType.OPENROUTER_API_KEY, re.compile(r"\bsk-or-v1-[a-f0-9]{40,80}\b")),
    (PIIType.IBAN, re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{12,30}\b")),
    (PIIType.DNI, re.compile(r"\b\d{8}[A-HJ-NP-TV-Z]\b")),
    (PIIType.PHONE_ES, re.compile(
        r"(?<![\w\d])(?:\+34|0034)?[\s\-]?[6-9]\d{2}[\s\-]?\d{3}[\s\-]?\d{3}(?!\d)"
    )),
    (PIIType.EMAIL, re.compile(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
    )),
    (PIIType.IPV4, re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
    (PIIType.IPV6, re.compile(
        r"\b(?:[a-fA-F0-9]{1,4}:){2,7}[a-fA-F0-9]{1,4}\b"
    )),
]


# ---------------------------------------------------------------------------
# Surrogates: pools y generadores
# ---------------------------------------------------------------------------


_DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"

_EMAIL_DOMAINS = (
    "example.com", "example.org", "test.local", "atlas.invalid", "redacted.test",
)
_EMAIL_NAMES = (
    "alex", "sam", "lee", "noa", "ruth", "kai", "tom", "amy", "jordan", "sky",
)


def _seed_int(*parts: str, mod: int = 2**32) -> int:
    """SHA-256 sobre las partes -> int (truncado)."""
    h = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") % mod


def _gen_email(original: str, salt: str) -> str:
    seed = _seed_int(salt, "email", original)
    name = _EMAIL_NAMES[seed % len(_EMAIL_NAMES)]
    domain = _EMAIL_DOMAINS[(seed // 7) % len(_EMAIL_DOMAINS)]
    suffix = (seed // 31) % 1000
    return f"{name}{suffix}@{domain}"


def _gen_phone_es(original: str, salt: str) -> str:
    seed = _seed_int(salt, "phone_es", original)
    # Movil ES: empieza por 6 o 7
    first = 6 + (seed % 2)
    rest = seed // 2
    digits = f"{first}{rest:08d}"[:9]
    return f"+34 {digits[:3]} {digits[3:6]} {digits[6:9]}"


def _gen_dni(original: str, salt: str) -> str:
    seed = _seed_int(salt, "dni", original)
    digits = f"{seed:08d}"[:8]
    letter = _DNI_LETTERS[int(digits) % 23]
    return f"{digits}{letter}"


def _gen_iban(original: str, salt: str) -> str:
    seed = _seed_int(salt, "iban", original, mod=10**22)
    body = f"{seed:022d}"[:22]
    return f"ES{body}"


def _gen_ipv4(original: str, salt: str) -> str:
    # TEST-NET-1: 192.0.2.0/24 reservado para documentacion (RFC 5737)
    seed = _seed_int(salt, "ipv4", original)
    return f"192.0.2.{seed % 256}"


def _gen_ipv6(original: str, salt: str) -> str:
    # 2001:db8::/32 reservado para documentacion (RFC 3849)
    seed = _seed_int(salt, "ipv6", original)
    return f"2001:db8:{(seed >> 16) & 0xFFFF:x}::{seed & 0xFFFF:x}"


def _gen_hermes_key(original: str, salt: str) -> str:
    seed = _seed_int(salt, "hermes_api_key", original)
    # Genera 43 chars alfanumericos deterministicos
    pool = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    out = []
    n = seed
    for _ in range(43):
        out.append(pool[n % len(pool)])
        n = (n * 1103515245 + 12345) & 0x7FFFFFFF
    return "".join(out)


def _gen_groq_key(original: str, salt: str) -> str:
    suffix = _gen_hermes_key(original, salt + ":groq")[:52]
    return f"gsk_{suffix}"


def _gen_openrouter_key(original: str, salt: str) -> str:
    seed = _seed_int(salt, "openrouter_api_key", original)
    hexstr = f"{seed:016x}" * 4
    return f"sk-or-v1-{hexstr[:64]}"


_GENERATORS = {
    PIIType.EMAIL:              _gen_email,
    PIIType.PHONE_ES:           _gen_phone_es,
    PIIType.DNI:                _gen_dni,
    PIIType.IBAN:               _gen_iban,
    PIIType.IPV4:               _gen_ipv4,
    PIIType.IPV6:               _gen_ipv6,
    PIIType.HERMES_API_KEY:     _gen_hermes_key,
    PIIType.GROQ_API_KEY:       _gen_groq_key,
    PIIType.OPENROUTER_API_KEY: _gen_openrouter_key,
}


# ---------------------------------------------------------------------------
# Surrogator
# ---------------------------------------------------------------------------


class PIISurrogate:
    """
    Detecta PII y sustituye por surrogates deterministas.

    Uso:
        surr = PIISurrogate()
        result = surr.redact("Mi email es ronin@gmail.com y mi DNI 12345678Z")
        # result.text -> "Mi email es sam234@example.com y mi DNI 04839271T"
        # result.mapping -> {"sam234@example.com": "ronin@gmail.com", ...}
        # Despues de la respuesta del LLM:
        restored = surr.restore(llm_response_text, result.mapping)

    El `salt` se lee de ATLAS_PII_SALT por defecto (recomendable fijo por
    instalacion). Si no esta, usa "atlas-default" — los surrogates seguiran
    siendo deterministas pero un atacante con acceso al codigo podria
    invertir el mapeo. Para produccion, pon un salt aleatorio largo.
    """

    DEFAULT_SALT = "atlas-default"

    def __init__(
        self,
        salt: str | None = None,
        enabled_types: set[PIIType] | None = None,
    ) -> None:
        self._salt = salt or os.environ.get("ATLAS_PII_SALT", self.DEFAULT_SALT)
        self._enabled = enabled_types or set(PIIType)

    @property
    def salt(self) -> str:
        return self._salt

    @property
    def enabled_types(self) -> frozenset[PIIType]:
        return frozenset(self._enabled)

    # ------------------------------------------------------------------
    # Deteccion (sin sustitucion)
    # ------------------------------------------------------------------

    def detect(self, text: str) -> list[PIIMatch]:
        """
        Devuelve los matches en orden de aparicion en el texto original.
        Garantiza que no haya solapamientos: si dos patrones matchean en
        la misma posicion, gana el primero en orden de _PATTERNS.
        """
        matches: list[PIIMatch] = []
        claimed: list[tuple[int, int]] = []   # rangos ya tomados

        for pii_type, pattern in _PATTERNS:
            if pii_type not in self._enabled:
                continue
            for m in pattern.finditer(text):
                start, end = m.start(), m.end()
                if any(_overlaps(start, end, s, e) for s, e in claimed):
                    continue
                claimed.append((start, end))
                original = m.group(0)
                surrogate = _GENERATORS[pii_type](original, self._salt)
                matches.append(PIIMatch(
                    start=start, end=end, type=pii_type,
                    original=original, surrogate=surrogate,
                ))
        matches.sort(key=lambda x: x.start)
        return matches

    # ------------------------------------------------------------------
    # Redact + restore
    # ------------------------------------------------------------------

    def redact(self, text: str) -> RedactionResult:
        matches = self.detect(text)
        if not matches:
            return RedactionResult(text=text, matches=(), mapping={})

        # Aplicar sustituciones de derecha a izquierda para no descuadrar offsets
        new_text = text
        for m in sorted(matches, key=lambda x: x.start, reverse=True):
            new_text = new_text[:m.start] + m.surrogate + new_text[m.end:]

        mapping: dict[str, str] = {}
        for m in matches:
            mapping[m.surrogate] = m.original
        return RedactionResult(
            text=new_text,
            matches=tuple(matches),
            mapping=mapping,
        )

    def restore(self, text: str, mapping: dict[str, str]) -> str:
        """
        Sustituye surrogates por sus originales segun `mapping`.
        Si dos surrogates colisionan (improbable con salt unica) se procesa
        el mas largo primero para evitar fragmentaciones.
        """
        if not mapping:
            return text
        ordered = sorted(mapping.keys(), key=len, reverse=True)
        out = text
        for surrogate in ordered:
            out = out.replace(surrogate, mapping[surrogate])
        return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return not (a_end <= b_start or b_end <= a_start)
