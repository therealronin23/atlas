"""Detector de deriva component_reality_matrix.jsonl↔grafo real (2026-07-30).

El 2026-07-29 se encontraron 8 filas donde el doc afirmaba "no WIRED" y el
grafo (AST real, no grep) mostraba importadores reales — nadie las había
contrastado desde que se escribieron. Mismo principio que
``ecosystem_drift.py``: determinista, barato, nunca LLM/red, TDD real en vez
de un script suelto (``sanitation_audit.py`` sólo importa y envuelve).

Dos direcciones de deriva, simétricas:
- SOBRECLAMADO: `statuses` incluye WIRED pero NINGÚN fichero de `code` tiene
  importadores reales.
- SUBCLAMADO: `statuses` NO incluye WIRED pero TODOS los ficheros de `code`
  sí tienen importadores reales (el bug real de ayer).

Deliberadamente SIN veredicto para filas mixtas (algunos ficheros con
importadores, otros sin ellos): un componente puede nombrar específicamente
el papel del fichero SIN importadores (p.ej. "Event Kernel projection" sobre
core_bridge.py + store.py — sólo core_bridge.py es la "proyección" que el
nombre describe, aunque store.py esté muy usado). Forzar un veredicto ahí
sería exactamente el tipo de afirmación no verificada que este detector
existe para atrapar."""

from __future__ import annotations

import json
from pathlib import Path

from atlas.core.self_maintenance.component_wiring_drift import component_wiring_drift


def _write_matrix(repo: Path, rows: list[dict]) -> None:
    path = repo / "docs" / "canon" / "component_reality_matrix.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _row(
    id_: str, name: str, code: list[str], statuses: list[str],
) -> dict:
    return {"id": id_, "name": name, "code": code, "statuses": statuses}


class TestOverclaimedWired:
    def test_wired_claimed_but_zero_real_importers_is_flagged(self, tmp_path: Path) -> None:
        _write_matrix(tmp_path, [
            _row("C1", "Ghost", ["src/atlas/x/ghost.py"], ["CODE_PRESENT", "TESTED", "WIRED"]),
        ])

        findings = component_wiring_drift(
            tmp_path, importers_of=lambda mod: [],
        )

        assert len(findings) == 1
        assert "C1" in findings[0] and "Ghost" in findings[0]
        assert "WIRED" in findings[0]


class TestUnderclaimedWired:
    def test_all_files_have_importers_but_wired_missing_is_flagged(self, tmp_path: Path) -> None:
        _write_matrix(tmp_path, [
            _row("C2", "Kernel", ["src/atlas/fabric/policy.py"], ["CODE_PRESENT", "TESTED"]),
        ])

        findings = component_wiring_drift(
            tmp_path, importers_of=lambda mod: ["atlas.core.orchestrator"],
        )

        assert len(findings) == 1
        assert "C2" in findings[0] and "Kernel" in findings[0]


class TestConsistentRowsAreSilent:
    def test_wired_claimed_and_confirmed_no_finding(self, tmp_path: Path) -> None:
        _write_matrix(tmp_path, [
            _row("C3", "OK-wired", ["src/atlas/a.py"], ["CODE_PRESENT", "WIRED"]),
        ])

        findings = component_wiring_drift(
            tmp_path, importers_of=lambda mod: ["atlas.orchestrator"],
        )

        assert findings == []

    def test_not_wired_claimed_and_confirmed_no_finding(self, tmp_path: Path) -> None:
        _write_matrix(tmp_path, [
            _row("C4", "OK-parked", ["src/atlas/parked.py"], ["CODE_PRESENT", "TESTED"]),
        ])

        findings = component_wiring_drift(
            tmp_path, importers_of=lambda mod: [],
        )

        assert findings == []


class TestMixedRowsAreNeverJudged:
    """Fila con VARIOS ficheros donde unos tienen importadores y otros no:
    el detector no falla un veredicto en ninguna dirección — es exactamente
    el caso "Event Kernel projection" del 2026-07-29, dejado sin corregir a
    propósito porque el nombre del componente puede referirse específicamente
    al fichero SIN importadores."""

    def test_partial_wiring_not_flagged_when_wired_claimed(self, tmp_path: Path) -> None:
        _write_matrix(tmp_path, [
            _row(
                "C5", "Event Kernel projection",
                ["src/atlas/events/core_bridge.py", "src/atlas/events/store.py"],
                ["CODE_PRESENT", "WIRED"],
            ),
        ])

        findings = component_wiring_drift(
            tmp_path,
            importers_of=lambda mod: (
                [] if mod.endswith("core_bridge") else ["atlas.api.server"]
            ),
        )

        assert findings == []

    def test_partial_wiring_not_flagged_when_wired_not_claimed(self, tmp_path: Path) -> None:
        _write_matrix(tmp_path, [
            _row(
                "C6", "OsEventStore and event bridge",
                ["src/atlas/events/store.py", "src/atlas/events/core_bridge.py"],
                ["CODE_PRESENT", "TESTED"],
            ),
        ])

        findings = component_wiring_drift(
            tmp_path,
            importers_of=lambda mod: (
                [] if mod.endswith("core_bridge") else ["atlas.api.server"]
            ),
        )

        assert findings == []


class TestRobustInputHandling:
    def test_non_python_code_entries_are_ignored(self, tmp_path: Path) -> None:
        _write_matrix(tmp_path, [
            _row("C7", "Config-only", [".cursor/mcp.json"], ["CODE_PRESENT"]),
        ])

        findings = component_wiring_drift(tmp_path, importers_of=lambda mod: [])

        assert findings == []

    def test_empty_code_list_is_ignored(self, tmp_path: Path) -> None:
        _write_matrix(tmp_path, [_row("C8", "No files", [], ["ACCEPTED_DESIGN"])])

        findings = component_wiring_drift(tmp_path, importers_of=lambda mod: [])

        assert findings == []

    def test_importers_of_exception_treats_row_as_unknown(self, tmp_path: Path) -> None:
        """Si el grafo falla (STALE, DB ausente...) para TODOS los ficheros
        de una fila, mejor callar que arriesgar un falso positivo — mismo
        fail-open que el resto del radar (`nunca rompe el radar`)."""
        _write_matrix(tmp_path, [
            _row("C9", "Unknowable", ["src/atlas/x.py"], ["CODE_PRESENT", "TESTED"]),
        ])

        def _boom(mod: str) -> list[str]:
            raise RuntimeError("project graph freshness is STALE")

        findings = component_wiring_drift(tmp_path, importers_of=_boom)

        assert findings == []

    def test_missing_matrix_file_returns_empty(self, tmp_path: Path) -> None:
        assert component_wiring_drift(tmp_path, importers_of=lambda mod: []) == []

    def test_malformed_json_line_is_skipped_not_crashed(self, tmp_path: Path) -> None:
        path = tmp_path / "docs" / "canon" / "component_reality_matrix.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "{not valid json\n"
            + json.dumps(_row("C10", "Real", ["src/atlas/y.py"], ["CODE_PRESENT", "TESTED"]))
            + "\n",
            encoding="utf-8",
        )

        findings = component_wiring_drift(tmp_path, importers_of=lambda mod: ["atlas.z"])

        assert len(findings) == 1
        assert "C10" in findings[0]


class TestDefaultImportersUsesTheRealGraph:
    """Sin `importers_of` inyectado, debe consultar el grafo real (mismo
    mecanismo que `build_graph_server` + `graph_freshness` para no exigir
    HEAD exacto — el daemon poll cada 3600s, casi nunca está FRESH)."""

    def test_real_graph_end_to_end(self, tmp_path: Path) -> None:
        import subprocess

        import pytest
        pytest.importorskip("kuzu")
        pytest.importorskip("mcp")

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
        atlas_dir = repo / "src" / "atlas"
        atlas_dir.mkdir(parents=True)
        (atlas_dir / "__init__.py").write_text("", encoding="utf-8")
        (atlas_dir / "a.py").write_text("X = 1\n", encoding="utf-8")
        (atlas_dir / "b.py").write_text("from atlas import a\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "c1"], cwd=repo, check=True)

        from atlas.memory.project_graph import build_project_graph

        db_path = tmp_path / "graph.kuzu"
        build_project_graph(repo, db_path, commits=1)

        _write_matrix(repo, [
            # "a" está importado de verdad por "b" -> subclamado real.
            _row("REAL1", "Real underclaim", ["src/atlas/a.py"], ["CODE_PRESENT", "TESTED"]),
            # "b" no lo importa nadie -> consistente, sin hallazgo.
            _row("REAL2", "Real ok-parked", ["src/atlas/b.py"], ["CODE_PRESENT"]),
        ])

        findings = component_wiring_drift(repo, db_path=db_path)

        assert any("REAL1" in f for f in findings)
        assert not any("REAL2" in f for f in findings)

    def test_default_path_opens_the_kuzu_database_once_not_per_module(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Deuda de rendimiento real (2026-07-30, ver WORK_LEDGER.md): la
        suite pasó de ~370s a 467-564s porque `_default_importers_of` abría
        una BD Kuzu nueva por CADA módulo consultado -- `build_graph_server`
        reabre la BD en cada llamada a `_query` a propósito para su propio
        caso de uso de servidor MCP de larga vida (otro proceso regenera el
        grafo mientras el server sigue vivo). Ese motivo no aplica aquí: un
        pase de `component_wiring_drift` es una lectura acotada de un solo
        proceso, así que reabrir por módulo es puro coste sin beneficio.

        El arreglo es BATCHEAR (una conexión, muchas queries), no mockear:
        mockear escondería el cableado real contra el grafo que este mismo
        test (`test_real_graph_end_to_end`) existe para probar."""
        import subprocess

        import pytest
        pytest.importorskip("kuzu")

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
        atlas_dir = repo / "src" / "atlas"
        atlas_dir.mkdir(parents=True)
        (atlas_dir / "__init__.py").write_text("", encoding="utf-8")
        (atlas_dir / "a.py").write_text("X = 1\n", encoding="utf-8")
        (atlas_dir / "b.py").write_text("Y = 2\n", encoding="utf-8")
        (atlas_dir / "c.py").write_text("Z = 3\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "c1"], cwd=repo, check=True)

        from atlas.memory.project_graph import build_project_graph

        db_path = tmp_path / "graph.kuzu"
        build_project_graph(repo, db_path, commits=1)

        # Tres módulos distintos en la misma fila -> tres llamadas a
        # importers_of() si no se batchea.
        _write_matrix(repo, [
            _row("REAL3", "Tres módulos", ["src/atlas/a.py", "src/atlas/b.py", "src/atlas/c.py"], []),
        ])

        import atlas.core.self_maintenance.component_wiring_drift as cwd_module

        calls = {"n": 0}
        real_open = cwd_module.open_kuzu_database

        def _counting_open(*args, **kwargs):
            calls["n"] += 1
            return real_open(*args, **kwargs)

        monkeypatch.setattr(cwd_module, "open_kuzu_database", _counting_open)

        component_wiring_drift(repo, db_path=db_path)

        assert calls["n"] == 1, (
            f"la BD se abrió {calls['n']} veces para 3 módulos de la misma fila -- "
            "debe abrirse una sola vez y reutilizar la conexión"
        )
