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
    F26GateStatus,
    f26_gate_notification,
    f26_gate_status,
    record_f26_run,
)


@pytest.fixture(autouse=True)
def _clean_git_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key, raising=False)


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


class TestNeverRun:
    def test_never_run_status_and_counts_all_current_adrs(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)

        status = f26_gate_status(repo)

        assert status.status == "never_run"
        assert status.last_run_sha is None
        assert "docs/decisions/adr/adr_001_first.md" in status.new_adrs_since


class TestRecordRun:
    def test_record_run_persists_head_sha_and_result(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)

        record = record_f26_run(repo, result="pass", notes="6/6 primera corrida")

        assert record["last_run_sha"] == _git(repo, "rev-parse", "HEAD")
        assert record["last_result"] == "pass"
        assert "generated_at" not in record  # el campo real se llama last_run_at
        assert "last_run_at" in record

    def test_record_run_rejects_invalid_result(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        with pytest.raises(ValueError):
            record_f26_run(repo, result="maybe")

    def test_status_current_immediately_after_recording_with_no_new_adrs(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path)
        record_f26_run(repo, result="pass")

        status = f26_gate_status(repo)

        assert status.status == "current"
        assert status.new_adrs_since == []
        assert status.last_result == "pass"


class TestDueOnNewAdr:
    def test_new_adr_after_recorded_run_marks_status_due(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        record_f26_run(repo, result="pass")

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
        record_f26_run(repo, result="pass")

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
        record_f26_run(repo, result="pass")

        (repo / "README.md").write_text("cambio irrelevante\n", encoding="utf-8")
        _commit_all(repo, "docs: readme")

        status = f26_gate_status(repo)

        assert status.status == "current"

    def test_re_recording_after_due_clears_it(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        record_f26_run(repo, result="pass")
        (repo / "docs" / "decisions" / "adr" / "adr_002_second.md").write_text(
            "# ADR-002\n", encoding="utf-8"
        )
        _commit_all(repo, "feat: ADR-002")
        assert f26_gate_status(repo).status == "due"

        record_f26_run(repo, result="pass", notes="6/6 tras ADR-002")
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

        record = record_f26_run(repo, result="pass", at_sha=first_sha)

        assert record["last_run_sha"] == first_sha
        status = f26_gate_status(repo)
        assert status.status == "due"  # ADR-002 es nuevo desde first_sha
        assert status.new_adrs_since == ["docs/decisions/adr/adr_002_second.md"]

    def test_cli_record_run_accepts_at_sha(
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

        assert result.exit_code == 0, result.output
        assert first_sha in result.output


class TestFailClosed:
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
        assert status.status == "current"
        assert status.last_result == "fail"


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

    def test_cli_f26_record_run_then_status_current(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from click.testing import CliRunner

        from atlas.interfaces.cli import cli

        repo = _make_repo(tmp_path)
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))
        runner = CliRunner()

        record = runner.invoke(cli, ["f26", "record-run", "--result", "pass", "--notes", "6/6"])
        assert record.exit_code == 0, record.output

        status = runner.invoke(cli, ["f26", "status"])
        assert "current" in status.output

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
        record_f26_run(repo, result="pass")
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
        record_f26_run(repo, result="pass")

        status = f26_gate_status(repo)

        assert status.status == "current"
        assert status.to_dict()["notification"] is None

    def test_to_dict_includes_notification_dict_when_due(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        record_f26_run(repo, result="pass")
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
        record_f26_run(repo, result="pass")
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
        record_f26_run(repo, result="pass")
        (repo / "docs" / "decisions" / "adr" / "adr_002_second.md").write_text(
            "# ADR-002\n", encoding="utf-8"
        )
        _commit_all(repo, "feat: ADR-002")

        report = collect_reality(repo_root=repo)

        assert report["f26_gate"]["notification"] is not None
        assert report["f26_gate"]["notification"]["title"]
