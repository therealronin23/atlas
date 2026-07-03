"""
Tests para patch_format — técnica #18 (gramática apply_patch, OpenAI/Cline).
"""

from __future__ import annotations

from atlas.core.patch_format import (
    AddFileOp,
    DeleteFileOp,
    HunkLine,
    UpdateFileOp,
    UpdateHunk,
    apply_update_hunk,
    parse_patch_envelope,
)


# ---------------------------------------------------------------------------
# parse_patch_envelope
# ---------------------------------------------------------------------------

def test_parse_add_file():
    text = (
        "*** Begin Patch\n"
        "*** Add File: src/new_module.py\n"
        "+def hello():\n"
        "+    return 'hi'\n"
        "*** End Patch\n"
    )
    ops = parse_patch_envelope(text)
    assert ops == [AddFileOp(
        path="src/new_module.py",
        content="def hello():\n    return 'hi'\n",
    )]


def test_parse_delete_file():
    text = "*** Begin Patch\n*** Delete File: old_module.py\n*** End Patch\n"
    ops = parse_patch_envelope(text)
    assert ops == [DeleteFileOp(path="old_module.py")]


def test_parse_update_file_single_hunk():
    text = (
        "*** Begin Patch\n"
        "*** Update File: foo.py\n"
        "@@\n"
        " def hello():\n"
        "-    return 'old'\n"
        "+    return 'new'\n"
        "*** End of File\n"
        "*** End Patch\n"
    )
    ops = parse_patch_envelope(text)
    assert len(ops) == 1
    op = ops[0]
    assert isinstance(op, UpdateFileOp)
    assert op.path == "foo.py"
    assert op.move_to is None
    assert len(op.hunks) == 1
    assert op.hunks[0].lines == [
        HunkLine(" ", "def hello():"),
        HunkLine("-", "    return 'old'"),
        HunkLine("+", "    return 'new'"),
    ]


def test_parse_update_file_with_move_to():
    text = (
        "*** Begin Patch\n"
        "*** Update File: old_name.py\n"
        "*** Move to: new_name.py\n"
        "@@\n"
        "-x = 1\n"
        "+x = 2\n"
        "*** End Patch\n"
    )
    ops = parse_patch_envelope(text)
    op = ops[0]
    assert isinstance(op, UpdateFileOp)
    assert op.path == "old_name.py"
    assert op.move_to == "new_name.py"


def test_parse_update_file_without_explicit_eof_marker():
    """El marcador '*** End of File' es OPCIONAL — un nuevo '*** Update File:'
    o '*** End Patch' también cierra el bloque anterior."""
    text = (
        "*** Begin Patch\n"
        "*** Update File: a.py\n"
        "@@\n"
        "-a = 1\n"
        "+a = 2\n"
        "*** Update File: b.py\n"
        "@@\n"
        "-b = 1\n"
        "+b = 2\n"
        "*** End Patch\n"
    )
    ops = parse_patch_envelope(text)
    assert len(ops) == 2
    assert ops[0].path == "a.py"
    assert ops[1].path == "b.py"


def test_parse_multiple_hunks_same_file():
    text = (
        "*** Begin Patch\n"
        "*** Update File: foo.py\n"
        "@@\n"
        "-x = 1\n"
        "+x = 2\n"
        "@@\n"
        "-y = 1\n"
        "+y = 2\n"
        "*** End Patch\n"
    )
    ops = parse_patch_envelope(text)
    op = ops[0]
    assert isinstance(op, UpdateFileOp)
    assert len(op.hunks) == 2


def test_parse_mixed_operations():
    text = (
        "*** Begin Patch\n"
        "*** Add File: new.py\n"
        "+x = 1\n"
        "*** Delete File: gone.py\n"
        "*** Update File: existing.py\n"
        "@@\n"
        "-a = 1\n"
        "+a = 2\n"
        "*** End Patch\n"
    )
    ops = parse_patch_envelope(text)
    assert len(ops) == 3
    assert isinstance(ops[0], AddFileOp)
    assert isinstance(ops[1], DeleteFileOp)
    assert isinstance(ops[2], UpdateFileOp)


def test_parse_no_envelope_returns_empty_fail_soft():
    """Sin '*** Begin Patch' reconocible → lista vacía, no excepción."""
    assert parse_patch_envelope("texto cualquiera sin marcadores") == []


def test_parse_empty_string():
    assert parse_patch_envelope("") == []


# ---------------------------------------------------------------------------
# apply_update_hunk
# ---------------------------------------------------------------------------

def test_apply_update_hunk_unique_match():
    original = "def hello():\n    return 'old'\n"
    hunk = UpdateHunk(lines=[
        HunkLine(" ", "def hello():"),
        HunkLine("-", "    return 'old'"),
        HunkLine("+", "    return 'new'"),
    ])
    result = apply_update_hunk(original, hunk)
    assert result == "def hello():\n    return 'new'\n"


def test_apply_update_hunk_not_found_returns_none():
    original = "x = 1\n"
    hunk = UpdateHunk(lines=[HunkLine("-", "y = 1"), HunkLine("+", "y = 2")])
    assert apply_update_hunk(original, hunk) is None


def test_apply_update_hunk_ambiguous_returns_none():
    """Fail-closed (técnica #3 reutilizada): ancla repetida → no aplica."""
    original = "x = 1\nx = 1\n"
    hunk = UpdateHunk(lines=[HunkLine("-", "x = 1"), HunkLine("+", "x = 2")])
    assert apply_update_hunk(original, hunk) is None


def test_apply_update_hunk_empty_anchor_returns_none():
    """Hunk sin líneas de contexto/minus (solo +) no tiene ancla — rechazado."""
    hunk = UpdateHunk(lines=[HunkLine("+", "nuevo")])
    assert apply_update_hunk("cualquier cosa\n", hunk) is None


# ---------------------------------------------------------------------------
# Robustez ante salidas reales de modelos (medido en vivo 2026-06-27: Kimi
# omite prefijos y deja líneas en blanco dentro del hunk)
# ---------------------------------------------------------------------------

def test_parse_blank_line_inside_hunk_is_context():
    """Una línea totalmente vacía dentro de un hunk es contexto vacío, no fin
    del hunk (los modelos las emiten así en vez de ' ' prefijado)."""
    text = (
        "*** Begin Patch\n"
        "*** Update File: foo.py\n"
        "@@\n"
        " def a():\n"
        "\n"
        "-    x = 1\n"
        "+    x = 2\n"
        "*** End Patch\n"
    )
    ops = parse_patch_envelope(text)
    assert len(ops) == 1
    op = ops[0]
    assert isinstance(op, UpdateFileOp)
    lines = op.hunks[0].lines
    assert HunkLine(" ", "") in lines  # la línea vacía sobrevive como contexto
    assert HunkLine("-", "    x = 1") in lines


def test_parse_begin_patch_with_leading_whitespace():
    """' *** Begin Patch' con espacio inicial (visto en vivo) se reconoce."""
    text = (
        " *** Begin Patch\n"
        "*** Delete File: gone.py\n"
        "*** End Patch\n"
    )
    ops = parse_patch_envelope(text)
    assert ops == [DeleteFileOp(path="gone.py")]


def test_apply_update_hunk_tolerates_reindent():
    """Ancla con indentación desviada (modelo perdió espacios) aplica igual si
    calza línea-a-línea ignorando whitespace y es única (técnica #13)."""
    original = "class A:\n    def f(self):\n        return 1\n"
    hunk = UpdateHunk(lines=[
        HunkLine(" ", "   def f(self):"),      # 3 espacios (perdió 1)
        HunkLine("-", "       return 1"),       # 7 espacios (perdió 1)
        HunkLine("+", "       return 2"),
    ])
    result = apply_update_hunk(original, hunk)
    assert result is not None
    assert "return 2" in result
    assert "        return 2" in result  # la indentación REAL del archivo se preserva


def test_apply_update_hunk_reindent_still_fail_closed_on_ambiguity():
    original = "  x = 1\n    x = 1\n"
    hunk = UpdateHunk(lines=[HunkLine("-", "\tx = 1"), HunkLine("+", "x = 2")])
    assert apply_update_hunk(original, hunk) is None


def test_apply_update_hunk_prefixless_insertion_recovery():
    """Recuperación del patrón medido en vivo (Kimi K2.6): hunk SIN ningún
    marcador +/- donde las primeras líneas existen en el archivo (ancla) y las
    restantes no (inserción). Solo se activa sin +/-; el ancla debe ser única."""
    original = (
        "    def search_by_tag(self, tag: str) -> list[Lesson]:\n"
        "        return [lesson for lesson in self.all() if tag in lesson.tags]\n"
    )
    # Salida literal de Kimi: todo como contexto, sin prefijos +/-
    hunk = UpdateHunk(lines=[
        HunkLine(" ", "   def search_by_tag(self, tag: str) -> list[Lesson]:"),
        HunkLine(" ", "       return [lesson for lesson in self.all() if tag in lesson.tags]"),
        HunkLine(" ", ""),
        HunkLine(" ", "   def stats(self) -> dict[str, Any]:"),
        HunkLine(" ", "       lessons = self.all()"),
        HunkLine(" ", '       return {"total": len(lessons)}'),
    ])
    result = apply_update_hunk(original, hunk)
    assert result is not None
    assert "def stats" in result
    assert "def search_by_tag" in result  # el ancla sobrevive
    assert "    def stats" in result       # reindentado a la indentación real


def test_apply_update_hunk_prefixless_no_anchor_fails_closed():
    """Sin +/- Y sin NINGUNA línea que exista en el archivo → None (no hay
    ancla, no se inventa dónde insertar)."""
    original = "x = 1\n"
    hunk = UpdateHunk(lines=[
        HunkLine(" ", "def nuevo():"),
        HunkLine(" ", "    pass"),
    ])
    assert apply_update_hunk(original, hunk) is None


def test_parse_prefixless_module_level_lines_as_context():
    """Línea de hunk SIN prefijo que empieza en columna 0 (ej. 'def foo():' a
    nivel de módulo, medido en vivo con Kimi) — se trata como contexto con el
    texto completo, no como fin del hunk."""
    text = (
        "*** Begin Patch\n"
        "*** Update File: mod.py\n"
        "@@\n"
        "def existing():\n"
        "    return 1\n"
        "\n"
        "def new_function():\n"
        "    return 2\n"
        "*** End Patch\n"
    )
    ops = parse_patch_envelope(text)
    assert len(ops) == 1
    op = ops[0]
    assert isinstance(op, UpdateFileOp)
    lines = op.hunks[0].lines
    assert HunkLine(" ", "def existing():") in lines
    assert HunkLine(" ", "def new_function():") in lines


def test_prefixless_module_level_insertion_end_to_end():
    """El caso completo medido en vivo: hunk prefix-less a nivel de módulo,
    ancla = función existente, inserción = función nueva."""
    original = "def existing():\n    return 1\n"
    text = (
        "*** Begin Patch\n"
        "*** Update File: mod.py\n"
        "@@\n"
        "def existing():\n"
        "    return 1\n"
        "\n"
        "def new_function():\n"
        "    return 2\n"
        "*** End Patch\n"
    )
    ops = parse_patch_envelope(text)
    result = apply_update_hunk(original, ops[0].hunks[0])
    assert result is not None
    assert "def new_function" in result
    assert "def existing" in result
