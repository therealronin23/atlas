"""
ParallelCoder — modo enjambre real: los workers exitosos deben sincronizar sus
cambios de vuelta al repo real (bug encontrado: antes, TODO se descartaba al
borrar el worktree, incluso los éxitos). También verifica pass-through de los
kwargs nuevos (edit_format, sandbox, etc.) a AtlasCoder.code().
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlas.core.atlas_coder import CoderResult
from atlas.core.parallel_coder import ParallelCoder, WorkerResult


def _git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("A_OLD = 1\n")
    (repo / "src" / "b.py").write_text("B_OLD = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    return repo


@pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git no disponible",
)
def test_successful_worker_syncs_files_back_to_real_repo(tmp_path: Path) -> None:
    """Bug encontrado: antes, incluso un worker EXITOSO perdía sus cambios al
    borrar el worktree. Ahora deben sincronizarse de vuelta."""
    repo = _git_repo(tmp_path)

    def fake_code(self, task, context_files, test_cmd, max_iterations=3, **kwargs):
        # Simula la edición real: modifica el archivo en el worktree (self._repo_root)
        target = self._repo_root / context_files[0]
        target.write_text(target.read_text().replace("A_OLD", "A_NEW"))
        return CoderResult(success=True, iterations=1, files_changed=[context_files[0]], test_output="")

    from atlas.core.inference_hub import Provider, InferenceLevel
    fake_provider = Provider(
        name="fake", level=InferenceLevel.L1, base_url="http://x",
        model_id="m", litellm_model="m", api_key_env="FAKE_KEY",
    )

    with patch.dict("os.environ", {"FAKE_KEY": "x"}), \
         patch("atlas.core.atlas_coder.AtlasCoder.code", fake_code):
        coder = ParallelCoder(repo_root=repo, providers=[fake_provider])
        result = coder.run(
            subtasks=["cambia A_OLD a A_NEW"],
            context_files=["src/a.py"],
            test_cmd=["true"],
        )

    assert result.subtasks_passed == 1
    # El repo REAL (no el worktree, ya borrado) debe tener el cambio
    assert "A_NEW" in (repo / "src" / "a.py").read_text()


@pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git no disponible",
)
def test_failed_worker_does_not_touch_real_repo(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    original = (repo / "src" / "a.py").read_text()

    def fake_code(self, task, context_files, test_cmd, max_iterations=3, **kwargs):
        return CoderResult(success=False, iterations=1, files_changed=[], test_output="", error="nope")

    from atlas.core.inference_hub import Provider, InferenceLevel
    fake_provider = Provider(
        name="fake", level=InferenceLevel.L1, base_url="http://x",
        model_id="m", litellm_model="m", api_key_env="FAKE_KEY",
    )

    with patch.dict("os.environ", {"FAKE_KEY": "x"}), \
         patch("atlas.core.atlas_coder.AtlasCoder.code", fake_code):
        coder = ParallelCoder(repo_root=repo, providers=[fake_provider])
        result = coder.run(
            subtasks=["tarea que falla"],
            context_files=["src/a.py"],
            test_cmd=["true"],
        )

    assert result.subtasks_passed == 0
    assert (repo / "src" / "a.py").read_text() == original


def test_kwargs_forwarded_to_atlas_coder_code(tmp_path: Path) -> None:
    """edit_format, use_apply_model, etc. deben llegar a AtlasCoder.code()."""
    repo = _git_repo(tmp_path)
    captured_kwargs: list[dict] = []

    def fake_code(self, task, context_files, test_cmd, max_iterations=3, **kwargs):
        captured_kwargs.append(kwargs)
        return CoderResult(success=True, iterations=1, files_changed=[], test_output="")

    from atlas.core.inference_hub import Provider, InferenceLevel
    fake_provider = Provider(
        name="fake", level=InferenceLevel.L1, base_url="http://x",
        model_id="m", litellm_model="m", api_key_env="FAKE_KEY",
    )

    with patch.dict("os.environ", {"FAKE_KEY": "x"}), \
         patch("atlas.core.atlas_coder.AtlasCoder.code", fake_code):
        coder = ParallelCoder(repo_root=repo, providers=[fake_provider])
        coder.run(
            subtasks=["t1"],
            context_files=["src/a.py"],
            test_cmd=["true"],
            edit_format="apply_patch",
            use_apply_model=True,
        )

    assert captured_kwargs
    assert captured_kwargs[0]["edit_format"] == "apply_patch"
    assert captured_kwargs[0]["use_apply_model"] is True


def test_level_forwarded_to_coder_that_accepts_it(tmp_path: Path) -> None:
    """Gap latente (2026-07-02): ParallelCoder.run(level=...) solo alimentaba
    discover_workers, nunca llegaba a coder.code(). ToolCoder SÍ tiene un
    parámetro `level` explícito — debe reenviarse cuando el motor lo acepta."""
    repo = _git_repo(tmp_path)
    captured_kwargs: list[dict] = []

    class _FakeCoderWithLevel:
        def __init__(self, hub, repo_root, timeout_s):
            pass

        def code(self, task, context_files, test_cmd, max_iterations=3, level=None, **kwargs):
            captured_kwargs.append({"level": level, **kwargs})
            return CoderResult(success=True, iterations=1, files_changed=[], test_output="")

    from atlas.core.inference_hub import Provider, InferenceLevel
    fake_provider = Provider(
        name="fake", level=InferenceLevel.L2, base_url="http://x",
        model_id="m", litellm_model="m", api_key_env="FAKE_KEY",
    )

    with patch.dict("os.environ", {"FAKE_KEY": "x"}):
        coder = ParallelCoder(
            repo_root=repo, providers=[fake_provider],
            coder_factory=lambda hub, root, timeout: _FakeCoderWithLevel(hub, root, timeout),
        )
        coder.run(
            subtasks=["t1"], context_files=["src/a.py"], test_cmd=["true"],
            level=InferenceLevel.L2,
        )

    assert captured_kwargs
    assert captured_kwargs[0]["level"] == InferenceLevel.L2


def test_level_not_forwarded_to_atlas_coder(tmp_path: Path) -> None:
    """AtlasCoder.code() no tiene parámetro `level` (ni **kwargs) — reenviarlo
    a ciegas rompería la llamada. No debe forzarse."""
    repo = _git_repo(tmp_path)
    captured_kwargs: list[dict] = []

    def fake_code(self, task, context_files, test_cmd, max_iterations=3, **kwargs):
        captured_kwargs.append(kwargs)
        return CoderResult(success=True, iterations=1, files_changed=[], test_output="")

    from atlas.core.inference_hub import Provider, InferenceLevel
    fake_provider = Provider(
        name="fake", level=InferenceLevel.L2, base_url="http://x",
        model_id="m", litellm_model="m", api_key_env="FAKE_KEY",
    )

    with patch.dict("os.environ", {"FAKE_KEY": "x"}), \
         patch("atlas.core.atlas_coder.AtlasCoder.code", fake_code):
        coder = ParallelCoder(repo_root=repo, providers=[fake_provider])
        coder.run(
            subtasks=["t1"], context_files=["src/a.py"], test_cmd=["true"],
            level=InferenceLevel.L2,
        )

    assert captured_kwargs
    assert "level" not in captured_kwargs[0]


def test_ensemble_picks_fewest_iterations_among_successes(tmp_path: Path) -> None:
    """Modo ensemble (patrón Cursor, cross-audit 2026-07-02): la MISMA tarea se
    manda a N workers/proveedores; gana el que tuvo éxito con menos
    iteraciones. Los cambios de los NO ganadores nunca deben tocar el repo
    real (evita ediciones en conflicto de intentos redundantes)."""
    from atlas.core.inference_hub import Provider, InferenceLevel
    repo = _git_repo(tmp_path)

    providers = [
        Provider(name=f"p{i}", level=InferenceLevel.L1, base_url="http://x",
                  model_id="m", litellm_model="m", api_key_env=f"FAKE_KEY_{i}")
        for i in range(3)
    ]
    env = {f"FAKE_KEY_{i}": "x" for i in range(3)}

    # p0: éxito en 3 iteraciones, escribe "P0_WIN". p1: éxito en 1 iteración
    # (debe ganar), escribe "P1_WIN". p2: falla.
    outcomes = {
        "p0": (True, 3, "P0_WIN"),
        "p1": (True, 1, "P1_WIN"),
        "p2": (False, 1, None),
    }

    def fake_code(self, task, context_files, test_cmd, max_iterations=3, **kwargs):
        name = self._hub._providers[0].name
        success, iterations, marker = outcomes[name]
        if marker:
            target = self._repo_root / context_files[0]
            target.write_text(marker)
        return CoderResult(
            success=success, iterations=iterations,
            files_changed=[context_files[0]] if marker else [],
            test_output="",
        )

    with patch.dict("os.environ", env), \
         patch("atlas.core.atlas_coder.AtlasCoder.code", fake_code):
        coder = ParallelCoder(repo_root=repo, providers=providers)
        result = coder.run_ensemble(
            task="cambia A_OLD", context_files=["src/a.py"], test_cmd=["true"], n=3,
        )

    assert result.winner is not None
    assert result.winner.provider_name == "p1"
    assert result.attempts == 3
    # Solo el ganador (p1) debe haber sincronizado al repo real
    assert (repo / "src" / "a.py").read_text() == "P1_WIN"


def test_ensemble_no_winner_when_all_fail(tmp_path: Path) -> None:
    from atlas.core.inference_hub import Provider, InferenceLevel
    repo = _git_repo(tmp_path)
    original = (repo / "src" / "a.py").read_text()

    def fake_code(self, task, context_files, test_cmd, max_iterations=3, **kwargs):
        return CoderResult(success=False, iterations=1, files_changed=[], test_output="", error="nope")

    fake_provider = Provider(
        name="fake", level=InferenceLevel.L1, base_url="http://x",
        model_id="m", litellm_model="m", api_key_env="FAKE_KEY",
    )
    with patch.dict("os.environ", {"FAKE_KEY": "x"}), \
         patch("atlas.core.atlas_coder.AtlasCoder.code", fake_code):
        coder = ParallelCoder(repo_root=repo, providers=[fake_provider])
        result = coder.run_ensemble(
            task="tarea que falla", context_files=["src/a.py"], test_cmd=["true"], n=2,
        )

    assert result.winner is None
    assert result.attempts == 2
    assert (repo / "src" / "a.py").read_text() == original
