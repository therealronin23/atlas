"""CLI: atlas connections credential-reference / test --mode=real (2026-07-24).

Cableado real de AuthBroker/ConnectorRegistry vía CLI, simétrico al endpoint
HTTP de product_routes.py."""
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from atlas.interfaces import cli as cli_mod


@pytest.fixture(autouse=True)
def _isolated_atlas_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas_home"))


def test_credential_reference_cli_creates_and_lists_reference(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli_mod.cli,
        ["connections", "credential-reference", "gmail", "MY_TOKEN", "--scope", "email.read"],
    )
    assert result.exit_code == 0, result.output
    assert "env:MY_TOKEN" in result.output

    from atlas.fabric.auth_broker import AuthBroker

    refs = AuthBroker().list_references()
    assert refs[0]["provider"] == "gmail"
    assert refs[0]["reference"] == "env:MY_TOKEN"


def test_credential_reference_cli_rejects_secret_value() -> None:
    result = CliRunner().invoke(
        cli_mod.cli,
        ["connections", "credential-reference", "gmail", "sk-abcdefghijklmnopqrstuvwx"],
    )
    assert result.exit_code == 1


def test_connections_test_cli_real_mode_blocked_without_reference() -> None:
    result = CliRunner().invoke(cli_mod.cli, ["connections", "test", "gmail", "--mode", "real"])
    assert result.exit_code == 0
    assert "BLOCKED_BY_MISSING_DEPENDENCY" in result.output
