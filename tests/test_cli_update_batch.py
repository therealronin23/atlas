"""CLI tests for the `atlas update batch-review` / `batch-approve` commands."""

from __future__ import annotations

from click.testing import CliRunner

from atlas.interfaces import cli as cli_mod


class _FakeBatchResult:
    def __init__(
        self,
        *,
        id: str,
        included: list[str],
        excluded: list[dict[str, str]],
        passed: bool,
        pytest_summary: str = "",
    ) -> None:
        self.id = id
        self.included = included
        self.excluded = excluded
        self.passed = passed
        self.pytest_summary = pytest_summary

    def to_dict(self):
        return {
            "id": self.id,
            "included": self.included,
            "excluded": self.excluded,
            "passed": self.passed,
            "pytest_summary": self.pytest_summary,
        }


class _FakeBatcher:
    def __init__(self, batches: dict[str, _FakeBatchResult] | None = None) -> None:
        self._batches = batches or {}

    def get_batch(self, batch_id: str):
        return self._batches.get(batch_id)

    def latest_batch(self):
        if not self._batches:
            return None
        return list(self._batches.values())[-1]


class _FakeOrchestrator:
    def __init__(self, batcher: _FakeBatcher, advance_results: dict[str, str] | None = None) -> None:
        self._batcher = batcher
        self._advance_results = advance_results or {}
        self.advance_calls: list[str] = []

    def maintenance_cold_update_batcher(self):
        return self._batcher

    def advance_cold_update(self, proposal_id: str) -> str:
        self.advance_calls.append(proposal_id)
        return self._advance_results.get(proposal_id, f"applied: {proposal_id}")


def test_batch_review_no_batches(monkeypatch) -> None:
    fake = _FakeOrchestrator(_FakeBatcher())
    monkeypatch.setattr(cli_mod, "get_orchestrator", lambda: fake)

    result = CliRunner().invoke(cli_mod.cli, ["update", "batch-review"])

    assert result.exit_code == 0
    assert "No hay ningún lote todavía" in result.output


def test_batch_review_shows_included_and_excluded(monkeypatch) -> None:
    batch = _FakeBatchResult(
        id="batch-1",
        included=["p1", "p2"],
        excluded=[{"proposal_id": "p3", "reason": "rompe tests"}],
        passed=True,
        pytest_summary="2 passed",
    )
    fake = _FakeOrchestrator(_FakeBatcher({"batch-1": batch}))
    monkeypatch.setattr(cli_mod, "get_orchestrator", lambda: fake)

    result = CliRunner().invoke(cli_mod.cli, ["update", "batch-review"])

    assert result.exit_code == 0
    assert "batch-1" in result.output
    assert "p1" in result.output
    assert "p2" in result.output
    assert "p3" in result.output
    assert "rompe tests" in result.output


def test_batch_approve_nonexistent_batch(monkeypatch) -> None:
    fake = _FakeOrchestrator(_FakeBatcher())
    monkeypatch.setattr(cli_mod, "get_orchestrator", lambda: fake)

    result = CliRunner().invoke(cli_mod.cli, ["update", "batch-approve", "does-not-exist"])

    assert result.exit_code != 0
    assert "no existe" in result.output


def test_batch_approve_rejects_unpassed_batch(monkeypatch) -> None:
    batch = _FakeBatchResult(id="batch-2", included=["p1"], excluded=[], passed=False)
    fake = _FakeOrchestrator(_FakeBatcher({"batch-2": batch}))
    monkeypatch.setattr(cli_mod, "get_orchestrator", lambda: fake)

    result = CliRunner().invoke(cli_mod.cli, ["update", "batch-approve", "batch-2"])

    assert result.exit_code != 0
    assert "no pasó validación" in result.output
    assert fake.advance_calls == []


def test_batch_approve_applies_all_in_order(monkeypatch) -> None:
    batch = _FakeBatchResult(id="batch-3", included=["p1", "p2", "p3"], excluded=[], passed=True)
    fake = _FakeOrchestrator(_FakeBatcher({"batch-3": batch}))
    monkeypatch.setattr(cli_mod, "get_orchestrator", lambda: fake)

    result = CliRunner().invoke(cli_mod.cli, ["update", "batch-approve", "batch-3"])

    assert result.exit_code == 0
    assert fake.advance_calls == ["p1", "p2", "p3"]
    assert "aplicado completo" in result.output


def test_batch_approve_stops_on_failure_mid_batch(monkeypatch) -> None:
    batch = _FakeBatchResult(id="batch-4", included=["p1", "p2", "p3"], excluded=[], passed=True)
    fake = _FakeOrchestrator(
        _FakeBatcher({"batch-4": batch}),
        advance_results={"p2": "error: propuesta p2 no existe"},
    )
    monkeypatch.setattr(cli_mod, "get_orchestrator", lambda: fake)

    result = CliRunner().invoke(cli_mod.cli, ["update", "batch-approve", "batch-4"])

    assert result.exit_code != 0
    assert fake.advance_calls == ["p1", "p2"]
    assert "p1" in result.output
    assert "Fallo aplicando p2" in result.output
