"""GoldenRoute (Foundry v0, ADR-069) — unidad: parsing acotado de peticiones,
guardas de ruta y generación de patch. La ceremonia E2E completa vive en
tests/acceptance/test_self_construction_golden_route.py."""

from __future__ import annotations

import pytest

from atlas.missions.golden_route import (
    UnsupportedRequestError,
    plan_from_request,
    unified_patch_for_append,
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
