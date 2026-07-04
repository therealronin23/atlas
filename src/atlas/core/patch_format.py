"""
Atlas Core — Patch Format (técnica #18, patrón OpenAI Codex CLI / adoptado por Cline)

Gramática `*** Begin Patch ... *** End Patch` como alternativa a SEARCH/REPLACE:
envelope orientado a ARCHIVO (Add/Delete/Update explícitos), no a un stream de
líneas ambiguo. Confirmado por dos fuentes independientes (OpenAI diseñó el
formato explícitamente para evitar los fallos de matching difuso de SEARCH/
REPLACE; Cline lo adoptó en su SDK reciente por el mismo motivo).

NOTA de nombres: existe `ColdUpdateManager._apply_patch` (aplica diffs
unificados vía `git apply`, no relacionado). Este módulo NO reutiliza ese
nombre como símbolo público — evita colisión semántica.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "AddFileOp", "DeleteFileOp", "UpdateFileOp", "PatchOp",
    "HunkLine", "UpdateHunk",
    "parse_patch_envelope", "apply_update_hunk",
]


@dataclass(frozen=True)
class HunkLine:
    prefix: str  # " " (contexto) | "-" (elimina) | "+" (añade)
    text: str


@dataclass(frozen=True)
class UpdateHunk:
    lines: list[HunkLine] = field(default_factory=list)


@dataclass(frozen=True)
class AddFileOp:
    path: str
    content: str


@dataclass(frozen=True)
class DeleteFileOp:
    path: str


@dataclass(frozen=True)
class UpdateFileOp:
    path: str
    hunks: list[UpdateHunk] = field(default_factory=list)
    move_to: str | None = None


PatchOp = AddFileOp | DeleteFileOp | UpdateFileOp

_BEGIN = "*** Begin Patch"
_END = "*** End Patch"
_EOF_MARK = "*** End of File"
_ADD_RE = re.compile(r"^\*\*\* Add File: (.+)$")
_DELETE_RE = re.compile(r"^\*\*\* Delete File: (.+)$")
_UPDATE_RE = re.compile(r"^\*\*\* Update File: (.+)$")
_MOVE_RE = re.compile(r"^\*\*\* Move to: (.+)$")


def _is_section_marker(line: str) -> bool:
    s = line.strip()
    return (
        s.startswith("*** Add File:")
        or s.startswith("*** Delete File:")
        or s.startswith("*** Update File:")
        or s == _END
    )


def parse_patch_envelope(text: str) -> list[PatchOp]:
    """Parsea el envelope `*** Begin Patch ... *** End Patch`.

    Fail-soft (igual que el regex de SEARCH/REPLACE): si no hay envelope
    reconocible, devuelve lista vacía en vez de lanzar excepción — el
    llamador decide qué hacer con "sin ediciones".
    """
    lines = text.splitlines()
    i = 0
    while i < len(lines) and lines[i].strip() != _BEGIN:
        i += 1
    if i >= len(lines):
        return []
    i += 1

    ops: list[PatchOp] = []
    while i < len(lines):
        line = lines[i]
        if line.strip() == _END:
            break

        m = _ADD_RE.match(line.strip())
        if m:
            path = m.group(1).strip()
            i += 1
            content_lines: list[str] = []
            while i < len(lines) and lines[i].startswith("+"):
                content_lines.append(lines[i][1:])
                i += 1
            content = "\n".join(content_lines) + ("\n" if content_lines else "")
            ops.append(AddFileOp(path=path, content=content))
            continue

        m = _DELETE_RE.match(line.strip())
        if m:
            ops.append(DeleteFileOp(path=m.group(1).strip()))
            i += 1
            continue

        m = _UPDATE_RE.match(line.strip())
        if m:
            path = m.group(1).strip()
            i += 1
            move_to: str | None = None
            if i < len(lines):
                mm = _MOVE_RE.match(lines[i].strip())
                if mm:
                    move_to = mm.group(1).strip()
                    i += 1

            hunks: list[UpdateHunk] = []
            current: list[HunkLine] = []
            while i < len(lines):
                subline = lines[i]
                if subline.strip() == _EOF_MARK:
                    i += 1
                    break
                if _is_section_marker(subline):
                    break
                if subline.startswith("@@"):
                    if current:
                        hunks.append(UpdateHunk(lines=current))
                        current = []
                    i += 1
                    continue
                if subline.startswith(("+", "-", " ")):
                    current.append(HunkLine(prefix=subline[0], text=subline[1:]))
                    i += 1
                    continue
                # Línea sin prefijo reconocible dentro del hunk (medido en
                # vivo, Kimi K2.6): líneas vacías y código a nivel de módulo
                # (columna 0, ej. "def foo():") llegan SIN el prefijo " ".
                # Se tratan como contexto con su texto completo — el modo
                # prefix-less de apply_update_hunk resuelve la semántica.
                current.append(HunkLine(prefix=" ", text=subline))
                i += 1
                continue
            if current:
                hunks.append(UpdateHunk(lines=current))
            ops.append(UpdateFileOp(path=path, hunks=hunks, move_to=move_to))
            continue

        i += 1  # línea suelta (blank, etc.) — se ignora

    return ops


def _apply_prefixless_insertion(original: str, hunk: UpdateHunk) -> str | None:
    """Hunk sin marcadores +/-: el prefijo de líneas que SÍ existen en el
    archivo (match tolerante a reindentado) es el ancla; el hunk completo
    (reindentado) la reemplaza — efecto neto: inserción tras el ancla."""
    hunk_texts = [hl.text for hl in hunk.lines]
    if not any(t.strip() for t in hunk_texts):
        return None

    original_lines = original.splitlines(keepends=True)
    stripped_original = [ln.rstrip("\n").strip() for ln in original_lines]

    # Ancla = prefijo más largo de líneas no-vacías del hunk que aparecen
    # consecutivas en el archivo. Mínimo 1 línea real de ancla.
    anchor: list[str] = []
    for text in hunk_texts:
        candidate = anchor + [text]
        stripped_candidate = [t.strip() for t in candidate]
        n = len(stripped_candidate)
        found = sum(
            1 for i in range(len(stripped_original) - n + 1)
            if stripped_original[i : i + n] == stripped_candidate
        )
        if found >= 1:
            anchor = candidate
        else:
            break
    if not any(t.strip() for t in anchor):
        return None  # ninguna línea del hunk existe en el archivo — sin ancla

    stripped_anchor = [t.strip() for t in anchor]
    n = len(stripped_anchor)
    matches = [
        i for i in range(len(stripped_original) - n + 1)
        if stripped_original[i : i + n] == stripped_anchor
    ]
    if len(matches) != 1:
        return None  # ancla ambigua o desaparecida — fail-closed

    start = matches[0]
    window = original_lines[start : start + n]
    first_real = window[0]
    real_indent = first_real[: len(first_real) - len(first_real.lstrip(" "))]
    hunk_first = anchor[0]
    hunk_indent = hunk_first[: len(hunk_first) - len(hunk_first.lstrip(" "))]
    delta = len(real_indent) - len(hunk_indent)

    def _reindent(line: str) -> str:
        if not line.strip():
            return line
        if delta > 0:
            return " " * delta + line
        if delta < 0:
            return line[min(-delta, len(line) - len(line.lstrip(" "))):]
        return line

    reindented = [_reindent(t) for t in hunk_texts]
    newline = "\n" if window[0].endswith("\n") else ""
    replacement_block = "\n".join(reindented) + (newline if reindented else "")

    return (
        "".join(original_lines[:start])
        + replacement_block
        + "".join(original_lines[start + n :])
    )


def apply_update_hunk(original: str, hunk: UpdateHunk) -> str | None:
    """Aplica un hunk (contexto+minus como ancla, contexto+plus como reemplazo)
    sobre *original*. Fail-closed (técnica #3 reutilizada): el ancla debe
    aparecer EXACTAMENTE una vez, o no se aplica (None).

    Si el match exacto falla, cae a un match tolerante a reindentado (técnica
    #13, misma cascada que SEARCH/REPLACE): compara línea a línea ignorando el
    whitespace inicial; si hay EXACTAMENTE una ventana que calza, reaplica el
    delta de indentación real del archivo sobre las líneas nuevas. Medido en
    vivo (2026-06-27): los modelos pierden espacios de indentación al emitir
    hunks, y el prefijo del diff consume además el primer carácter.
    """
    has_markers = any(hl.prefix in ("+", "-") for hl in hunk.lines)
    if not has_markers:
        # Recuperación del patrón "prefix-less" (medido en vivo, Kimi K2.6):
        # el modelo emite TODO como contexto — las líneas que existen en el
        # archivo son el ancla, las que no existen son la inserción. Acotado:
        # solo sin ningún +/-, ancla única obligatoria, fail-closed si no.
        return _apply_prefixless_insertion(original, hunk)

    search_lines = [hl.text for hl in hunk.lines if hl.prefix in (" ", "-")]
    replace_lines = [hl.text for hl in hunk.lines if hl.prefix in (" ", "+")]
    search_text = "\n".join(search_lines)
    if search_text.strip() == "":
        return None
    count = original.count(search_text)
    if count == 1:
        replace_text = "\n".join(replace_lines)
        return original.replace(search_text, replace_text, 1)
    if count > 1:
        return None  # ambiguo — fail-closed, no adivinar

    # Fallback tolerante a reindentado (técnica #13).
    original_lines = original.splitlines(keepends=True)
    stripped_search = [ln.strip() for ln in search_lines]
    n = len(search_lines)
    if n == 0 or n > len(original_lines):
        return None

    matches: list[int] = []
    for i in range(len(original_lines) - n + 1):
        window = original_lines[i : i + n]
        if [ln.rstrip("\n").strip() for ln in window] == stripped_search:
            matches.append(i)
    if len(matches) != 1:
        return None

    start = matches[0]
    window = original_lines[start : start + n]
    first_real = window[0]
    real_indent = first_real[: len(first_real) - len(first_real.lstrip(" "))]
    # Delta: diferencia entre la indentación real y la que trae el hunk.
    hunk_first = search_lines[0]
    hunk_indent = hunk_first[: len(hunk_first) - len(hunk_first.lstrip(" "))]
    delta = len(real_indent) - len(hunk_indent)

    def _reindent(line: str) -> str:
        if not line.strip():
            return line
        if delta > 0:
            return " " * delta + line
        if delta < 0:
            return line[min(-delta, len(line) - len(line.lstrip(" "))):]
        return line

    reindented = [_reindent(ln) for ln in replace_lines]
    newline = "\n" if window[0].endswith("\n") else ""
    replacement_block = "\n".join(reindented) + (newline if reindented else "")

    return (
        "".join(original_lines[:start])
        + replacement_block
        + "".join(original_lines[start + n :])
    )
