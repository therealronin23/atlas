"""t1-daemon-control-surface: fichero de estado de pausa del self-build.

Contrato de ``self_build_pause``: la sola presencia del fichero
``workspace/self_build/pause_state.json`` es la señal de pausa (fail-safe);
``pause``/``resume`` son idempotentes; ``pause_status`` es legible desde
``atlas selfbuild status``/``atlas reality`` sin lanzar nunca, incluso con
un JSON corrupto.
"""

from __future__ import annotations

from pathlib import Path

from atlas.core.self_maintenance.self_build_pause import (
    is_paused,
    pause,
    pause_status,
    resume,
)


def test_not_paused_by_default(tmp_path: Path) -> None:
    assert is_paused(tmp_path) is False
    assert pause_status(tmp_path) == {"paused": False, "paused_at": None, "reason": None}


def test_pause_writes_state_file_and_is_paused(tmp_path: Path) -> None:
    state = pause(tmp_path, reason="sesion de desarrollo")
    assert state["paused"] is True
    assert state["reason"] == "sesion de desarrollo"
    assert is_paused(tmp_path) is True

    status = pause_status(tmp_path)
    assert status["paused"] is True
    assert status["reason"] == "sesion de desarrollo"
    assert status["paused_at"] == state["paused_at"]

    state_file = tmp_path / "workspace" / "self_build" / "pause_state.json"
    assert state_file.is_file()


def test_pause_is_idempotent(tmp_path: Path) -> None:
    pause(tmp_path, reason="primero")
    pause(tmp_path, reason="segundo")
    assert is_paused(tmp_path) is True
    assert pause_status(tmp_path)["reason"] == "segundo"


def test_resume_clears_pause(tmp_path: Path) -> None:
    pause(tmp_path, reason="temporal")
    assert is_paused(tmp_path) is True

    resume(tmp_path)

    assert is_paused(tmp_path) is False
    assert pause_status(tmp_path) == {"paused": False, "paused_at": None, "reason": None}


def test_resume_without_prior_pause_is_a_noop(tmp_path: Path) -> None:
    resume(tmp_path)  # no debe lanzar
    assert is_paused(tmp_path) is False


def test_pause_status_fail_safe_on_corrupt_json(tmp_path: Path) -> None:
    state_dir = tmp_path / "workspace" / "self_build"
    state_dir.mkdir(parents=True)
    (state_dir / "pause_state.json").write_text("{not valid json", encoding="utf-8")

    # Fail-safe: un fichero corrupto sigue contando como PAUSADO, nunca lo
    # contrario -- mejor pausado de más que perder la señal por un parseo roto.
    assert is_paused(tmp_path) is True
    status = pause_status(tmp_path)
    assert status["paused"] is True
    assert status["reason"] == "pause_state.json unreadable"
