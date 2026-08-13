"""F2.6 como gate automático recurrente (spec B+C §4, MAXIMUS Cycle 12).

F2.6 (rúbrica de sucesión, 6 ítems) es cara y necesita juicio real — sigue
siendo una sesión LLM deliberada, NUNCA automática. Lo que SÍ se automatiza,
mismo principio que `PreflightGate`: la detección BARATA y determinista de
cuándo está DEBIDA ("cambio grande" = ADR nuevo desde el último run
registrado). Quien corre F2.6 de verdad registra el resultado con
`record_f26_run`; este módulo nunca inventa que se corrió.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from atlas.core.self_maintenance.f26_gate import (
    F26AuditError,
    F26GateStatus,
    f26_gate_notification,
    f26_gate_status,
    record_f26_run,
)


@pytest.fixture(autouse=True)
def _clean_git_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas-home"))


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return out.stdout.strip()


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", message)
    return _git(repo, "rev-parse", "HEAD")


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs" / "decisions" / "adr").mkdir(parents=True)
    (repo / "docs" / "decisions" / "adr" / "adr_001_first.md").write_text(
        "# ADR-001\n", encoding="utf-8"
    )
    _git(repo, "init", "-q")
    _commit_all(repo, "init")
    return repo


def _record_confirmed_pass(
    repo: Path, *, notes: str = "", at_sha: str | None = None,
) -> dict[str, object]:
    automatic = record_f26_run(
        repo,
        result="pending_review",
        notes=notes,
        at_sha=at_sha,
        transcript_sha256="a" * 64,
        automatic_score="6/6",
        semantic_verification="not_performed",
        _state_source="automatic_run",
    )
    return record_f26_run(
        repo,
        result="pass",
        notes=notes,
        at_sha=at_sha,
        transcript_sha256="a" * 64,
        automatic_score="6/6",
        semantic_verification="operator_confirmed",
        semantic_review_actor="atlas-tests:operator",
        source_state_sha256=str(automatic["state_sha256"]),
    )


class TestNeverRun:
    def test_never_run_status_and_counts_all_current_adrs(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)

        status = f26_gate_status(repo)

        assert status.status == "never_run"
        assert status.last_run_sha is None
        assert "docs/decisions/adr/adr_001_first.md" in status.new_adrs_since

    def test_orphan_f26_receipt_without_state_is_unknown(self, tmp_path: Path) -> None:
        from atlas.logging.merkle_logger import MerkleLogger

        repo = _make_repo(tmp_path)
        merkle = MerkleLogger(tmp_path / "atlas-home" / "memory" / "audit")
        merkle.log(
            action="session.started", agent="atlas.f26_gate", result="success",
            risk_level="moderate", payload={"run_sha": _git(repo, "rev-parse", "HEAD")},
            task_id="f26:orphan",
        )

        status = f26_gate_status(repo)

        assert status.status == "unknown"
        assert "state" in status.reason.casefold()

    def test_deleted_state_after_completed_run_is_unknown(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        record_f26_run(repo, result="fail")
        (repo / "workspace" / "self_build" / "f26_gate_state.json").unlink()

        status = f26_gate_status(repo)

        assert status.status == "unknown"

    def test_orphan_start_after_valid_state_is_unknown(self, tmp_path: Path) -> None:
        from atlas.logging.merkle_logger import MerkleLogger

        repo = _make_repo(tmp_path)
        _record_confirmed_pass(repo)
        merkle = MerkleLogger(tmp_path / "atlas-home" / "memory" / "audit")
        merkle.log(
            action="session.started", agent="atlas.f26_gate", result="success",
            risk_level="moderate", payload={"run_sha": _git(repo, "rev-parse", "HEAD")},
            task_id="f26:orphan-after-current",
        )

        status = f26_gate_status(repo)

        assert status.status == "unknown"
        assert "incomplet" in status.reason.casefold() or "orphan" in status.reason.casefold()

    def test_broken_merkle_without_state_is_unknown(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import atlas.core.self_maintenance.f26_gate as f26_gate_module

        repo = _make_repo(tmp_path)

        class BrokenMerkle:
            def __init__(self, _path: Path) -> None:
                pass

            def verify_chain(self) -> tuple[bool, str]:
                return False, "tampered fixture"

        monkeypatch.setattr(f26_gate_module, "MerkleLogger", BrokenMerkle)

        status = f26_gate_status(repo)

        assert status.status == "unknown"
        assert "Merkle" in status.reason


class TestRecordRun:
    def test_record_run_persists_head_sha_and_result(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)

        record = _record_confirmed_pass(repo, notes="6/6 primera corrida")

        assert record["last_run_sha"] == _git(repo, "rev-parse", "HEAD")
        assert record["last_result"] == "pass"
        assert "generated_at" not in record  # el campo real se llama last_run_at
        assert "last_run_at" in record

    def test_record_run_rejects_invalid_result(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        with pytest.raises(ValueError):
            record_f26_run(repo, result="maybe")

    def test_manual_pass_without_bound_semantic_review_is_rejected(
        self, tmp_path: Path,
    ) -> None:
        repo = _make_repo(tmp_path)

        with pytest.raises(Exception, match="semantic|semánt|6/6|transcript"):
            record_f26_run(repo, result="pass")

    def test_automatic_six_of_six_remains_due_pending_semantic_review(
        self, tmp_path: Path,
    ) -> None:
        repo = _make_repo(tmp_path)

        record = record_f26_run(
            repo,
            result="pending_review",
            transcript_sha256="b" * 64,
            automatic_score="6/6",
            semantic_verification="not_performed",
            task_id="f26:pending",
            _state_source="automatic_run",
        )
        status = f26_gate_status(repo)

        assert record["last_result"] == "pending_review"
        assert status.status == "due"
        assert status.last_result == "pending_review"
        notification = status.to_dict()["notification"]
        assert notification is not None
        assert "review" in (notification["title"] + notification["prompt"]).casefold()

    def test_pending_review_with_new_adr_requires_rerun_not_old_review(
        self, tmp_path: Path,
    ) -> None:
        repo = _make_repo(tmp_path)
        record_f26_run(
            repo,
            result="pending_review",
            transcript_sha256="b" * 64,
            automatic_score="6/6",
            semantic_verification="not_performed",
            task_id="f26:pending-before-new-adr",
            _state_source="automatic_run",
        )
        (repo / "docs" / "decisions" / "adr" / "adr_002_second.md").write_text(
            "# ADR-002\n", encoding="utf-8",
        )
        _commit_all(repo, "feat: ADR after pending review")

        status = f26_gate_status(repo)
        notification = status.to_dict()["notification"]

        assert status.status == "due"
        assert notification is not None
        combined = (notification["title"] + notification["prompt"]).casefold()
        assert "repet" in combined or "corre de nuevo" in combined
        assert "no confirmes" in combined

    def test_confirmed_pass_must_link_latest_pending_review_hash(
        self, tmp_path: Path,
    ) -> None:
        repo = _make_repo(tmp_path)
        pending = record_f26_run(
            repo,
            result="pending_review",
            transcript_sha256="c" * 64,
            automatic_score="6/6",
            semantic_verification="not_performed",
            task_id="f26:pending-link",
            _state_source="automatic_run",
        )

        with pytest.raises(F26AuditError, match="source|pending|latest"):
            record_f26_run(
                repo,
                result="pass",
                transcript_sha256="c" * 64,
                automatic_score="6/6",
                semantic_verification="operator_confirmed",
                semantic_review_actor="operator",
                source_state_sha256="d" * 64,
            )

        assert pending["state_sha256"] != "d" * 64

    def test_status_current_immediately_after_recording_with_no_new_adrs(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path)
        _record_confirmed_pass(repo)

        status = f26_gate_status(repo)

        assert status.status == "current"
        assert status.new_adrs_since == []
        assert status.last_result == "pass"


class TestDueOnNewAdr:
    def test_new_adr_after_recorded_run_marks_status_due(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        _record_confirmed_pass(repo)

        (repo / "docs" / "decisions" / "adr" / "adr_002_second.md").write_text(
            "# ADR-002\n", encoding="utf-8"
        )
        _commit_all(repo, "feat: ADR-002")

        status = f26_gate_status(repo)

        assert status.status == "due"
        assert status.new_adrs_since == ["docs/decisions/adr/adr_002_second.md"]
        assert "1 ADR" in status.reason

    def test_multiple_new_adrs_all_listed(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        _record_confirmed_pass(repo)

        for n in (2, 3):
            (repo / "docs" / "decisions" / "adr" / f"adr_00{n}_x.md").write_text(
                f"# ADR-00{n}\n", encoding="utf-8"
            )
        _commit_all(repo, "feat: 2 ADRs nuevos")

        status = f26_gate_status(repo)

        assert status.status == "due"
        assert len(status.new_adrs_since) == 2

    def test_non_adr_changes_do_not_trigger_due(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        _record_confirmed_pass(repo)

        (repo / "README.md").write_text("cambio irrelevante\n", encoding="utf-8")
        _commit_all(repo, "docs: readme")

        status = f26_gate_status(repo)

        assert status.status == "current"

    def test_re_recording_after_due_clears_it(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        _record_confirmed_pass(repo)
        (repo / "docs" / "decisions" / "adr" / "adr_002_second.md").write_text(
            "# ADR-002\n", encoding="utf-8"
        )
        _commit_all(repo, "feat: ADR-002")
        assert f26_gate_status(repo).status == "due"

        _record_confirmed_pass(repo, notes="6/6 tras ADR-002")
        status = f26_gate_status(repo)

        assert status.status == "current"
        assert status.new_adrs_since == []


class TestAtShaBackfill:
    def test_record_run_with_explicit_at_sha_overrides_head(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        first_sha = _git(repo, "rev-parse", "HEAD")
        (repo / "docs" / "decisions" / "adr" / "adr_002_second.md").write_text(
            "# ADR-002\n", encoding="utf-8"
        )
        _commit_all(repo, "feat: ADR-002")  # HEAD avanza; first_sha queda atrás

        record = _record_confirmed_pass(repo, at_sha=first_sha)

        assert record["last_run_sha"] == first_sha
        status = f26_gate_status(repo)
        assert status.status == "due"  # ADR-002 es nuevo desde first_sha
        assert status.new_adrs_since == ["docs/decisions/adr/adr_002_second.md"]

    def test_cli_record_run_cannot_self_assert_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from click.testing import CliRunner

        from atlas.interfaces.cli import cli

        repo = _make_repo(tmp_path)
        first_sha = _git(repo, "rev-parse", "HEAD")
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))
        runner = CliRunner()

        result = runner.invoke(
            cli, ["f26", "record-run", "--result", "pass", "--at-sha", first_sha]
        )

        assert result.exit_code != 0


class TestFailClosed:
    def test_publish_failure_preserves_previous_state_and_leaves_gate_unknown(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import atlas.core.self_maintenance.f26_gate as f26_gate_module

        repo = _make_repo(tmp_path)
        state_path = tmp_path / "shared" / "f26.json"
        record_f26_run(repo, result="fail", notes="previous", state_path=state_path)
        previous = state_path.read_bytes()

        monkeypatch.setattr(
            f26_gate_module,
            "_publish_f26_state",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                F26AuditError("injected publish failure")
            ),
        )

        with pytest.raises(F26AuditError, match="publish failure"):
            record_f26_run(repo, result="fail", notes="new", state_path=state_path)

        assert state_path.read_bytes() == previous
        assert len(f26_gate_module._pending_state_paths(state_path)) == 1
        status = f26_gate_status(repo, state_path=state_path)
        assert status.status == "unknown"
        assert "staged" in status.reason.casefold()

    def test_review_receipt_without_prior_automatic_pending_end_is_unknown(
        self, tmp_path: Path,
    ) -> None:
        import atlas.core.self_maintenance.f26_gate as f26_gate_module
        from atlas.logging.merkle_logger import MerkleLogger

        repo = _make_repo(tmp_path)
        run_sha = _git(repo, "rev-parse", "HEAD")
        source_hash = "e" * 64
        base = {
            "last_run_sha": run_sha,
            "last_run_at": "2026-08-13T08:00:00+00:00",
            "last_result": "pass",
            "notes": "forged review without source terminal",
            "task_id": "f26:review:forged",
            "transcript_sha256": "a" * 64,
            "automatic_score": "6/6",
            "semantic_verification": "operator_confirmed",
            "semantic_review_actor": "operator",
            "state_source": "semantic_review",
            "source_state_sha256": source_hash,
        }
        state = {**base, "state_sha256": f26_gate_module._state_sha256(base)}
        state_path = repo / "workspace" / "self_build" / "f26_gate_state.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        merkle = MerkleLogger(tmp_path / "atlas-home" / "memory" / "audit")
        merkle.log(
            action="session.ended", agent="atlas.f26_gate", result="success",
            risk_level="moderate", task_id="f26:review:forged",
            payload={
                "run_sha": run_sha,
                "overall_result": "pass",
                "transcript_sha256": "a" * 64,
                "state_sha256": state["state_sha256"],
                "state_source": "semantic_review",
                "automatic_score": "6/6",
                "semantic_verification": "operator_confirmed",
                "semantic_review_actor": "operator",
                "source_state_sha256": source_hash,
            },
        )

        status = f26_gate_status(repo)

        assert status.status == "unknown"
        assert "pending" in status.reason.casefold() or "source" in status.reason.casefold()

    def test_corrupt_state_file_reports_unknown_never_crashes(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        state_path = tmp_path / "state.json"
        state_path.write_text("{not valid json", encoding="utf-8")

        status = f26_gate_status(repo, state_path=state_path)

        assert status.status == "unknown"

    def test_custom_state_path_is_respected(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        state_path = tmp_path / "custom" / "f26.json"

        record_f26_run(repo, result="fail", notes="2/6, gaps reales", state_path=state_path)

        assert state_path.is_file()
        status = f26_gate_status(repo, state_path=state_path)
        assert status.status == "due"
        assert status.last_result == "fail"

    def test_failed_run_remains_due_without_new_adrs(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        record_f26_run(repo, result="fail", notes="automatic 4/6")

        status = f26_gate_status(repo)

        assert status.status == "due"
        assert status.new_adrs_since == []
        assert "fall" in status.reason.casefold() or "repet" in status.reason.casefold()

    def test_fail_state_rejects_success_receipt_result(self, tmp_path: Path) -> None:
        import atlas.core.self_maintenance.f26_gate as f26_gate_module
        from atlas.logging.merkle_logger import MerkleLogger

        repo = _make_repo(tmp_path)
        state = record_f26_run(repo, result="fail", notes="real failure")
        merkle = MerkleLogger(tmp_path / "atlas-home" / "memory" / "audit")
        records = merkle.read_all()
        ended = records[-1]
        assert ended.result == "failure"
        ended.result = "success"
        ended.hash_self = ended._compute()
        audit_file = tmp_path / "atlas-home" / "memory" / "audit" / "merkle.jsonl"
        audit_file.write_text(
            "\n".join(json.dumps(record.to_dict()) for record in records) + "\n",
            encoding="utf-8",
        )

        status = f26_gate_status(repo)

        assert state["last_result"] == "fail"
        assert status.status == "unknown"
        assert "receipt" in status.reason.casefold() or "result" in status.reason.casefold()

    def test_legacy_failed_state_remains_due_but_legacy_pass_is_unknown(
        self, tmp_path: Path,
    ) -> None:
        repo = _make_repo(tmp_path)
        state_path = tmp_path / "legacy-state.json"
        legacy = {
            "last_run_sha": _git(repo, "rev-parse", "HEAD"),
            "last_run_at": "2026-08-12T01:45:48+00:00",
            "last_result": "fail",
            "notes": "automatic 4/6",
        }
        state_path.write_text(json.dumps(legacy), encoding="utf-8")

        failed = f26_gate_status(repo, state_path=state_path)
        legacy["last_result"] = "pass"
        state_path.write_text(json.dumps(legacy), encoding="utf-8")
        passed = f26_gate_status(repo, state_path=state_path)

        assert failed.status == "due"
        assert failed.to_dict()["notification"] is not None
        assert "legad" in failed.reason.casefold()
        assert passed.status == "unknown"


class TestCliWiring:
    def test_cli_f26_status_never_run(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from click.testing import CliRunner

        from atlas.interfaces.cli import cli

        repo = _make_repo(tmp_path)
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))
        runner = CliRunner()

        result = runner.invoke(cli, ["f26", "status"])

        assert result.exit_code == 0, result.output
        assert "never_run" in result.output

    def test_cli_f26_record_run_rejects_unbound_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from click.testing import CliRunner

        from atlas.interfaces.cli import cli

        repo = _make_repo(tmp_path)
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))
        runner = CliRunner()

        record = runner.invoke(
            cli, ["f26", "record-run", "--result", "pass", "--notes", "6/6"]
        )

        assert record.exit_code != 0

    def test_cli_f26_record_run_rejects_bad_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from click.testing import CliRunner

        from atlas.interfaces.cli import cli

        repo = _make_repo(tmp_path)
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))
        runner = CliRunner()

        result = runner.invoke(cli, ["f26", "record-run", "--result", "maybe"])

        assert result.exit_code != 0


class TestRealityWiring:
    def test_reality_surfaces_f26_never_run(self, tmp_path: Path) -> None:
        from atlas.core.reality import collect_reality

        repo = _make_repo(tmp_path)
        report = collect_reality(repo_root=repo)

        assert report["f26_gate"]["status"] == "never_run"

    def test_reality_surfaces_f26_due_after_new_adr(self, tmp_path: Path) -> None:
        from atlas.core.reality import collect_reality

        repo = _make_repo(tmp_path)
        _record_confirmed_pass(repo)
        (repo / "docs" / "decisions" / "adr" / "adr_002_second.md").write_text(
            "# ADR-002\n", encoding="utf-8"
        )
        _commit_all(repo, "feat: ADR-002")

        report = collect_reality(repo_root=repo)

        assert report["f26_gate"]["status"] == "due"
        assert report["f26_gate"]["new_adrs_since"]


class TestNotification:
    """Punto 4 del diseño (docs/superpowers/plans/2026-07-17-f26-succession-test-PENDIENTE.md):
    la notificación NUNCA llama a spawn_task ella misma (esa tool solo existe
    dentro de una sesión agente MCP) — solo prepara el dict con los mismos
    campos que esa tool espera, para que CUALQUIER sesión agente que vea
    status=='due' pueda invocarla."""

    def _due_status(self, new_adrs: list[str]) -> F26GateStatus:
        return F26GateStatus(
            status="due",
            last_run_sha="abc123",
            last_run_at="2026-07-20T00:00:00+00:00",
            last_result="pass",
            new_adrs_since=new_adrs,
            reason=f"{len(new_adrs)} ADR(s) nuevo(s) desde el último run",
        )

    def test_due_status_returns_dict_with_three_fields(self) -> None:
        status = self._due_status(["docs/decisions/adr/adr_002_second.md"])

        notification = f26_gate_notification(status)

        assert notification is not None
        assert set(notification.keys()) == {"title", "tldr", "prompt"}
        assert isinstance(notification["title"], str)
        assert isinstance(notification["tldr"], str)
        assert isinstance(notification["prompt"], str)

    def test_title_under_60_chars_and_imperative(self) -> None:
        status = self._due_status(["docs/decisions/adr/adr_002_second.md"])

        notification = f26_gate_notification(status)

        assert notification is not None
        assert len(notification["title"]) < 60
        assert "f26" in notification["title"].lower() or "F2.6" in notification["title"]

    def test_adr_count_cited_in_title_and_tldr(self) -> None:
        status = self._due_status([
            "docs/decisions/adr/adr_002_second.md",
            "docs/decisions/adr/adr_003_third.md",
        ])

        notification = f26_gate_notification(status)

        assert notification is not None
        assert "2" in notification["title"]
        assert "2" in notification["tldr"]

    def test_prompt_mentions_atlas_f26_run_and_is_self_contained(self) -> None:
        status = self._due_status(["docs/decisions/adr/adr_002_second.md"])

        notification = f26_gate_notification(status)

        assert notification is not None
        assert "atlas f26 run" in notification["prompt"]
        assert "docs/decisions/adr/adr_002_second.md" in notification["prompt"]

    def test_failed_run_notification_includes_capable_provider_and_actor(self) -> None:
        status = F26GateStatus(
            status="due", last_run_sha="abc123",
            last_run_at="2026-08-13T00:00:00+00:00", last_result="fail",
            new_adrs_since=[], reason="el último run falló",
        )

        notification = f26_gate_notification(status)

        assert notification is not None
        assert "--provider groq_llama_70b" in notification["prompt"]
        assert "--approval-actor ACTOR" in notification["prompt"]

    @pytest.mark.parametrize("status_value", ["current", "never_run", "unknown"])
    def test_non_due_status_returns_none(self, status_value: str) -> None:
        status = F26GateStatus(
            status=status_value,
            last_run_sha=None,
            last_run_at=None,
            last_result=None,
            new_adrs_since=[],
            reason="da igual",
        )

        assert f26_gate_notification(status) is None

    def test_to_dict_includes_notification_null_when_not_due(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        _record_confirmed_pass(repo)

        status = f26_gate_status(repo)

        assert status.status == "current"
        assert status.to_dict()["notification"] is None

    def test_to_dict_includes_notification_dict_when_due(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        _record_confirmed_pass(repo)
        (repo / "docs" / "decisions" / "adr" / "adr_002_second.md").write_text(
            "# ADR-002\n", encoding="utf-8"
        )
        _commit_all(repo, "feat: ADR-002")

        status = f26_gate_status(repo)
        notification = status.to_dict()["notification"]

        assert status.status == "due"
        assert notification is not None
        assert notification["title"]

    def test_cli_f26_status_json_exposes_notification(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from click.testing import CliRunner

        from atlas.interfaces.cli import cli

        repo = _make_repo(tmp_path)
        _record_confirmed_pass(repo)
        (repo / "docs" / "decisions" / "adr" / "adr_002_second.md").write_text(
            "# ADR-002\n", encoding="utf-8"
        )
        _commit_all(repo, "feat: ADR-002")
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))
        runner = CliRunner()

        result = runner.invoke(cli, ["f26", "status", "--json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["notification"] is not None
        assert "atlas f26 run" in payload["notification"]["prompt"]

    def test_reality_json_exposes_f26_notification_when_due(self, tmp_path: Path) -> None:
        from atlas.core.reality import collect_reality

        repo = _make_repo(tmp_path)
        _record_confirmed_pass(repo)
        (repo / "docs" / "decisions" / "adr" / "adr_002_second.md").write_text(
            "# ADR-002\n", encoding="utf-8"
        )
        _commit_all(repo, "feat: ADR-002")

        report = collect_reality(repo_root=repo)

        assert report["f26_gate"]["notification"] is not None
        assert report["f26_gate"]["notification"]["title"]
