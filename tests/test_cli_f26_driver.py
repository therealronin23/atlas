"""CLI: `atlas f26 run --driver agentic` selecciona el dispatch agnóstico de
proveedor en vez del default `claude -p`. Sólo prueba la SELECCIÓN de
dispatch (monkeypatch de `run_f26`), no dispara red/LLM real."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from click.testing import CliRunner

from atlas.interfaces import cli as cli_mod


def _fake_run_f26_capturing(calls: list[dict[str, Any]]):
    def _fake(root: Path, *, doc_path: Path | None = None, dispatch=None) -> dict[str, Any]:
        calls.append({"root": root, "doc_path": doc_path, "dispatch": dispatch})
        return {
            "success": True, "transcript_path": "t.txt", "meta_path": "m.json",
            "grading": None, "overall_result": None, "recorded": False,
        }
    return _fake


class TestF26RunDriverFlag:
    def test_default_driver_leaves_dispatch_unset(self, tmp_path: Path, monkeypatch) -> None:
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(
            "atlas.core.self_maintenance.f26_gate.run_f26", _fake_run_f26_capturing(calls),
        )
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, ["f26", "run"])

        assert result.exit_code == 0, result.output
        assert len(calls) == 1
        assert calls[0]["dispatch"] is None  # run_f26 usa su default (_default_claude_dispatch)

    def test_driver_agentic_passes_agentic_dispatch(self, tmp_path: Path, monkeypatch) -> None:
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(
            "atlas.core.self_maintenance.f26_gate.run_f26", _fake_run_f26_capturing(calls),
        )
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, ["f26", "run", "--driver", "agentic"])

        assert result.exit_code == 0, result.output
        assert len(calls) == 1
        assert callable(calls[0]["dispatch"])

    def test_unknown_driver_rejected(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, ["f26", "run", "--driver", "bogus"])

        assert result.exit_code != 0
