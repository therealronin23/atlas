"""Escáner de amenazas para contenido externo NO confiable (2026-08-05).

Complementa, no sustituye, a `static_content.scan_static_content`: aquél es
un **veto** para contribuciones declarativas (skills/plugins, ADR-075) y es
deliberadamente draconiano — cualquier `|` mata el texto. Esa política es
correcta ahí e inservible aquí: este módulo corre en la ruta de LECTURA
(`web_crawl`, `read_external_file`, resultados MCP), donde vetar rompería la
navegación normal y empujaría a desactivar la defensa entera.

Qué protege, concretamente. Atlas ya trata el contenido externo como dato
(`wrap_untrusted`, ADR-037) y ya degrada las mutaciones a HITL cuando el
loop está contaminado (`loop_is_tainted`). Las dos defensas descansan en lo
mismo: **que el operador que aprueba vea lo que el modelo ve**. Un texto
recuperado que esconde caracteres invisibles al humano pero visibles al
tokenizador, o que reescribe la terminal donde se pinta el resultado, rompe
justo esa premisa — no la política de permisos, sino la vista sobre la que
se ejerce.

Por eso la respuesta es **igualar las dos vistas**, no vetar:

- Los peligros de RENDERIZADO (escapes de terminal, caracteres ocultos) se
  neutralizan y se hacen visibles: la evidencia se conserva, el efecto no.
- Los peligros de CONTENIDO (pipe-a-intérprete, URLs con alfabetos
  mezclados) se REPORTAN sin tocar el texto: son legítimos de leer, y el
  operador necesita verlos tal cual para juzgarlos.

Fail-honest: un `ScanResult` sin amenazas significa "no encontré ninguna de
las clases que sé buscar", nunca "esto es seguro".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit

HIDDEN_CHAR_THREAT = "hidden_chars"
TERMINAL_ESCAPE_THREAT = "terminal_escape"
PIPE_TO_INTERPRETER_THREAT = "pipe_to_interpreter"
HOMOGRAPH_URL_THREAT = "homograph_url"


# --- caracteres invisibles -------------------------------------------------
# Clase Trojan Source (CVE-2021-42574). \t, \n y \r quedan FUERA a propósito:
# son formato legítimo de cualquier documento recuperado.
_HIDDEN_CHARS = re.compile(
    "["
    "­"              # soft hyphen
    "᠎"              # mongolian vowel separator
    "​-‏"       # ZWSP, ZWNJ, ZWJ, LRM, RLM
    "‪-‮"       # LRE, RLE, PDF, LRO, RLO (overrides bidi)
    "⁠-⁤"       # word joiner e invisibles matemáticos
    "⁦-⁩"       # LRI, RLI, FSI, PDI (aislantes bidi)
    "﻿"              # BOM / ZWNBSP
    "]"
)

# --- secuencias de escape de terminal --------------------------------------
# Orden importante: las formas largas (CSI/OSC) antes que el ESC suelto, o se
# consumiría el introductor y quedaría el payload como texto.
_TERMINAL_ESCAPES = re.compile(
    "(?:"
    r"(?:\x1b\]|\x9d)[^\x07\x1b]*(?:\x07|\x1b\\)?"   # OSC ... BEL/ST
    r"|(?:\x1b\[|\x9b)[0-?]*[ -/]*[@-~]"             # CSI ... final
    r"|\x1bP[^\x1b]*(?:\x1b\\)?"                     # DCS
    r"|\x1b[@-Z\\-_]"                                # ESC de 2 bytes
    r"|[\x1b\x9b]"                                   # ESC/CSI sueltos
    r"|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"             # C0 restantes (BEL, BS...)
    ")"
)

# --- descarga canalizada a un intérprete ------------------------------------
_PIPE_TO_INTERPRETER = re.compile(
    r"""(?:
        \b(?:curl|wget|iwr|Invoke-WebRequest|fetch)\b [^\n|]* \|\s*
        (?:sudo\s+)?
        (?:sh|bash|zsh|dash|ksh|fish|python[0-9.]*|perl|ruby|node|
           iex|Invoke-Expression|powershell|pwsh)\b
      |
        (?:sh|bash|zsh|python[0-9.]*)\s+-c\s* ["']?\$\(\s*(?:curl|wget)\b
    )""",
    re.IGNORECASE | re.VERBOSE,
)

_URLS = re.compile(r"\bhttps?://[^\s<>\"')\]}]+", re.IGNORECASE)

#: Cuántos caracteres de contexto se citan al describir una amenaza. Corto a
#: propósito: el reporte es para orientar al humano, no para reproducir el
#: payload dentro del propio aviso.
_EXCERPT = 60


@dataclass(frozen=True)
class ContentThreat:
    kind: str
    detail: str


@dataclass(frozen=True)
class ScanResult:
    """`threats` vacío = "ninguna de las clases conocidas", no "seguro"."""

    threats: tuple[ContentThreat, ...]
    sanitized: str

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(t.kind for t in self.threats))

    def summary(self) -> str:
        """Una línea para el encabezado de `wrap_untrusted`. Vacía si limpio."""
        if not self.threats:
            return ""
        return "; ".join(f"{t.kind}: {t.detail}" for t in self.threats)


def _script_of(char: str) -> str | None:
    """Alfabeto al que pertenece un carácter alfabético ('LATIN', 'CYRILLIC',
    'GREEK'...). None si no es alfabético (dígitos, '-', '.')."""
    if not char.isalpha():
        return None
    try:
        name = unicodedata.name(char)
    except ValueError:
        return None
    return name.split(" ", 1)[0]


def _homograph_hosts(text: str) -> list[str]:
    """Hostnames que MEZCLAN alfabetos — la señal real de suplantación IDN.

    Un hostname enteramente en otro alfabeto (`пример.рф`) es un dominio
    internacionalizado legítimo y NO se marca: marcarlo sería castigar a
    media internet por no escribir en latín, y ahogaría la señal de verdad.
    """
    suspicious: list[str] = []
    for match in _URLS.finditer(text):
        host = urlsplit(match.group(0)).hostname or ""
        if host.isascii():
            continue
        scripts = {s for s in (_script_of(c) for c in host) if s is not None}
        if len(scripts) > 1:
            suspicious.append(host)
    return suspicious


def scan_untrusted_content(text: str) -> ScanResult:
    """Escanea y neutraliza contenido externo. Nunca lanza: en la ruta de
    lectura, un escáner que revienta es peor que uno que no encuentra nada."""
    threats: list[ContentThreat] = []
    sanitized = text

    escapes = _TERMINAL_ESCAPES.findall(sanitized)
    if escapes:
        threats.append(ContentThreat(
            TERMINAL_ESCAPE_THREAT,
            f"{len(escapes)} secuencia(s) de control de terminal neutralizadas "
            "(podían reescribir lo que ve el operador)",
        ))
        sanitized = _TERMINAL_ESCAPES.sub("⟨ESC⟩", sanitized)

    hidden = _HIDDEN_CHARS.findall(sanitized)
    if hidden:
        codepoints = sorted({f"U+{ord(c):04X}" for c in hidden})
        threats.append(ContentThreat(
            HIDDEN_CHAR_THREAT,
            f"{len(hidden)} carácter(es) invisible(s) hechos visibles: "
            + ", ".join(codepoints),
        ))
        sanitized = _HIDDEN_CHARS.sub(
            lambda m: f"⟨U+{ord(m.group(0)):04X}⟩", sanitized,
        )

    # Los dos siguientes NO modifican el texto: son contenido legítimo de
    # leer, y el operador necesita verlo tal cual para juzgarlo.
    pipes = _PIPE_TO_INTERPRETER.findall(sanitized)
    if pipes:
        first = _PIPE_TO_INTERPRETER.search(sanitized)
        excerpt = first.group(0)[:_EXCERPT] if first else ""
        threats.append(ContentThreat(
            PIPE_TO_INTERPRETER_THREAT,
            f"{len(pipes)} descarga(s) canalizada(s) a un intérprete: {excerpt!r}",
        ))

    hosts = _homograph_hosts(sanitized)
    if hosts:
        threats.append(ContentThreat(
            HOMOGRAPH_URL_THREAT,
            "hostname(s) con alfabetos mezclados (posible suplantación IDN): "
            + ", ".join(sorted(set(hosts))[:5]),
        ))

    return ScanResult(threats=tuple(threats), sanitized=sanitized)
