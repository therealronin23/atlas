"""Tests para scripts/graphify-monitor-and-switch.sh (Bugs 1 y 3 del plan F1).

Bug 1: choose_fallback() nunca veía las API keys del `.env` porque el script
no las cargaba tras el `cd` inicial (a diferencia de
run-graphify-quality-pipeline.sh), así que siempre caía al default
`openai:openai` -> modelo gpt-4o-mini, que NVIDIA no sirve.

Bug 3a: el array WRAPPER_LOGS tenía /tmp/graphify_gemini_run.log duplicado.

Bug 3b: count_pattern (ahora count_pattern_delta) contaba sobre el fichero
completo acumulado en cada pasada del bucle de monitorización, así que una
vez superado el umbral se quedaba "superado" para siempre aunque no hubiera
fallos nuevos. Debe comparar solo el incremento (delta) desde la última
pasada, persistido en un fichero de estado.

Aislamiento: cada test COPIA el script real a tmp_path/scripts/ (el script
hace `cd "$(dirname "$0")/.."`, así que ejecutar la copia ahí evita que
`source .env` cargue el `.env` REAL del repo con credenciales reales — la
consigna es no tocar nunca el .env real ni imprimir valores de keys reales).
El .env usado en los tests es siempre sintético (NVIDIA_API_KEY=fake-for-test).
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "graphify-monitor-and-switch.sh"


def _copy_script(tmp_path: Path) -> Path:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    dst = scripts_dir / "graphify-monitor-and-switch.sh"
    dst.write_text(SCRIPT_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    dst.chmod(0o755)
    return dst


def _clean_env(**overrides: str) -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", "")}
    env.update(overrides)
    return env


def _run(script: Path, tmp_path: Path, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


class TestBug1EnvNotLoaded:
    def test_print_fallback_only_reads_synthetic_env_file_and_prefers_nvidia(
        self, tmp_path: Path
    ) -> None:
        script = _copy_script(tmp_path)
        (tmp_path / ".env").write_text("NVIDIA_API_KEY=fake-for-test\n", encoding="utf-8")

        result = _run(script, tmp_path, "--print-fallback-only", env=_clean_env())

        assert result.returncode == 0, result.stderr
        fallback = result.stdout.strip()
        assert fallback == "openai:nvidia", (
            f"choose_fallback() devolvio {fallback!r}; se esperaba 'openai:nvidia'. "
            "Si el .env no se carga, choose_fallback() nunca ve NVIDIA_API_KEY y "
            "cae al default 'openai:openai' (modelo gpt-4o-mini, que NVIDIA no sirve)."
        )

    def test_print_fallback_only_without_any_key_falls_back_to_default(
        self, tmp_path: Path
    ) -> None:
        """Sanidad: sin ninguna key disponible (ni siquiera en un .env), el
        default explícito sigue siendo openai:openai — el fix de carga de
        .env no debe inventar keys que no existen."""
        script = _copy_script(tmp_path)
        # Sin fichero .env en absoluto.

        result = _run(script, tmp_path, "--print-fallback-only", env=_clean_env())

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "openai:openai"


class TestBug3aDuplicateWrapperLogs:
    def test_wrapper_logs_has_no_duplicate_entries(self) -> None:
        script_text = SCRIPT_PATH.read_text(encoding="utf-8")
        match = re.search(r"WRAPPER_LOGS=\(([^)]*)\)", script_text)
        assert match, "no se encontro la declaracion de WRAPPER_LOGS en el script"
        entries = match.group(1).split()
        assert len(entries) == len(set(entries)), (
            f"WRAPPER_LOGS tiene entradas duplicadas: {entries}"
        )


class TestBug3bDeltaCounting:
    def test_count_pattern_delta_second_pass_sees_only_new_matches(
        self, tmp_path: Path
    ) -> None:
        script = _copy_script(tmp_path)
        log = tmp_path / "growing.log"
        state_file = tmp_path / "state.json"
        log.write_text("invalid JSON\ninvalid JSON\n", encoding="utf-8")  # 2 occurrences

        env = _clean_env(GRAPHIFY_MONITOR_STATE_FILE=str(state_file))

        first = _run(script, tmp_path, "--count-pattern-delta", "invalid JSON", str(log), env=env)
        assert first.returncode == 0, first.stderr
        assert first.stdout.strip() == "2"

        with log.open("a", encoding="utf-8") as f:
            f.write("invalid JSON\n")  # log grows: 3 occurrences total, 1 new

        second = _run(script, tmp_path, "--count-pattern-delta", "invalid JSON", str(log), env=env)
        assert second.returncode == 0, second.stderr
        assert second.stdout.strip() == "1", (
            "count_pattern_delta debe ver SOLO el incremento (1 linea nueva), no "
            "el total acumulado (3) - bug original: contaba sobre el fichero completo "
            "en cada pasada, asi que una vez superado el umbral se quedaba asi para siempre."
        )

    def test_count_pattern_delta_with_no_new_matches_is_zero(self, tmp_path: Path) -> None:
        script = _copy_script(tmp_path)
        log = tmp_path / "stable.log"
        state_file = tmp_path / "state.json"
        log.write_text("invalid JSON\ninvalid JSON\ninvalid JSON\n", encoding="utf-8")

        env = _clean_env(GRAPHIFY_MONITOR_STATE_FILE=str(state_file))

        first = _run(script, tmp_path, "--count-pattern-delta", "invalid JSON", str(log), env=env)
        assert first.stdout.strip() == "3"

        # log NO crece entre pasadas
        second = _run(script, tmp_path, "--count-pattern-delta", "invalid JSON", str(log), env=env)
        assert second.returncode == 0, second.stderr
        assert second.stdout.strip() == "0"
