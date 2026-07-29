"""Tests for ancestry-verified, read-only incremental review preparation."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlas.core.git_env import clean_git_env
from atlas.core.verify import Verdict
from atlas.engineering.baselines import EngineeringReviewBaselineStore
from atlas.engineering.incremental import (
    EngineeringIncrementalReviewRunner,
    EngineeringIncrementalReviewPreparer,
    IncrementalReviewPreparationError,
)
from atlas.engineering.findings import EngineeringFindingStore
from atlas.engineering.review import (
    EngineeringReviewReport,
    EngineeringReviewCoordinator,
    EngineeringReviewRequest,
    ReviewOutcome,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        env=clean_git_env(),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, filename: str, content: str, message: str) -> str:
    path = repo / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", filename)
    _git(repo, "commit", "-qm", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture()
def repository(tmp_path: Path) -> tuple[Path, str, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    first = _commit(repo, "src/example.py", "one\n", "first")
    accepted = _commit(repo, "src/example.py", "two\n", "accepted")
    candidate = _commit(repo, "src/example.py", "three\n", "candidate")
    return repo, first, accepted, candidate


def _request(*, base: str, candidate: str) -> EngineeringReviewRequest:
    return EngineeringReviewRequest(
        run_id="run_incremental_001",
        task_id="task_001",
        mission_id=None,
        repository="atlas-core",
        base_revision=base,
        candidate_revision=candidate,
        diff="caller-provided diff must be replaced only after verification",
        scope=("src/example.py",),
        acceptance_criteria=("Use the verified delta only.",),
        at="2026-07-29T16:00:00+00:00",
    )


def _pass_report(*, base: str, candidate: str) -> EngineeringReviewReport:
    return EngineeringReviewReport(
        request=_request(base=base, candidate=candidate),
        verdict=Verdict.PASS,
        outcomes=(ReviewOutcome(adapter_id="deterministic", verdict=Verdict.PASS),),
        findings=(),
    )


def test_preparer_uses_explicit_accepted_base_and_returns_only_verified_delta(
    repository: tuple[Path, str, str, str], tmp_path: Path
) -> None:
    repo, first, accepted, candidate = repository
    baselines = EngineeringReviewBaselineStore(tmp_path / "baselines.jsonl")
    baselines.record_accepted(
        _pass_report(base=first, candidate=accepted),
        acceptance_ref="approval_001",
        accepted_by="operator",
        at="2026-07-29T16:01:00+00:00",
    )

    prepared = EngineeringIncrementalReviewPreparer(
        repo_root=repo,
        baselines=baselines,
    ).prepare(_request(base=first, candidate=candidate))

    assert prepared.ancestry_verified is True
    assert prepared.request is not None
    assert prepared.request.base_revision == accepted
    assert "+three" in prepared.request.diff
    assert "-one" not in prepared.request.diff
    assert prepared.selection.accepted_baseline is not None


def test_preparer_refuses_a_baseline_that_is_not_an_ancestor(
    repository: tuple[Path, str, str, str], tmp_path: Path
) -> None:
    repo, first, accepted, candidate = repository
    _git(repo, "checkout", "-qb", "side", first)
    side = _commit(repo, "src/side.py", "side\n", "side")
    _git(repo, "checkout", "-q", candidate)
    baselines = EngineeringReviewBaselineStore(tmp_path / "baselines.jsonl")
    baselines.record_accepted(
        _pass_report(base=first, candidate=side),
        acceptance_ref="approval_side",
        accepted_by="operator",
        at="2026-07-29T16:01:00+00:00",
    )

    with pytest.raises(IncrementalReviewPreparationError, match="not an ancestor"):
        EngineeringIncrementalReviewPreparer(repo_root=repo, baselines=baselines).prepare(
            _request(base=first, candidate=candidate)
        )


def test_already_accepted_candidate_skips_git_diff_and_review(
    repository: tuple[Path, str, str, str], tmp_path: Path
) -> None:
    repo, first, accepted, _candidate = repository
    baselines = EngineeringReviewBaselineStore(tmp_path / "baselines.jsonl")
    baselines.record_accepted(
        _pass_report(base=first, candidate=accepted),
        acceptance_ref="approval_001",
        accepted_by="operator",
        at="2026-07-29T16:01:00+00:00",
    )

    prepared = EngineeringIncrementalReviewPreparer(repo_root=repo, baselines=baselines).prepare(
        _request(base=first, candidate=accepted)
    )

    assert prepared.request is None
    assert prepared.ancestry_verified is False
    assert prepared.selection.review_required is False


def test_preparer_never_requests_external_diff_or_textconv(
    repository: tuple[Path, str, str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, first, accepted, candidate = repository
    baselines = EngineeringReviewBaselineStore(tmp_path / "baselines.jsonl")
    baselines.record_accepted(
        _pass_report(base=first, candidate=accepted),
        acceptance_ref="approval_001",
        accepted_by="operator",
        at="2026-07-29T16:01:00+00:00",
    )
    seen: list[list[str]] = []
    real_run = subprocess.run

    def recording_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(command)
        return real_run(command, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("atlas.engineering.incremental.subprocess.run", recording_run)

    EngineeringIncrementalReviewPreparer(repo_root=repo, baselines=baselines).prepare(
        _request(base=first, candidate=candidate)
    )

    diff_command = next(command for command in seen if command[1] == "diff")
    assert "--no-ext-diff" in diff_command
    assert "--no-textconv" in diff_command


def test_preparer_rejects_an_oversized_diff_before_review(
    repository: tuple[Path, str, str, str], tmp_path: Path
) -> None:
    repo, first, accepted, candidate = repository
    baselines = EngineeringReviewBaselineStore(tmp_path / "baselines.jsonl")
    baselines.record_accepted(
        _pass_report(base=first, candidate=accepted),
        acceptance_ref="approval_001",
        accepted_by="operator",
        at="2026-07-29T16:01:00+00:00",
    )

    with pytest.raises(IncrementalReviewPreparationError, match="exceeds"):
        EngineeringIncrementalReviewPreparer(
            repo_root=repo,
            baselines=baselines,
            max_diff_bytes=1,
        ).prepare(_request(base=first, candidate=candidate))


class _CapturingAdapter:
    adapter_id = "capturing"

    def __init__(self) -> None:
        self.requests: list[EngineeringReviewRequest] = []

    def review(self, request: EngineeringReviewRequest) -> ReviewOutcome:
        self.requests.append(request)
        return ReviewOutcome(adapter_id=self.adapter_id, verdict=Verdict.PASS)


def test_incremental_runner_composes_verified_delta_with_existing_review_coordinator(
    repository: tuple[Path, str, str, str], tmp_path: Path
) -> None:
    repo, first, accepted, candidate = repository
    baselines = EngineeringReviewBaselineStore(tmp_path / "baselines.jsonl")
    baselines.record_accepted(
        _pass_report(base=first, candidate=accepted),
        acceptance_ref="approval_001",
        accepted_by="operator",
        at="2026-07-29T16:01:00+00:00",
    )
    adapter = _CapturingAdapter()
    coordinator = EngineeringReviewCoordinator(
        store=EngineeringFindingStore(tmp_path / "findings.jsonl"),
        adapters=[adapter],
    )
    runner = EngineeringIncrementalReviewRunner(
        preparer=EngineeringIncrementalReviewPreparer(repo_root=repo, baselines=baselines),
        coordinator=coordinator,
    )

    execution = runner.run(_request(base=first, candidate=candidate))

    assert execution.report is not None
    assert execution.report.verdict is Verdict.PASS
    assert execution.prepared.ancestry_verified is True
    assert adapter.requests[0].base_revision == accepted
    assert "+three" in adapter.requests[0].diff


def test_incremental_runner_does_not_re_review_an_already_accepted_candidate(
    repository: tuple[Path, str, str, str], tmp_path: Path
) -> None:
    repo, first, accepted, _candidate = repository
    baselines = EngineeringReviewBaselineStore(tmp_path / "baselines.jsonl")
    baselines.record_accepted(
        _pass_report(base=first, candidate=accepted),
        acceptance_ref="approval_001",
        accepted_by="operator",
        at="2026-07-29T16:01:00+00:00",
    )
    adapter = _CapturingAdapter()
    coordinator = EngineeringReviewCoordinator(
        store=EngineeringFindingStore(tmp_path / "findings.jsonl"),
        adapters=[adapter],
    )
    runner = EngineeringIncrementalReviewRunner(
        preparer=EngineeringIncrementalReviewPreparer(repo_root=repo, baselines=baselines),
        coordinator=coordinator,
    )

    execution = runner.run(_request(base=first, candidate=accepted))

    assert execution.report is None
    assert execution.prepared.selection.review_required is False
    assert adapter.requests == []
