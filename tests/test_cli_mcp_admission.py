"""CLI tests for `atlas mcp admit-third-party` / `revoke-third-party`
(ADC-WO-124)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from atlas.interfaces import cli as cli_mod
from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.third_party_admission import load_receipt


class _FakeSentinel:
    def __init__(self, receipts_dir: Path) -> None:
        self.receipts_dir = receipts_dir


class _FakeOrchestrator:
    def __init__(self, tmp_path: Path) -> None:
        self._sentinel = _FakeSentinel(tmp_path / "receipts")
        self._merkle = MerkleLogger(tmp_path / "merkle")


def _fake_executable(tmp_path: Path) -> Path:
    path = tmp_path / "fake-desktop-mcp"
    path.write_bytes(b"#!/bin/sh\necho hi\n")
    path.chmod(0o755)
    return path


def test_admit_third_party_writes_receipt_and_merkle_entry(
    tmp_path: Path, monkeypatch,
) -> None:
    orch = _FakeOrchestrator(tmp_path)
    monkeypatch.setattr(cli_mod, "get_orchestrator", lambda: orch)
    executable = _fake_executable(tmp_path)

    result = CliRunner().invoke(cli_mod.cli, [
        "mcp", "admit-third-party",
        "--server", "fake-desktop-mcp",
        "--executable", str(executable),
        "--package", "fake-desktop-mcp",
        "--version", "0.3.10",
        "--license", "MIT",
        "--dependency", "mcp",
        "--static-scan-verdict", "semgrep p/security-audit: 0 findings",
        "--display", ":99",
        "--admitted-by", "operator:tomas",
        "--yes",
    ])

    assert result.exit_code == 0, result.output
    assert "Admitido" in result.output
    receipt = load_receipt(orch._sentinel.receipts_dir, "fake-desktop-mcp")
    assert receipt is not None
    assert receipt.env_extra == {"DISPLAY": ":99"}
    assert receipt.revoked is False
    merkle_records = [
        r for r in orch._merkle.read_all() if r.task_id == "fake-desktop-mcp"
    ]
    assert any(r.action == "sentinel.receipt_admitted" for r in merkle_records)


def test_admit_third_party_xvfb_only_requires_display(
    tmp_path: Path, monkeypatch,
) -> None:
    orch = _FakeOrchestrator(tmp_path)
    monkeypatch.setattr(cli_mod, "get_orchestrator", lambda: orch)
    executable = _fake_executable(tmp_path)

    result = CliRunner().invoke(cli_mod.cli, [
        "mcp", "admit-third-party",
        "--server", "fake-desktop-mcp", "--executable", str(executable),
        "--package", "fake-desktop-mcp", "--version", "0.3.10",
        "--license", "MIT", "--static-scan-verdict", "clean",
        "--admitted-by", "operator:tomas", "--yes",
    ])

    assert result.exit_code != 0
    assert load_receipt(orch._sentinel.receipts_dir, "fake-desktop-mcp") is None


def test_admit_third_party_without_yes_requires_confirmation(
    tmp_path: Path, monkeypatch,
) -> None:
    orch = _FakeOrchestrator(tmp_path)
    monkeypatch.setattr(cli_mod, "get_orchestrator", lambda: orch)
    executable = _fake_executable(tmp_path)

    result = CliRunner().invoke(cli_mod.cli, [
        "mcp", "admit-third-party",
        "--server", "fake-desktop-mcp", "--executable", str(executable),
        "--package", "fake-desktop-mcp", "--version", "0.3.10",
        "--license", "MIT", "--static-scan-verdict", "clean",
        "--display", ":99", "--admitted-by", "operator:tomas",
    ], input="n\n")

    assert result.exit_code != 0
    assert load_receipt(orch._sentinel.receipts_dir, "fake-desktop-mcp") is None


def test_revoke_third_party_restores_quarantine(tmp_path: Path, monkeypatch) -> None:
    orch = _FakeOrchestrator(tmp_path)
    monkeypatch.setattr(cli_mod, "get_orchestrator", lambda: orch)
    executable = _fake_executable(tmp_path)
    CliRunner().invoke(cli_mod.cli, [
        "mcp", "admit-third-party",
        "--server", "fake-desktop-mcp", "--executable", str(executable),
        "--package", "fake-desktop-mcp", "--version", "0.3.10",
        "--license", "MIT", "--static-scan-verdict", "clean",
        "--display", ":99", "--admitted-by", "operator:tomas", "--yes",
    ])

    result = CliRunner().invoke(cli_mod.cli, [
        "mcp", "revoke-third-party",
        "--server", "fake-desktop-mcp", "--revoked-by", "operator:tomas",
    ])

    assert result.exit_code == 0, result.output
    receipt = load_receipt(orch._sentinel.receipts_dir, "fake-desktop-mcp")
    assert receipt is not None
    assert receipt.revoked is True
