"""GoldenRoute (Foundry v0, ADR-069) — unidad: parsing acotado de peticiones,
guardas de ruta y generación de patch. La ceremonia E2E completa vive en
tests/acceptance/test_self_construction_golden_route.py."""

from __future__ import annotations

import pytest

from atlas.missions.golden_route import (
    UnsupportedRequestError,
    plan_from_request,
    unified_patch_for_append,
    unified_patch_for_rename,
)


# ------------------------------------------------------------------ parsing

def test_plan_parses_default_append_request() -> None:
    plan = plan_from_request(
        "añade una línea al final de docs/demo/GOLDEN_ROUTE_DEMO.md"
    )
    assert plan["action"] == "append_line"
    assert plan["path"] == "docs/demo/GOLDEN_ROUTE_DEMO.md"
    assert plan["line"]  # contenido por defecto determinista, no vacío


def test_plan_parses_quoted_line_request() -> None:
    plan = plan_from_request(
        'añade la línea "Hola Foundry" al final de docs/notes.md'
    )
    assert plan["line"] == "Hola Foundry"
    assert plan["path"] == "docs/notes.md"


def test_plan_rejects_unsupported_request() -> None:
    with pytest.raises(UnsupportedRequestError, match="v0 solo sabe"):
        plan_from_request("refactoriza el orchestrator entero")


@pytest.mark.parametrize(
    "path",
    [
        "src/atlas/core/orchestrator.py",  # fuera de docs/ (v0 es doc-only)
        "config/governance.json",          # ruta protegida SIEMPRE
        "/etc/passwd",                     # absoluta
        "docs/../src/atlas/cli.py",        # escape por ..
    ],
)
def test_plan_rejects_paths_outside_docs(path: str) -> None:
    with pytest.raises(UnsupportedRequestError):
        plan_from_request(f"añade una línea al final de {path}")


# --------------------------------------------------------- rename (T1.1 v2)

def test_plan_parses_rename_request() -> None:
    plan = plan_from_request("renombra old_name a new_name en src/atlas/demo.py")
    assert plan["action"] == "rename_identifier"
    assert plan["path"] == "src/atlas/demo.py"
    assert plan["old"] == "old_name"
    assert plan["new"] == "new_name"


@pytest.mark.parametrize(
    "path",
    [
        "src/atlas/demo.py",
        "tests/test_demo.py",
        "scripts/run.py",
        "config/app.json",
        "docs/demo.md",
    ],
)
def test_plan_rename_accepts_allowed_prefixes(path: str) -> None:
    plan = plan_from_request(f"renombra a a b en {path}")
    assert plan["path"] == path


@pytest.mark.parametrize(
    "path",
    [
        "vendor/lib.py",       # fuera de todo prefijo permitido
        "/etc/passwd",         # absoluta
        "src/../etc/passwd",   # escape por ..
    ],
)
def test_plan_rename_rejects_paths_outside_allowed_prefixes(path: str) -> None:
    with pytest.raises(UnsupportedRequestError):
        plan_from_request(f"renombra old a new en {path}")


def test_plan_rename_rejects_non_identifier_tokens() -> None:
    # "X"/"Y" deben ser identificadores válidos, no expresiones arbitrarias
    with pytest.raises(UnsupportedRequestError):
        plan_from_request("renombra 1viejo a nuevo en src/atlas/demo.py")


# -------------------------------------------------------------------- patch

def test_unified_patch_appends_line() -> None:
    patch = unified_patch_for_append(
        "docs/x.md", "a\nb\n", "nueva línea"
    )
    assert "--- a/docs/x.md" in patch
    assert "+++ b/docs/x.md" in patch
    assert "+nueva línea" in patch
    # las líneas existentes no se tocan (contexto, no cambios)
    assert "-a" not in patch and "-b" not in patch


def test_unified_patch_handles_missing_trailing_newline() -> None:
    patch = unified_patch_for_append("docs/x.md", "a\nb", "c")
    # el patch debe ser aplicable: b se reescribe con newline + c
    assert "+b" in patch and "+c" in patch


def test_unified_patch_handles_empty_file() -> None:
    patch = unified_patch_for_append("docs/x.md", "", "primera")
    # inserción pura: git apply/patch rechazan hunks que "eliminan" la línea
    # fantasma de un fichero de 0 bytes
    assert "@@ -0,0 +1 @@" in patch
    assert "+primera" in patch
    assert "\n-" not in patch


def test_unified_patch_for_rename_replaces_whole_word_occurrences() -> None:
    current = "def old_name():\n    return old_name\n"
    patch = unified_patch_for_rename("src/atlas/demo.py", current, "old_name", "new_name")
    assert "--- a/src/atlas/demo.py" in patch
    assert "+++ b/src/atlas/demo.py" in patch
    assert "-def old_name():" in patch
    assert "+def new_name():" in patch
    assert "-    return old_name" in patch
    assert "+    return new_name" in patch


def test_unified_patch_for_rename_does_not_touch_substrings() -> None:
    # "old" no debe reescribir "old_name" (whole-word, no substring)
    current = "old = 1\nold_name = 2\n"
    patch = unified_patch_for_rename("src/atlas/demo.py", current, "old", "new")
    assert "-old = 1" in patch and "+new = 1" in patch
    assert "old_name" not in patch.replace("old_name = 2", "")  # no aparece tocada
    assert "-old_name" not in patch
    assert "+new_name" not in patch


def test_unified_patch_for_rename_rejects_when_identifier_absent() -> None:
    with pytest.raises(UnsupportedRequestError, match="no aparece"):
        unified_patch_for_rename("src/atlas/demo.py", "def foo():\n    pass\n", "bar", "baz")
