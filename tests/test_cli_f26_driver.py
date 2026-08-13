"""CLI: `atlas f26 run --driver agentic` selecciona el dispatch agnóstico de
proveedor en vez del default `claude -p`. Sólo prueba la SELECCIÓN de
dispatch (monkeypatch de `run_f26`), no dispara red/LLM real."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from click.testing import CliRunner

from atlas.interfaces import cli as cli_mod


def _fake_run_f26_capturing(calls: list[dict[str, Any]]):
    def _fake(
        root: Path,
        *,
        doc_path: Path | None = None,
        dispatch=None,
        allow_unsafe_legacy_dispatch: bool = False,
    ) -> dict[str, Any]:
        calls.append({
            "root": root,
            "doc_path": doc_path,
            "dispatch": dispatch,
            "allow_unsafe_legacy_dispatch": allow_unsafe_legacy_dispatch,
        })
        return {
            "success": True, "transcript_path": "t.txt", "meta_path": "m.json",
            "grading": None, "overall_result": None, "recorded": False,
        }
    return _fake


class TestF26RunDriverFlag:
    def test_default_driver_uses_agentic_l1(self, tmp_path: Path, monkeypatch) -> None:
        calls: list[dict[str, Any]] = []
        captured: dict[str, Any] = {}

        def fake_agentic_dispatch(prompt: str, cwd: Path, **kwargs: Any) -> Any:
            captured.update(prompt=prompt, cwd=cwd, **kwargs)
            return None

        def fake_run(
            root: Path,
            *,
            doc_path: Path | None = None,
            dispatch=None,
            allow_unsafe_legacy_dispatch: bool = False,
        ) -> dict[str, Any]:
            assert dispatch is not None
            dispatch("prompt", root, task_id="f26:default")
            calls.append({
                "dispatch": dispatch,
                "allow_unsafe_legacy_dispatch": allow_unsafe_legacy_dispatch,
            })
            return {
                "success": True, "transcript_path": "t.txt", "meta_path": "m.json",
                "grading": None, "overall_result": None, "recorded": False,
            }

        monkeypatch.setattr(
            "atlas.core.self_maintenance.f26_agentic_dispatch.agentic_dispatch",
            fake_agentic_dispatch,
        )
        monkeypatch.setattr(
            "atlas.core.self_maintenance.f26_gate.run_f26", fake_run,
        )
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, ["f26", "run"])

        assert result.exit_code == 0, result.output
        assert len(calls) == 1
        assert callable(calls[0]["dispatch"])
        assert calls[0]["allow_unsafe_legacy_dispatch"] is False
        assert captured["level"].value == "L1"

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
        assert calls[0]["allow_unsafe_legacy_dispatch"] is False

    def test_agentic_level_l2_is_forwarded_explicitly(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_agentic_dispatch(prompt: str, cwd: Path, **kwargs: Any) -> Any:
            captured.update(prompt=prompt, cwd=cwd, **kwargs)
            return None

        def fake_run_f26(
            root: Path,
            *,
            doc_path: Path | None = None,
            dispatch=None,
            allow_unsafe_legacy_dispatch: bool = False,
        ) -> dict[str, Any]:
            assert dispatch is not None
            dispatch("prompt", root, task_id="f26:l2")
            return {
                "success": True, "transcript_path": "t.txt", "meta_path": "m.json",
                "grading": None, "overall_result": None, "recorded": False,
            }

        monkeypatch.setattr(
            "atlas.core.self_maintenance.f26_agentic_dispatch.agentic_dispatch",
            fake_agentic_dispatch,
        )
        monkeypatch.setattr(
            "atlas.core.self_maintenance.f26_gate.run_f26", fake_run_f26,
        )
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(
            cli_mod.cli, ["f26", "run", "--driver", "agentic", "--level", "L2"],
        )

        assert result.exit_code == 0, result.output
        assert captured["level"].value == "L2"

    def test_agentic_provider_pin_is_forwarded_explicitly(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_agentic_dispatch(prompt: str, cwd: Path, **kwargs: Any) -> Any:
            captured.update(prompt=prompt, cwd=cwd, **kwargs)
            return None

        def fake_run_f26(
            root: Path, *, doc_path: Path | None = None, dispatch=None,
            allow_unsafe_legacy_dispatch: bool = False,
        ) -> dict[str, Any]:
            assert dispatch is not None
            dispatch("prompt", root, task_id="f26:pinned")
            return {
                "success": True, "transcript_path": "t.txt", "meta_path": "m.json",
                "grading": None, "overall_result": None, "recorded": False,
            }

        monkeypatch.setattr(
            "atlas.core.self_maintenance.f26_agentic_dispatch.agentic_dispatch",
            fake_agentic_dispatch,
        )
        monkeypatch.setattr(
            "atlas.core.self_maintenance.f26_gate.run_f26", fake_run_f26,
        )
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, [
            "f26", "run", "--provider", "groq_llama_70b",
        ])

        assert result.exit_code == 0, result.output
        assert captured["provider_name"] == "groq_llama_70b"

    def test_agentic_approval_actor_is_forwarded_explicitly(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_agentic_dispatch(
            prompt: str, cwd: Path, *, golden_route_approval_actor: str | None = None,
            task_id: str | None = None, level: Any = None,
            provider_name: str | None = None,
        ) -> Any:
            captured.update(
                prompt=prompt,
                cwd=cwd,
                approval_actor=golden_route_approval_actor,
                task_id=task_id,
            )
            return None

        def fake_run_f26(
            root: Path, *, doc_path: Path | None = None, dispatch=None,
            allow_unsafe_legacy_dispatch: bool = False,
        ) -> dict[str, Any]:
            assert dispatch is not None
            dispatch("prompt", root, task_id="f26:exact-run-id")
            return {
                "success": True, "transcript_path": "t.txt", "meta_path": "m.json",
                "grading": None, "overall_result": None, "recorded": False,
            }

        monkeypatch.setattr(
            "atlas.core.self_maintenance.f26_agentic_dispatch.agentic_dispatch",
            fake_agentic_dispatch,
        )
        monkeypatch.setattr(
            "atlas.core.self_maintenance.f26_gate.run_f26", fake_run_f26,
        )
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, [
            "f26", "run", "--driver", "agentic",
            "--approval-actor", "tomas:f26-explicit",
        ])

        assert result.exit_code == 0, result.output
        assert captured["approval_actor"] == "tomas:f26-explicit"
        assert captured["task_id"] == "f26:exact-run-id"

    def test_approval_actor_is_rejected_for_claude_driver(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, [
            "f26", "run", "--driver", "claude", "--approval-actor", "operator",
        ])

        assert result.exit_code != 0
        assert "agentic" in result.output.casefold()

    def test_claude_driver_requires_explicit_unsafe_opt_in(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(
            "atlas.core.self_maintenance.f26_gate.run_f26", _fake_run_f26_capturing(calls),
        )
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, ["f26", "run", "--driver", "claude"])

        assert result.exit_code != 0
        assert not calls
        assert "unsafe" in result.output.casefold() or "inseguro" in result.output.casefold()

    def test_claude_driver_explicit_opt_in_reaches_legacy_dispatch(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(
            "atlas.core.self_maintenance.f26_gate.run_f26", _fake_run_f26_capturing(calls),
        )
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, [
            "f26", "run", "--driver", "claude", "--allow-unsafe-legacy-driver",
        ])

        assert result.exit_code == 0, result.output
        assert calls[0]["dispatch"] is None
        assert calls[0]["allow_unsafe_legacy_dispatch"] is True

    def test_unsafe_legacy_flag_is_rejected_for_agentic(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(
            "atlas.core.self_maintenance.f26_gate.run_f26", _fake_run_f26_capturing(calls),
        )
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, [
            "f26", "run", "--allow-unsafe-legacy-driver",
        ])

        assert result.exit_code != 0
        assert not calls
        assert "claude" in result.output.casefold()

    def test_prompt_extraction_error_is_reported_as_pre_dispatch(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        from atlas.core.self_maintenance.f26_gate import F26PromptExtractionError

        def fake_run(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            raise F26PromptExtractionError("doc ausente")

        monkeypatch.setattr("atlas.core.self_maintenance.f26_gate.run_f26", fake_run)
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, ["f26", "run"])

        assert result.exit_code != 0
        assert "construir el prompt" in result.output.casefold()
        assert "pudo haber dispatch" not in result.output.casefold()

    def test_audit_error_does_not_claim_it_was_pre_dispatch(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        from atlas.core.self_maintenance.f26_gate import F26AuditError

        def fake_run(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            raise F26AuditError("falló la escritura final")

        monkeypatch.setattr("atlas.core.self_maintenance.f26_gate.run_f26", fake_run)
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, ["f26", "run"])

        assert result.exit_code != 0
        normalized = " ".join(result.output.casefold().split())
        assert "pudo haber dispatch" in normalized
        assert "antes del dispatch" not in normalized

    def test_pending_review_is_never_rendered_as_pass(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        grading = {
            "score": "6/6",
            **{f"item_{index}": "pass" for index in range(1, 7)},
        }

        def fake_run(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {
                "success": True,
                "transcript_path": "t.txt",
                "meta_path": "m.json",
                "grading": grading,
                "automatic_result": "pass",
                "overall_result": "pending_review",
                "recorded": True,
                "f26_record": {
                    "last_run_sha": "abc123", "last_result": "pending_review",
                },
            }

        monkeypatch.setattr("atlas.core.self_maintenance.f26_gate.run_f26", fake_run)
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, ["f26", "run"])

        assert result.exit_code == 0, result.output
        assert "pending_review" in result.output
        assert "revisión semántica pendiente" in result.output.casefold()
        assert "result=pass" not in result.output.casefold()

    def test_failed_dispatch_returns_nonzero_exit(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        def fake_run(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {
                "success": False,
                "error": "unknown provider pin",
                "stderr": "provider inexistente",
                "meta_path": "m.json",
                "grading": None,
                "overall_result": None,
                "recorded": False,
            }

        monkeypatch.setattr("atlas.core.self_maintenance.f26_gate.run_f26", fake_run)
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, ["f26", "run"])

        assert result.exit_code != 0
        assert "unknown provider pin" in result.output

    def test_failed_dispatch_json_returns_nonzero_exit(self, tmp_path: Path, monkeypatch) -> None:
        def fake_run(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {
                "success": False,
                "error": "unknown provider pin",
                "stderr": "provider inexistente",
                "meta_path": "m.json",
                "grading": None,
                "overall_result": None,
                "recorded": False,
            }

        monkeypatch.setattr("atlas.core.self_maintenance.f26_gate.run_f26", fake_run)
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, ["f26", "run", "--json"])

        assert result.exit_code != 0
        assert '"success": false' in result.output.casefold()

    def test_help_does_not_advertise_removed_gemini_provider(self) -> None:
        result = CliRunner().invoke(cli_mod.cli, ["f26", "run", "--help"])

        assert result.exit_code == 0, result.output
        assert "Gemini" not in result.output
        assert "legacy" in result.output.casefold()

    def test_unknown_level_rejected(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, ["f26", "run", "--level", "L3"])

        assert result.exit_code != 0

    def test_unknown_driver_rejected(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, ["f26", "run", "--driver", "bogus"])

        assert result.exit_code != 0


class TestF26RecordRunSemanticReview:
    def test_pass_forwards_explicit_review_and_live_pending_hash(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        state_path = tmp_path / "workspace" / "self_build" / "f26_gate_state.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text(
            '{"state_sha256":"' + ("a" * 64) + '"}', encoding="utf-8",
        )
        captured: dict[str, Any] = {}

        def fake_record(root: Path, **kwargs: Any) -> dict[str, Any]:
            captured.update(root=root, **kwargs)
            return {"last_run_sha": "abc123", "last_result": "pass"}

        monkeypatch.setattr(
            "atlas.core.self_maintenance.f26_gate.record_f26_run", fake_record,
        )
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, [
            "f26", "record-run",
            "--result", "pass",
            "--transcript-sha256", "b" * 64,
            "--automatic-score", "6/6",
            "--semantic-review-actor", "tomas:f26-review",
        ])

        assert result.exit_code == 0, result.output
        assert captured["transcript_sha256"] == "b" * 64
        assert captured["automatic_score"] == "6/6"
        assert captured["semantic_verification"] == "operator_confirmed"
        assert captured["semantic_review_actor"] == "tomas:f26-review"
        assert captured["source_state_sha256"] == "a" * 64

    def test_pass_reads_shared_state_path_from_environment(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        shared_state = tmp_path / "runtime-authority" / "f26-state.json"
        shared_state.parent.mkdir(parents=True)
        shared_state.write_text(
            '{"state_sha256":"' + ("c" * 64) + '"}', encoding="utf-8",
        )
        captured: dict[str, Any] = {}

        def fake_record(root: Path, **kwargs: Any) -> dict[str, Any]:
            captured.update(root=root, **kwargs)
            return {"last_run_sha": "abc123", "last_result": "pass"}

        monkeypatch.setattr(
            "atlas.core.self_maintenance.f26_gate.record_f26_run", fake_record,
        )
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "clean-worktree"))
        monkeypatch.setenv("ATLAS_F26_STATE_PATH", str(shared_state))

        result = CliRunner().invoke(cli_mod.cli, [
            "f26", "record-run", "--result", "pass",
            "--transcript-sha256", "b" * 64,
            "--automatic-score", "6/6",
            "--semantic-review-actor", "operator",
        ])

        assert result.exit_code == 0, result.output
        assert captured["source_state_sha256"] == "c" * 64

    def test_pass_rejects_missing_pending_state_before_gate_call(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        called = False

        def fake_record(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            nonlocal called
            called = True
            return {}

        monkeypatch.setattr(
            "atlas.core.self_maintenance.f26_gate.record_f26_run", fake_record,
        )
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, [
            "f26", "record-run", "--result", "pass",
            "--transcript-sha256", "b" * 64,
            "--automatic-score", "6/6",
            "--semantic-review-actor", "operator",
        ])

        assert result.exit_code != 0
        assert called is False
        assert "pending" in result.output.casefold()

    def test_fail_rejects_semantic_review_actor(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))

        result = CliRunner().invoke(cli_mod.cli, [
            "f26", "record-run", "--result", "fail",
            "--semantic-review-actor", "operator",
        ])

        assert result.exit_code != 0
        assert "pass" in result.output.casefold()
