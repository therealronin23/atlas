"""Fuzzer determinista puro para mutaciones de poc_script.

Genera mutaciones de un string poc_script sin ejecutar los payloads.
Misma entrada → misma salida (determinista).

Familias de mutación:
  1. Flip de literales booleanos/numéricos
  2. Inyección de caracteres especiales en posiciones clave
  3. Valores límite (strings vacíos, enteros extremos)
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterator

from atlas.core.verify import Evidence, Verdict
from atlas.security.authorization import (
    AuthorizationGrant,
    PoCReproductionVerifier,
    SecurityFinding,
)


# ---------------------------------------------------------------------------
# Familia 1 — flip de literales booleanos/numéricos
# ---------------------------------------------------------------------------

_BOOL_FLIPS: list[tuple[str, str]] = [
    ("True", "False"),
    ("False", "True"),
    ("true", "false"),
    ("false", "true"),
]

_INT_REPLACEMENTS: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"\b0\b"), ["1", "-1"]),
    (re.compile(r"\b1\b"), ["0", "-1"]),
    (re.compile(r"\b-?\d{2,}\b"), ["0", "2147483647", "-2147483648"]),
]


def _family1_bool_numeric(script: str) -> Iterator[str]:
    """Flip booleanos y sustituye literales numéricos."""
    for original, replacement in _BOOL_FLIPS:
        if original in script:
            yield script.replace(original, replacement, 1)

    for pattern, replacements in _INT_REPLACEMENTS:
        match = pattern.search(script)
        if match:
            start, end = match.span()
            for rep in replacements:
                yield script[:start] + rep + script[end:]


# ---------------------------------------------------------------------------
# Familia 2 — inyección de caracteres especiales
# ---------------------------------------------------------------------------

_SPECIAL_CHARS: list[str] = [
    "\x00",          # null byte
    "'",             # comilla simple
    '"',             # comilla doble
    "\\",            # backslash
    "\n",            # newline
    "../",           # path traversal
    "<script>",      # XSS stub
    "';--",          # SQL injection stub
]

# Posiciones donde inyectar: tras el primer token (espacio/igual/paréntesis)
_INJECT_POINTS: re.Pattern[str] = re.compile(r'(?<=[=(\s])')


def _family2_special_chars(script: str) -> Iterator[str]:
    """Inserta caracteres especiales en el primer punto de inyección."""
    match = _INJECT_POINTS.search(script)
    if not match:
        # Fallback: insertar al principio
        pos = 0
    else:
        pos = match.start()

    for char in _SPECIAL_CHARS:
        yield script[:pos] + char + script[pos:]


# ---------------------------------------------------------------------------
# Familia 3 — valores límite
# ---------------------------------------------------------------------------

_STRING_LITERAL: re.Pattern[str] = re.compile(r'("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')')
_INT_LITERAL: re.Pattern[str] = re.compile(r'\b\d+\b')

_BOUNDARY_STRINGS: list[str] = ['""', "''", '"' + "A" * 256 + '"']
_BOUNDARY_INTS: list[str] = ["0", "2147483647", "4294967295"]


def _family3_boundary_values(script: str) -> Iterator[str]:
    """Sustituye el primer string/int por valores límite."""
    str_match = _STRING_LITERAL.search(script)
    if str_match:
        start, end = str_match.span()
        for boundary in _BOUNDARY_STRINGS:
            yield script[:start] + boundary + script[end:]

    int_match = _INT_LITERAL.search(script)
    if int_match:
        start, end = int_match.span()
        for boundary in _BOUNDARY_INTS:
            yield script[:start] + boundary + script[end:]


# ---------------------------------------------------------------------------
# Función pública
# ---------------------------------------------------------------------------

def fuzz_script(poc_script: str) -> list[str]:
    """Genera mutaciones deterministas del poc_script.

    Misma entrada → misma salida (lista ordenada, sin explosión combinatoria).
    Los payloads son strings; no se ejecutan.

    Args:
        poc_script: Fragmento de código o comando a mutar.

    Returns:
        Lista de strings mutados, máx ~20 elementos, orden determinista.
    """
    seen: set[str] = set()
    payloads: list[str] = []

    generators = [
        _family1_bool_numeric(poc_script),
        _family2_special_chars(poc_script),
        _family3_boundary_values(poc_script),
    ]

    # Límite global para evitar explosión combinatoria
    limit = 20

    for gen in generators:
        for payload in gen:
            if payload == poc_script:
                continue
            if payload not in seen:
                seen.add(payload)
                payloads.append(payload)
            if len(payloads) >= limit:
                return payloads

    return payloads


# ---------------------------------------------------------------------------
# FuzzResult + FuzzReport dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FuzzResult:
    finding: SecurityFinding
    evidence: Evidence


@dataclass(frozen=True)
class FuzzReport:
    payloads_generated: int
    reproduced_count: int
    results: tuple[FuzzResult, ...]


# ---------------------------------------------------------------------------
# Harness público
# ---------------------------------------------------------------------------


def _select_grant(
    grants: list[AuthorizationGrant],
    finding: SecurityFinding,
) -> AuthorizationGrant | None:
    """Primer grant cuyo target matchee y capability coincida con el finding."""
    for grant in grants:
        if (
            grant.capability == finding.capability
            and grant.target.matches(finding.target)
        ):
            return grant
    return None


def run_fuzz_harness(
    base_finding: SecurityFinding,
    grants: list[AuthorizationGrant],
    verifier: PoCReproductionVerifier,
) -> FuzzReport:
    """Genera mutaciones del poc_script del base_finding y verifica cada una.

    Fail-closed: si ningún grant cubre target+capability, se llama igualmente
    al verifier con el primer grant de la lista (que denegará por autorización).
    Si la lista está vacía se lanza ValueError — no hay forma segura de proceder.
    """
    if not grants:
        raise ValueError("Se requiere al menos un grant para ejecutar el harness")

    payloads = fuzz_script(base_finding.poc_script)
    results: list[FuzzResult] = []

    for payload in payloads:
        digest = hashlib.sha256(payload.encode()).hexdigest()
        finding = SecurityFinding(
            id=f"{base_finding.id}-fuzz-{digest[:8]}",
            target=base_finding.target,
            capability=base_finding.capability,
            description=base_finding.description,
            poc_script=payload,
            evidence_hash=digest,
        )
        grant = _select_grant(grants, finding) or grants[0]
        evidence = verifier.verify(finding, grant)
        results.append(FuzzResult(finding=finding, evidence=evidence))

    reproduced = sum(1 for r in results if r.evidence.verdict == Verdict.PASS)
    return FuzzReport(
        payloads_generated=len(payloads),
        reproduced_count=reproduced,
        results=tuple(results),
    )
