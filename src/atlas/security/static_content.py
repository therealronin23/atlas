"""Small, data-only vetoes for declarative third-party text contributions."""

from __future__ import annotations

import re


# Metacharacters that are meaningful when a supposedly declarative document is
# later interpreted as an instruction. Newlines are intentionally not included.
_SHELL_METACHARS: tuple[str, ...] = (";", "|", "$(", "`", "&&", "||", ">", "<")
_SUSPICIOUS_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\beval\s*\(", "eval() en contenido"),
    (r"\bexec\s*\(", "exec() en contenido"),
    (r"__import__\s*\(", "__import__() en contenido"),
    (r"\bos\.system\s*\(", "os.system() en contenido"),
    (r"\bsubprocess\.", "subprocess en contenido"),
    (r"\bcurl\s+", "curl en contenido estático"),
    (r"\bwget\s+", "wget en contenido estático"),
    (r"base64\.(?:b64decode|decode)", "decodificación base64 en contenido"),
)

MAX_CONTENT_BYTES = 256_000
MIN_CONTENT_CHARS = 40


def scan_static_content(text: str) -> str | None:
    """Return a stable veto reason without evaluating or retaining instructions."""

    if len(text.strip()) < MIN_CONTENT_CHARS:
        return f"contenido demasiado corto (<{MIN_CONTENT_CHARS} chars)"
    if len(text.encode("utf-8")) > MAX_CONTENT_BYTES:
        return f"contenido demasiado grande (>{MAX_CONTENT_BYTES} bytes)"
    for char in _SHELL_METACHARS:
        if char in text:
            return f"metacaracter de shell detectado: {char!r}"
    for pattern, label in _SUSPICIOUS_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return label
    return None
