"""
Tests para atlas.core.validation_runner.

REGLA: NUNCA invocar ValidationRunner.run() real desde pytest.
subprocess.run está mockeado para capturar el env.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_proc(returncode: int = 0) -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = ""
    m.stderr = ""
    return m


def test_extra_env_se_aplica_al_subprocess(tmp_path: Path):
    """extra_env={'ATLAS_HOME': '/fake'} debe aparecer en el env pasado a subprocess.run."""
    from atlas.core.validation_runner import ValidationRunner

    runner = ValidationRunner(tmp_path, extra_env={"ATLAS_HOME": "/fake/home"})

    captured_envs: list[dict] = []

    def fake_run(cmd, **kwargs):
        captured_envs.append(dict(kwargs.get("env") or {}))
        return _make_proc(0)

    with patch("subprocess.run", side_effect=fake_run):
        # run() lanza RuntimeError si PYTEST_CURRENT_TEST en env — parchamos eso
        import os
        env_backup = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            runner.run(timeout_s=5)
        except Exception:
            pass
        finally:
            if env_backup is not None:
                os.environ["PYTEST_CURRENT_TEST"] = env_backup

    # Debe haber capturado al menos un env (pytest call)
    assert captured_envs, "subprocess.run no fue llamado"
    for env in captured_envs:
        assert env.get("ATLAS_HOME") == "/fake/home", f"ATLAS_HOME ausente o incorrecto: {env}"


def test_extra_env_gana_sobre_environ(tmp_path: Path, monkeypatch):
    """extra_env sobrescribe valores del environ base."""
    import os
    from atlas.core.validation_runner import ValidationRunner

    monkeypatch.setenv("ATLAS_HOME", "/original")
    runner = ValidationRunner(tmp_path, extra_env={"ATLAS_HOME": "/overridden"})

    captured_envs: list[dict] = []

    def fake_run(cmd, **kwargs):
        captured_envs.append(dict(kwargs.get("env") or {}))
        return _make_proc(0)

    with patch("subprocess.run", side_effect=fake_run):
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        runner.run(timeout_s=5)

    for env in captured_envs:
        assert env["ATLAS_HOME"] == "/overridden"


def test_sin_extra_env_funciona(tmp_path: Path, monkeypatch):
    """extra_env=None no rompe nada."""
    from atlas.core.validation_runner import ValidationRunner

    runner = ValidationRunner(tmp_path)

    def fake_run(cmd, **kwargs):
        return _make_proc(0)

    with patch("subprocess.run", side_effect=fake_run):
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        report = runner.run(timeout_s=5)

    assert report.passed is True


def test_guard_antirecursion_lanza():
    """run() dentro de pytest (con PYTEST_CURRENT_TEST) debe levantar RuntimeError."""
    import os
    from atlas.core.validation_runner import ValidationRunner

    runner = ValidationRunner(Path("/tmp"))
    assert "PYTEST_CURRENT_TEST" in os.environ
    import pytest as _pytest
    with _pytest.raises(RuntimeError, match="recursiva"):
        runner.run()
