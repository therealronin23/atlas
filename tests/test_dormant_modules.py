"""Detector de módulos dormidos por resolución REAL de imports (2026-07-31).

Existe por un fallo medido, no por gusto. ``scripts/sanitation_audit.py``
buscaba importadores con la heurística de texto
``import .*\\bmod\\b|from .*\\bmod\\b import|\\.mod\\b``. Esa tercera rama
(``\\.mod\\b``) da un FALSO NEGATIVO —el peor sentido para un radar— en
cuanto el nombre del módulo aparece como texto literal en cualquier otro
sitio: un acceso a atributo, una clave de diccionario, una cadena, un
comentario. En este repo pasaba de verdad con ``engineering/reproduction.py``
(489 loc) y ``engineering/diagnostics.py`` (391 loc): las palabras
``reproduction`` y ``diagnostics`` aparecen como texto en
``logging/merkle_logger.py`` y ``core/doctor.py``, así que **el radar daba
por vivos a los dos módulos dormidos más grandes del repo**.

El caso RED de esta suite es exactamente ése (``TestTextMentionIsNotAnImport``).

Mismo principio que ``ecosystem_drift.py`` y ``component_wiring_drift.py``:
determinista, barato, nunca LLM/red, la lógica vive aquí en TDD real y
``sanitation_audit.py`` sólo importa y envuelve fail-open.
"""

from __future__ import annotations

from pathlib import Path

from atlas.core.self_maintenance.dormant_modules import dormant_modules


def _mod(repo: Path, rel: str, body: str = "") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


class TestTextMentionIsNotAnImport:
    """EL caso que motivó todo esto: mención textual ≠ importador."""

    def test_attribute_access_with_the_module_name_is_not_an_importer(
        self, tmp_path: Path
    ) -> None:
        # `self.reproduction` casaba con `\.reproduction\b` en el regex viejo.
        _mod(tmp_path, "src/atlas/engineering/reproduction.py", "VALUE = 1\n")
        _mod(
            tmp_path,
            "src/atlas/logging/merkle_logger.py",
            "class L:\n    def emit(self) -> None:\n        self.reproduction = 1\n",
        )

        assert "src/atlas/engineering/reproduction.py" in dormant_modules(tmp_path)

    def test_module_name_inside_a_string_literal_is_not_an_importer(
        self, tmp_path: Path
    ) -> None:
        _mod(tmp_path, "src/atlas/engineering/diagnostics.py", "VALUE = 1\n")
        _mod(tmp_path, "src/atlas/core/doctor.py", 'SECTIONS = ["diagnostics", "health"]\n')

        assert "src/atlas/engineering/diagnostics.py" in dormant_modules(tmp_path)

    def test_module_name_in_a_comment_is_not_an_importer(self, tmp_path: Path) -> None:
        _mod(tmp_path, "src/atlas/engineering/hypotheses.py", "VALUE = 1\n")
        _mod(tmp_path, "src/atlas/core/notes.py", "# ver .hypotheses para el detalle\nX = 1\n")

        assert "src/atlas/engineering/hypotheses.py" in dormant_modules(tmp_path)


class TestRealImportsAreDetected:
    def test_from_package_import_module(self, tmp_path: Path) -> None:
        _mod(tmp_path, "src/atlas/engineering/review.py", "VALUE = 1\n")
        _mod(tmp_path, "src/atlas/core/user.py", "from atlas.engineering import review\n")

        assert "src/atlas/engineering/review.py" not in dormant_modules(tmp_path)

    def test_from_module_import_name(self, tmp_path: Path) -> None:
        _mod(tmp_path, "src/atlas/engineering/review.py", "VALUE = 1\n")
        _mod(tmp_path, "src/atlas/core/user.py", "from atlas.engineering.review import VALUE\n")

        assert "src/atlas/engineering/review.py" not in dormant_modules(tmp_path)

    def test_plain_dotted_import(self, tmp_path: Path) -> None:
        _mod(tmp_path, "src/atlas/engineering/review.py", "VALUE = 1\n")
        _mod(tmp_path, "src/atlas/core/user.py", "import atlas.engineering.review\n")

        assert "src/atlas/engineering/review.py" not in dormant_modules(tmp_path)

    def test_relative_import_from_sibling(self, tmp_path: Path) -> None:
        _mod(tmp_path, "src/atlas/engineering/review.py", "VALUE = 1\n")
        _mod(tmp_path, "src/atlas/engineering/other.py", "from .review import VALUE\n")

        assert "src/atlas/engineering/review.py" not in dormant_modules(tmp_path)

    def test_relative_import_from_parent_package(self, tmp_path: Path) -> None:
        _mod(tmp_path, "src/atlas/engineering/review.py", "VALUE = 1\n")
        _mod(tmp_path, "src/atlas/engineering/deep/inner.py", "from ..review import VALUE\n")

        assert "src/atlas/engineering/review.py" not in dormant_modules(tmp_path)

    def test_deferred_import_inside_a_function_counts(self, tmp_path: Path) -> None:
        # El punto ciego que `_CLASSIFIED_ZERO_IMPORTERS` documenta para
        # live_loop.py (ADR-074): import diferido dentro de una función.
        # El AST sí lo ve; un escáner "a nivel de módulo" no.
        _mod(tmp_path, "src/atlas/immunity/live_loop.py", "VALUE = 1\n")
        _mod(
            tmp_path,
            "src/atlas/core/orchestrator.py",
            "def enable() -> None:\n    from atlas.immunity.live_loop import VALUE\n",
        )

        assert "src/atlas/immunity/live_loop.py" not in dormant_modules(tmp_path)

    def test_importer_living_in_scripts_counts(self, tmp_path: Path) -> None:
        _mod(tmp_path, "src/atlas/engineering/review.py", "VALUE = 1\n")
        _mod(tmp_path, "scripts/do_thing.py", "from atlas.engineering.review import VALUE\n")

        assert "src/atlas/engineering/review.py" not in dormant_modules(tmp_path)


class TestSubprocessEntrypoints:
    """`python -m atlas.x.y` desde un hook/shell es un caller de producción
    real, invisible a cualquier escaneo de imports. Es literalmente el motivo
    del entry `impacted_tests.py` en la tabla de clasificados."""

    def test_python_dash_m_in_a_shell_hook_counts_as_caller(self, tmp_path: Path) -> None:
        _mod(tmp_path, "src/atlas/engineering/impacted_tests.py", "VALUE = 1\n")
        hook = tmp_path / ".githooks" / "pre-commit"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text(
            "#!/bin/sh\npython -m atlas.engineering.impacted_tests --changed\n",
            encoding="utf-8",
        )

        assert "src/atlas/engineering/impacted_tests.py" not in dormant_modules(tmp_path)


class TestDynamicDispatchByModuleName:
    """Despacho dinámico por nombre de módulo: registros que se spawnean con
    ``[exe, "-m", spec.module]`` (``mcp/trunk_server.py:86`), mapas de
    servidores nativos (``security/sentinel_gate.py``), ``import_module(...)``.
    Ningún escaneo de imports puede verlo, y son cableado REAL.

    La precisión se conserva porque lo que cuenta es la ruta punteada
    COMPLETA como constante de cadena, no el stem suelto — que es justo lo
    que hacía inútil al regex viejo."""

    def test_dotted_module_name_as_a_string_constant_counts(self, tmp_path: Path) -> None:
        _mod(tmp_path, "src/atlas/mcp/operating_server.py", "VALUE = 1\n")
        _mod(
            tmp_path,
            "src/atlas/mcp/manifest.py",
            'ROOTS = [("atlas-operating", "atlas.mcp.operating_server")]\n',
        )

        assert "src/atlas/mcp/operating_server.py" not in dormant_modules(tmp_path)

    def test_dotted_name_only_inside_a_docstring_does_not_count(
        self, tmp_path: Path
    ) -> None:
        # `tools/computer_use/desktop_planner.py` cita atlas.mcp.adapter_registry
        # en su docstring. Documentar un módulo no es llamarlo.
        _mod(tmp_path, "src/atlas/mcp/adapter_registry.py", "VALUE = 1\n")
        _mod(
            tmp_path,
            "src/atlas/tools/planner.py",
            '"""Usa el espejo pydantic de atlas.mcp.adapter_registry."""\nX = 1\n',
        )

        assert "src/atlas/mcp/adapter_registry.py" in dormant_modules(tmp_path)

    def test_bare_stem_in_a_string_still_does_not_count(self, tmp_path: Path) -> None:
        # Guardia de regresión del bug original: la cadena "reproduction" NO
        # es la ruta punteada "atlas.engineering.reproduction".
        _mod(tmp_path, "src/atlas/engineering/reproduction.py", "VALUE = 1\n")
        _mod(tmp_path, "src/atlas/logging/merkle.py", 'KINDS = ["reproduction"]\n')

        assert "src/atlas/engineering/reproduction.py" in dormant_modules(tmp_path)


class TestExclusions:
    def test_a_module_importing_itself_is_still_dormant(self, tmp_path: Path) -> None:
        _mod(
            tmp_path,
            "src/atlas/engineering/lonely.py",
            "from atlas.engineering.lonely import X\n",
        )

        assert "src/atlas/engineering/lonely.py" in dormant_modules(tmp_path)

    def test_entrypoint_stems_are_not_reported(self, tmp_path: Path) -> None:
        _mod(tmp_path, "src/atlas/cli.py", "VALUE = 1\n")
        _mod(tmp_path, "src/atlas/engineering/__init__.py", "")

        reported = dormant_modules(tmp_path)
        assert "src/atlas/cli.py" not in reported
        assert "src/atlas/engineering/__init__.py" not in reported

    def test_classified_modules_are_not_reported(self, tmp_path: Path) -> None:
        _mod(tmp_path, "src/atlas/engineering/parked.py", "VALUE = 1\n")

        reported = dormant_modules(
            tmp_path, classified={"src/atlas/engineering/parked.py": "PARK por ahora"}
        )

        assert reported == []

    def test_tests_do_not_count_as_production_callers(self, tmp_path: Path) -> None:
        # Regla dura tras ADC-WO-108: tests en verde NO son evidencia de cableado.
        _mod(tmp_path, "src/atlas/engineering/hypotheses.py", "VALUE = 1\n")
        _mod(
            tmp_path,
            "tests/test_hypotheses.py",
            "from atlas.engineering.hypotheses import VALUE\n",
        )

        assert "src/atlas/engineering/hypotheses.py" in dormant_modules(tmp_path)


class TestFailHonest:
    def test_a_file_that_does_not_parse_does_not_crash_the_radar(
        self, tmp_path: Path
    ) -> None:
        _mod(tmp_path, "src/atlas/engineering/review.py", "VALUE = 1\n")
        _mod(tmp_path, "src/atlas/core/broken.py", "def (((: this is not python\n")
        _mod(tmp_path, "src/atlas/core/user.py", "from atlas.engineering import review\n")

        reported = dormant_modules(tmp_path)

        assert "src/atlas/engineering/review.py" not in reported
        assert "src/atlas/core/broken.py" in reported

    def test_missing_src_tree_returns_empty_instead_of_raising(self, tmp_path: Path) -> None:
        assert dormant_modules(tmp_path) == []
