"""
Pre-chequeo barato antes de la validación cara (2026-08-05).

Origen: extracción de la técnica del LSP de Hermes, NO del paquete. Sus 4.704
loc de `agent/lsp/` usan un solo grupo de métodos del protocolo —
`textDocument/diagnostic`, `publishDiagnostics`, `didOpen/didChange/didSave` —
o sea, es una tubería de diagnósticos, no navegación de símbolos. Y su valor
real es uno: **enterarse del error sin ejecutar todo**.

Atlas hoy no tiene nada equivalente: `ToolCoder` y el lazo de evolución van
directos al `test_cmd`. Coste medido en esta máquina:

    ast.parse de un fichero      ~0 ms
    mypy de un fichero          249 ms
    pytest de un fichero      3.195 ms
    suite completa           562.000 ms

Un candidato generado que ni siquiera parsea se lleva por delante hasta 562
segundos de suite para acabar en 0.0. Ese es el desperdicio que esto corta.

Por qué NO se replica el LSP entero: la otra ganancia teórica —diagnósticos de
lenguajes no-Python— hoy no tiene a qué apuntar. Atlas tiene 1 fichero
no-Python en `prototypes/`, `ui/atlas-shell` se fue al graveyard con ADR-085 y
los forks viven fuera del repo. Construirlo ahora sería un cascarón esperando
una base de código que aún no existe.

Regla de severidad, deliberada: un fichero que no PARSEA nunca puede estar
bien, así que es rechazo duro. Los errores de TIPO se reportan pero no
rechazan — mypy da falsos positivos con stubs ausentes, y un pre-chequeo que
descarta candidatos buenos enseñaría al lazo que todo falla.
"""

from __future__ import annotations

from pathlib import Path

from atlas.engineering.fast_precheck import PrecheckResult, precheck_files


class TestSyntaxIsAHardReject:
    def test_a_file_that_does_not_parse_is_rejected(self, tmp_path: Path) -> None:
        broken = tmp_path / "roto.py"
        broken.write_text("def f(:\n    pass\n")

        result = precheck_files([broken], repo_root=tmp_path)

        assert result.ok is False
        assert result.stage == "syntax"
        assert "roto.py" in result.detail

    def test_a_valid_file_passes_the_syntax_stage(self, tmp_path: Path) -> None:
        good = tmp_path / "bien.py"
        good.write_text("def f() -> int:\n    return 1\n")

        result = precheck_files([good], repo_root=tmp_path, run_types=False)

        assert result.ok is True
        assert result.stage == "ok"

    def test_the_syntax_stage_does_not_need_mypy_at_all(self, tmp_path: Path) -> None:
        """El corte barato tiene que funcionar aunque no haya mypy: es lo que
        lo hace utilizable dentro de un worktree efímero recién creado."""
        broken = tmp_path / "roto.py"
        broken.write_text("class A(\n")

        result = precheck_files([broken], repo_root=tmp_path, run_types=True)

        assert result.stage == "syntax"  # ni llega a tipos


class TestTypesAreReportedNotRejected:
    def test_a_type_error_is_reported_but_does_not_reject(self, tmp_path: Path) -> None:
        typed = tmp_path / "tipos.py"
        typed.write_text("def f() -> int:\n    return 'no soy un int'\n")

        result = precheck_files([typed], repo_root=tmp_path)

        # No rechaza: mypy sin el entorno del proyecto da falsos positivos, y
        # descartar candidatos buenos es peor que dejar pasar uno malo (los
        # tests siguen detrás).
        assert result.ok is True
        assert result.type_errors, "el error de tipo debería quedar reportado"


class TestItIgnoresWhatItCannotJudge:
    def test_non_python_files_are_skipped_not_failed(self, tmp_path: Path) -> None:
        other = tmp_path / "algo.ts"
        other.write_text("const x: number = 'nope';\n")

        result = precheck_files([other], repo_root=tmp_path)

        assert result.ok is True
        assert result.stage == "ok"

    def test_a_missing_file_does_not_crash_the_loop(self, tmp_path: Path) -> None:
        result = precheck_files([tmp_path / "no_existe.py"], repo_root=tmp_path)

        assert isinstance(result, PrecheckResult)
        assert result.ok is True  # no medible != roto

    def test_no_files_is_a_pass(self, tmp_path: Path) -> None:
        assert precheck_files([], repo_root=tmp_path).ok is True


class TestWiredIntoTheEvolutionLoop:
    """Un pre-chequeo que nadie llama no ahorra nada. Se cablea donde el
    desperdicio es mayor: el lazo de evolución, que corre `test_cmd` por cada
    candidato generado."""

    def test_a_candidate_that_does_not_parse_never_reaches_the_test_command(
        self, tmp_path: Path
    ) -> None:
        import subprocess
        from unittest.mock import MagicMock

        from atlas.core.self_maintenance.self_build_runner import SelfBuildRunner

        repo = tmp_path / "repo"
        repo.mkdir()
        for args in (["init", "-q"], ["config", "user.email", "t@t.local"],
                     ["config", "user.name", "t"]):
            subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)
        (repo / "target.py").write_text("x = 1\n")
        subprocess.run(["git", "-C", str(repo), "add", "target.py"], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"],
                       capture_output=True, check=True)

        runner = SelfBuildRunner(
            repo_root=repo, hub=MagicMock(), cold_update_manager=MagicMock(),
        )
        # Un test_cmd que tardaría lo indecible: si el pre-chequeo funciona,
        # nunca llega a ejecutarse.
        import sys
        import time
        started = time.perf_counter()
        result = runner._evaluate_candidate_in_worktree(
            target_rel="target.py",
            candidate_code="def roto(:\n",  # no parsea
            test_cmd=[sys.executable, "-c", "import time; time.sleep(20)"],
            base_ref="HEAD",
        )
        elapsed = time.perf_counter() - started

        assert result == {"score": 0.0}
        assert elapsed < 10, (
            f"tardó {elapsed:.1f}s: el candidato roto llegó a ejecutar el test_cmd"
        )
