"""Mapeo staged → tests impactados, el que consume el gate de `.githooks/pre-commit`.

Por qué existe: el 2026-07-29 un cambio en `docs/design/mcp_catalog.yaml` rompió
los 37 tests del tronco MCP y el pre-commit pasó igual, porque sólo mapeaba
`src/<stem>.py → tests/test_<stem>*.py`. Los ficheros de datos no mapeaban a
NADA, y el glob por stem era además demasiado estrecho: `src/atlas/mcp/catalog.py`
sólo alcanzaba `tests/test_catalog_resources.py`, 1 de los 16 que lo ejercitan.

El mapeo se prueba contra el repo REAL, no contra un fixture: el fixture habría
pasado el día del fallo.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def test_staged_data_file_maps_to_tests_that_reference_it() -> None:
    """La regresión de 2026-07-29: tocar el catálogo debe arrastrar sus tests."""
    from atlas.engineering.impacted_tests import impacted_tests

    got = impacted_tests(["docs/design/mcp_catalog.yaml"], root=_ROOT)

    assert "tests/test_mcp_catalog_structured.py" in got
    assert "tests/test_adapter_registry.py" in got


def test_staged_src_module_maps_beyond_the_stem_glob() -> None:
    """`src/atlas/mcp/catalog.py` debe alcanzar los tests que lo importan, no
    sólo los que casan `tests/test_catalog*.py` por nombre."""
    from atlas.engineering.impacted_tests import impacted_tests

    got = impacted_tests(["src/atlas/mcp/catalog.py"], root=_ROOT)

    assert "tests/test_mcp_catalog_structured.py" in got
    assert "tests/test_mcp_trunk_aggregator.py" in got
    # el glob por stem se conserva, no se pierde cobertura previa
    assert "tests/test_catalog_resources.py" in got


def test_staged_test_file_maps_to_itself() -> None:
    from atlas.engineering.impacted_tests import impacted_tests

    got = impacted_tests(["tests/test_adapter_registry.py"], root=_ROOT)

    assert got == ["tests/test_adapter_registry.py"]


def test_result_is_deduped_and_sorted() -> None:
    from atlas.engineering.impacted_tests import impacted_tests

    got = impacted_tests(
        ["src/atlas/mcp/catalog.py", "docs/design/mcp_catalog.yaml"], root=_ROOT
    )

    assert got == sorted(set(got))


def test_mapping_is_capped_so_the_gate_cannot_become_the_full_suite() -> None:
    """La suite completa pica ~7,5 GB y earlyoom la mata: el gate nunca debe
    degenerar en ella por un cambio transversal."""
    from atlas.engineering.impacted_tests import impacted_tests

    got = impacted_tests(["src/atlas/core/orchestrator.py"], root=_ROOT, max_files=5)

    assert len(got) == 5


def test_unreferenced_path_maps_to_nothing(tmp_path: Path) -> None:
    from atlas.engineering.impacted_tests import impacted_tests

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_x(): pass\n", encoding="utf-8")

    assert impacted_tests(["docs/nada_referenciado.yaml"], root=tmp_path) == []


# ---------------------------------------------------------------------------
# Entrada CLI: es lo que invoca `.githooks/pre-commit`, así que se prueba como
# proceso real, no llamando a main() por dentro.
# ---------------------------------------------------------------------------


def test_cli_prints_one_mapped_test_per_line() -> None:
    import subprocess

    proc = subprocess.run(
        ["python", "-m", "atlas.engineering.impacted_tests", "docs/design/mcp_catalog.yaml"],
        cwd=_ROOT,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "src"},
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert "tests/test_mcp_catalog_structured.py" in proc.stdout.splitlines()


def test_cli_warns_on_stderr_when_the_mapping_is_truncated() -> None:
    """Si el cambio es transversal, el gate mide un subconjunto: debe decirlo,
    no dejar creer que cubrió todo."""
    import subprocess

    proc = subprocess.run(
        [
            "python", "-m", "atlas.engineering.impacted_tests",
            "--max-files", "3", "src/atlas/core/orchestrator.py",
        ],
        cwd=_ROOT,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "src"},
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert len(proc.stdout.splitlines()) == 3
    assert "truncad" in proc.stderr.lower()
