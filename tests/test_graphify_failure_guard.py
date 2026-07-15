"""Tests para scripts/graphify_failure_guard.py (Bug 4 del plan F1).

Bug 4: graphify no tenia guard de fallos repetidos -- un fichero que revienta
GRAPHIFY_MAX_OUTPUT_TOKENS en cada corrida se reintenta para siempre. El
guard parsea un log de pipeline buscando los dos patrones confirmados:

  1. "single-file chunk <PATH> truncated at max_completion_tokens" (mensaje
     real de graphify.llm._extract_with_adaptive_retry, ver
     .venv/lib/python3.12/site-packages/graphify/llm.py:1771).
  2. "LLM returned invalid JSON" con el path embebido como
     "source_file":"..." en el JSON parcial de la MISMA linea (repr del raw
     content, ver graphify/llm.py:876-880).

Acumula contador por fichero en un counts-file JSON y, al llegar a 3 fallos,
anade el fichero (idempotente) a .graphifyignore.

Diseno adicional (no pedido literalmente pero necesario dada la Tarea 6 del
mismo plan: run-graphify-quality-pipeline.sh ahora ABRE el log en modo
append, no trunca): si el log contiene una o mas cabeceras
"--- run started ..." el guard solo escanea el contenido DESPUES de la
ULTIMA cabecera -- si escaneara el fichero completo en cada corrida,
re-contaria los fallos de corridas anteriores cada vez que se le llama
(exactamente el mismo problema que el Bug 3 del monitor). Los tests que no
incluyen cabecera verifican el comportamiento "escanea todo" (retrocompatible
con logs sin marcador).
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "graphify_failure_guard.py"


def _mod() -> ModuleType:
    spec = importlib.util.spec_from_file_location("graphify_failure_guard", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _truncated_line(path: str) -> str:
    return f"[graphify] single-file chunk {path} truncated at max_completion_tokens — partial result kept"


def _invalid_json_line(path: str) -> str:
    return (
        "[graphify] LLM returned invalid JSON, skipping chunk "
        f'(first 200 chars: \'{{"nodes": [{{"id": "n1", "source_file": "{path}", "label": "x"}}]}}\')'
    )


class TestThresholdCrossing:
    def test_three_truncated_failures_same_file_added_to_ignore(self, tmp_path: Path) -> None:
        m = _mod()
        log = tmp_path / "pipeline.log"
        target = "docs/design/mcp_catalog_classified.yaml"
        log.write_text("\n".join([_truncated_line(target)] * 3) + "\n", encoding="utf-8")
        ignore_file = tmp_path / ".graphifyignore"
        counts_file = tmp_path / "counts.json"

        rc = m.main([str(log), "--ignore-file", str(ignore_file), "--counts-file", str(counts_file)])

        assert rc == 0
        assert ignore_file.exists()
        ignored = ignore_file.read_text(encoding="utf-8")
        assert target in ignored
        assert "# auto: failure_guard" in ignored

    def test_two_failures_not_added(self, tmp_path: Path) -> None:
        m = _mod()
        log = tmp_path / "pipeline.log"
        target = "docs/design/mcp_catalog_classified.yaml"
        log.write_text("\n".join([_truncated_line(target)] * 2) + "\n", encoding="utf-8")
        ignore_file = tmp_path / ".graphifyignore"
        counts_file = tmp_path / "counts.json"

        rc = m.main([str(log), "--ignore-file", str(ignore_file), "--counts-file", str(counts_file)])

        assert rc == 0
        if ignore_file.exists():
            assert target not in ignore_file.read_text(encoding="utf-8")

    def test_repeated_runs_do_not_duplicate_ignore_entry(self, tmp_path: Path) -> None:
        m = _mod()
        target = "docs/design/mcp_catalog_classified.yaml"
        ignore_file = tmp_path / ".graphifyignore"
        counts_file = tmp_path / "counts.json"

        # Corrida 1: 2 fallos (todavia no cruza el umbral).
        log1 = tmp_path / "run1.log"
        log1.write_text("\n".join([_truncated_line(target)] * 2) + "\n", encoding="utf-8")
        m.main([str(log1), "--ignore-file", str(ignore_file), "--counts-file", str(counts_file)])
        assert not ignore_file.exists() or target not in ignore_file.read_text(encoding="utf-8")

        # Corrida 2: 2 fallos mas -> total acumulado 4, cruza el umbral.
        log2 = tmp_path / "run2.log"
        log2.write_text("\n".join([_truncated_line(target)] * 2) + "\n", encoding="utf-8")
        m.main([str(log2), "--ignore-file", str(ignore_file), "--counts-file", str(counts_file)])
        assert target in ignore_file.read_text(encoding="utf-8")

        # Corrida 3: sigue cruzado -> NO debe duplicar la entrada.
        log3 = tmp_path / "run3.log"
        log3.write_text(_truncated_line(target) + "\n", encoding="utf-8")
        m.main([str(log3), "--ignore-file", str(ignore_file), "--counts-file", str(counts_file)])

        ignored_text = ignore_file.read_text(encoding="utf-8")
        assert ignored_text.count(target) == 1, (
            f"la entrada de {target} aparece {ignored_text.count(target)} veces en "
            f".graphifyignore tras corridas repetidas -- debe ser idempotente:\n{ignored_text}"
        )


class TestInvalidJsonPattern:
    def test_invalid_json_source_file_is_extracted_from_same_line(self, tmp_path: Path) -> None:
        m = _mod()
        log = tmp_path / "pipeline.log"
        target = "docs/design/mcp_catalog_classified.yaml"
        log.write_text("\n".join([_invalid_json_line(target)] * 3) + "\n", encoding="utf-8")
        ignore_file = tmp_path / ".graphifyignore"
        counts_file = tmp_path / "counts.json"

        rc = m.main([str(log), "--ignore-file", str(ignore_file), "--counts-file", str(counts_file)])

        assert rc == 0
        assert target in ignore_file.read_text(encoding="utf-8")

    def test_invalid_json_line_without_source_file_is_not_attributed(self, tmp_path: Path) -> None:
        """Sin source_file en la linea no hay a que fichero atribuir el fallo
        -- no debe inventarse ni crashear."""
        m = _mod()
        log = tmp_path / "pipeline.log"
        log.write_text(
            "\n".join(
                [
                    "[graphify] LLM returned invalid JSON, skipping chunk (first 200 chars: 'not json at all')"
                ]
                * 5
            )
            + "\n",
            encoding="utf-8",
        )
        ignore_file = tmp_path / ".graphifyignore"
        counts_file = tmp_path / "counts.json"

        rc = m.main([str(log), "--ignore-file", str(ignore_file), "--counts-file", str(counts_file)])

        assert rc == 0
        assert not ignore_file.exists() or ignore_file.read_text(encoding="utf-8").strip() == ""


class TestCountsFilePersistence:
    def test_counts_file_accumulates_across_invocations(self, tmp_path: Path) -> None:
        m = _mod()
        target = "some/other_file.py"
        counts_file = tmp_path / "counts.json"
        ignore_file = tmp_path / ".graphifyignore"

        log1 = tmp_path / "run1.log"
        log1.write_text(_truncated_line(target) + "\n", encoding="utf-8")
        m.main([str(log1), "--ignore-file", str(ignore_file), "--counts-file", str(counts_file)])

        data = json.loads(counts_file.read_text(encoding="utf-8"))
        assert data[target] == 1

        log2 = tmp_path / "run2.log"
        log2.write_text(_truncated_line(target) + "\n", encoding="utf-8")
        m.main([str(log2), "--ignore-file", str(ignore_file), "--counts-file", str(counts_file)])

        data = json.loads(counts_file.read_text(encoding="utf-8"))
        assert data[target] == 2


class TestRunStartedMarkerScoping:
    def test_only_scans_after_last_run_started_marker(self, tmp_path: Path) -> None:
        """El LOG_PATH de pipeline.sh es append-only (Tarea 6): si el guard
        re-escaneara el fichero completo en cada corrida, los 3 fallos de la
        corrida anterior (ya contados) se sumarian de nuevo. Con la cabecera
        "--- run started ..." como marcador, cada corrida debe contar solo
        SUS PROPIOS fallos nuevos."""
        m = _mod()
        target = "docs/design/mcp_catalog_classified.yaml"
        ignore_file = tmp_path / ".graphifyignore"
        counts_file = tmp_path / "counts.json"

        log = tmp_path / "pipeline.log"
        log.write_text(
            "--- run started 2026-07-15T10:00:00Z backend=openai model=x ---\n"
            + _truncated_line(target)
            + "\n"
            + _truncated_line(target)
            + "\n",
            encoding="utf-8",
        )
        m.main([str(log), "--ignore-file", str(ignore_file), "--counts-file", str(counts_file)])
        assert json.loads(counts_file.read_text(encoding="utf-8"))[target] == 2

        # Nueva corrida: el log CRECE (append) con una nueva cabecera + 1 fallo
        # nuevo. Sin scoping por marcador, este escaneo volveria a contar los
        # 2 fallos viejos + el nuevo = 3 de golpe en una sola corrida donde en
        # realidad solo hubo 1 fallo nuevo.
        with log.open("a", encoding="utf-8") as f:
            f.write("--- run started 2026-07-15T11:00:00Z backend=openai model=x ---\n")
            f.write(_truncated_line(target) + "\n")

        m.main([str(log), "--ignore-file", str(ignore_file), "--counts-file", str(counts_file)])
        assert json.loads(counts_file.read_text(encoding="utf-8"))[target] == 3


class TestCliContract:
    def test_cli_end_to_end_via_subprocess(self, tmp_path: Path) -> None:
        target = "docs/design/mcp_catalog_classified.yaml"
        log = tmp_path / "pipeline.log"
        log.write_text("\n".join([_truncated_line(target)] * 3) + "\n", encoding="utf-8")
        ignore_file = tmp_path / ".graphifyignore"
        counts_file = tmp_path / "counts.json"

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                str(log),
                "--ignore-file",
                str(ignore_file),
                "--counts-file",
                str(counts_file),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0, result.stderr
        assert target in ignore_file.read_text(encoding="utf-8")

    def test_missing_log_file_does_not_crash(self, tmp_path: Path) -> None:
        m = _mod()
        rc = m.main(
            [
                str(tmp_path / "does-not-exist.log"),
                "--ignore-file",
                str(tmp_path / ".graphifyignore"),
                "--counts-file",
                str(tmp_path / "counts.json"),
            ]
        )
        assert rc == 0
