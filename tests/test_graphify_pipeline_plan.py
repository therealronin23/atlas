"""Tests para scripts/run-graphify-quality-pipeline.sh (Bug 2 del plan F1).

Bug 2: cuando falta OPENAI_API_KEY pero hay NVIDIA_API_KEY, el script
redirigia OPENAI_BASE_URL al endpoint OpenAI-compatible de NVIDIA pero
conservaba MODEL="gpt-4o-mini" si venia preseteado (via --model o
GRAPHIFY_MODEL) -- NVIDIA no sirve ese modelo, asi que el backend siempre
fallaba. Ademas la cascada de autodeteccion de backend estaba DUPLICADA
respecto a scripts/update-knowledge-graph-rag.sh (dos fuentes de verdad que
podian discrepar).

Fix: pipeline.sh elimina su propia cascada de autodeteccion y delega la
eleccion de backend a update-knowledge-graph-rag.sh (unica fuente de verdad);
solo pasa --backend/--model rio abajo si el usuario los dio EXPLICITOS por
CLI. El unico remapeo que queda vivo en pipeline.sh es el residual: si el
usuario fuerza --backend openai sin OPENAI_API_KEY pero con NVIDIA_API_KEY,
se redirige el endpoint Y se fuerza el modelo lejos de cualquier nombre
gpt-* hacia uno que NVIDIA sirva.

--print-plan imprime backend/modelo/endpoint resueltos y sale sin ejecutar
nada (sin llamar a update-knowledge-graph-rag.sh, sin tocar graphify-out/).

Aislamiento: se copia el script a tmp_path/scripts/ (usa
"$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" para su propio ROOT_DIR,
asi que ejecutar la copia ahi evita tocar el .env REAL del repo -- las keys
usadas en los tests son siempre sinteticas). Se stubea .venv/bin/activate
porque el script exige que exista antes de llegar al parseo de flags.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "run-graphify-quality-pipeline.sh"


def _copy_script(tmp_path: Path) -> Path:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    dst = scripts_dir / "run-graphify-quality-pipeline.sh"
    dst.write_text(SCRIPT_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    dst.chmod(0o755)
    # El script exige source .venv/bin/activate antes de nada; un activate
    # no-op basta (no se llega a ejecutar ningun venv real en modo --print-plan).
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True, exist_ok=True)
    (venv_bin / "activate").write_text("# stub activate for tests\n", encoding="utf-8")
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


class TestBug2NvidiaModelRemap:
    def test_print_plan_forces_nvidia_model_when_backend_openai_forced_explicitly(
        self, tmp_path: Path
    ) -> None:
        """El caso real reportado: alguien invoca pipeline.sh con --backend
        openai --model gpt-4o-mini (p.ej. un comando copiado de otra sesion)
        y solo tiene NVIDIA_API_KEY disponible (sin OPENAI_API_KEY real). El
        endpoint se redirige a NVIDIA pero el modelo DEBE dejar de ser
        gpt-4o-mini -- si no, NVIDIA rechaza cada request (fallo perpetuo)."""
        script = _copy_script(tmp_path)
        env = _clean_env(NVIDIA_API_KEY="fake-for-test")

        result = _run(
            script, tmp_path, "--backend", "openai", "--model", "gpt-4o-mini", "--print-plan", env=env
        )

        assert result.returncode == 0, result.stderr
        plan = result.stdout
        assert "gpt-4o-mini" not in plan, f"el plan todavia menciona gpt-4o-mini:\n{plan}"
        assert "model=meta/llama-3.3-70b-instruct" in plan, plan
        assert "endpoint=https://integrate.api.nvidia.com/v1" in plan, plan

    def test_print_plan_without_explicit_backend_never_shows_gpt4o_mini(
        self, tmp_path: Path
    ) -> None:
        """Sin --backend/--model explicitos y solo NVIDIA_API_KEY disponible,
        pipeline.sh delega la resolucion a update-knowledge-graph-rag.sh (no
        inventa un gpt-4o-mini por su cuenta)."""
        script = _copy_script(tmp_path)
        env = _clean_env(NVIDIA_API_KEY="fake-for-test")

        result = _run(script, tmp_path, "--print-plan", env=env)

        assert result.returncode == 0, result.stderr
        assert "gpt-4o-mini" not in result.stdout, result.stdout

    def test_print_plan_respects_explicit_non_gpt_model(self, tmp_path: Path) -> None:
        """Si el usuario da explicitamente un modelo que NO es gpt-*, el
        residual remap no debe tocarlo (solo interviene sobre nombres
        gpt-* que NVIDIA no puede servir)."""
        script = _copy_script(tmp_path)
        env = _clean_env(NVIDIA_API_KEY="fake-for-test")

        result = _run(
            script,
            tmp_path,
            "--backend",
            "openai",
            "--model",
            "custom/other-model",
            "--print-plan",
            env=env,
        )

        assert result.returncode == 0, result.stderr
        assert "model=custom/other-model" in result.stdout, result.stdout

    def test_print_plan_does_not_touch_graphify_out(self, tmp_path: Path) -> None:
        """--print-plan sale antes de mkdir graphify-out / de invocar a
        update-knowledge-graph-rag.sh -- no debe dejar rastro en disco."""
        script = _copy_script(tmp_path)
        env = _clean_env(NVIDIA_API_KEY="fake-for-test")

        result = _run(script, tmp_path, "--print-plan", env=env)

        assert result.returncode == 0, result.stderr
        assert not (tmp_path / "graphify-out").exists()


def _stub_rag_script(tmp_path: Path) -> None:
    """Sustituye update-knowledge-graph-rag.sh por un stub que no llama a
    ningun LLM -- solo para probar el manejo del log de pipeline.sh en
    aislamiento (nunca se lanza una corrida real de graphify aqui)."""
    rag = tmp_path / "scripts" / "update-knowledge-graph-rag.sh"
    rag.write_text("#!/usr/bin/env bash\necho 'stub rag ran'\n", encoding="utf-8")
    rag.chmod(0o755)


def _copy_failure_guard(tmp_path: Path) -> None:
    dst = tmp_path / "scripts" / "graphify_failure_guard.py"
    dst.write_text(
        (REPO_ROOT / "scripts" / "graphify_failure_guard.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


class TestBug6LogAppendMode:
    """Tarea 6: LOG_PATH pasa de modo truncado (>) a modo append (>>), con una
    cabecera "--- run started ..." antes de cada corrida -- necesario para que
    graphify_failure_guard.py (Bug 4) pueda ver fallos repetidos ENTRE
    corridas en vez de perderlos cada vez que el log se pisa."""

    def test_log_path_append_mode_preserves_previous_run_content(self, tmp_path: Path) -> None:
        script = _copy_script(tmp_path)
        _stub_rag_script(tmp_path)
        _copy_failure_guard(tmp_path)
        (tmp_path / "graphify-out" / "logs").mkdir(parents=True)
        log_path = tmp_path / "graphify-out" / "logs" / "pipeline.log"
        log_path.write_text("SENTINEL_FROM_PREVIOUS_RUN\n", encoding="utf-8")

        env = _clean_env(NVIDIA_API_KEY="fake-for-test")
        result = _run(
            script, tmp_path, "--backend", "openai", "--model", "meta/llama-3.3-70b-instruct", env=env
        )

        assert result.returncode == 0, result.stderr
        log_text = log_path.read_text(encoding="utf-8")
        assert "SENTINEL_FROM_PREVIOUS_RUN" in log_text, (
            f"el log se trunco en vez de preservarse (modo append):\n{log_text}"
        )
        assert "--- run started" in log_text
        assert "stub rag ran" in log_text
