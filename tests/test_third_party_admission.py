"""ADC-WO-124 — receipt de admisión gobernada para ejecutables MCP de
terceros. `SentinelGate` sigue vetando cualquier third-party sin receipt
(ver test_sentinel_gate.py); este módulo cubre el ciclo de vida del
receipt en sí: admitir, cargar, revocar — siempre con hash recomputado
del artefacto real, nunca confiado de un campo declarado."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.security.third_party_admission import (
    ReceiptIntegrityError,
    ThirdPartyReceipt,
    admit_third_party,
    load_receipt,
    revoke_third_party,
)


def _fake_executable(tmp_path: Path, content: bytes = b"#!/bin/sh\necho hi\n") -> Path:
    path = tmp_path / "fake-mcp-bin"
    path.write_bytes(content)
    path.chmod(0o755)
    return path


class _RecordingMerkle:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def log(self, **kwargs: object) -> object:
        self.calls.append(kwargs)

        class _Record:
            id = f"rec-{len(self.calls)}"

        return _Record()


def test_admit_computes_hash_from_the_real_file_not_a_declared_value(
    tmp_path: Path,
) -> None:
    executable = _fake_executable(tmp_path)
    merkle = _RecordingMerkle()
    receipts_dir = tmp_path / "receipts"

    receipt = admit_third_party(
        receipts_dir,
        merkle.log,
        server="computer-control-mcp",
        cmd=[str(executable)],
        cwd=None,
        env_extra={"DISPLAY": ":99"},
        env_passthrough=[],
        executable_path=executable,
        package="computer-control-mcp",
        version="0.3.10",
        license_name="MIT",
        dependency_inventory=["mcp", "pyautogui"],
        static_scan_verdict="semgrep p/security-audit: 0 findings",
        xvfb_only=True,
        admitted_by="operator:tomas",
    )

    import hashlib
    expected = hashlib.sha256(executable.read_bytes()).hexdigest()
    assert receipt.executable_sha256 == expected
    assert receipt.revoked is False
    assert merkle.calls[0]["action"] == "sentinel.receipt_admitted"
    assert merkle.calls[0]["task_id"] == "computer-control-mcp"


def test_admit_rejects_missing_executable(tmp_path: Path) -> None:
    merkle = _RecordingMerkle()
    with pytest.raises(FileNotFoundError):
        admit_third_party(
            tmp_path / "receipts",
            merkle.log,
            server="ghost-mcp",
            cmd=["/nowhere/ghost"],
            cwd=None,
            env_extra={},
            env_passthrough=[],
            executable_path=tmp_path / "nowhere",
            package="ghost", version="0.0.1", license_name="MIT",
            dependency_inventory=[], static_scan_verdict="n/a",
            xvfb_only=False, admitted_by="operator:tomas",
        )


def test_load_receipt_roundtrips(tmp_path: Path) -> None:
    executable = _fake_executable(tmp_path)
    merkle = _RecordingMerkle()
    receipts_dir = tmp_path / "receipts"
    admit_third_party(
        receipts_dir, merkle.log,
        server="computer-control-mcp", cmd=[str(executable)], cwd=None,
        env_extra={"DISPLAY": ":99"}, env_passthrough=[],
        executable_path=executable, package="computer-control-mcp",
        version="0.3.10", license_name="MIT",
        dependency_inventory=["mcp"], static_scan_verdict="clean",
        xvfb_only=True, admitted_by="operator:tomas",
    )

    loaded = load_receipt(receipts_dir, "computer-control-mcp")
    assert isinstance(loaded, ThirdPartyReceipt)
    assert loaded.cmd == (str(executable),)
    assert loaded.env_extra == {"DISPLAY": ":99"}
    assert loaded.revoked is False


def test_load_receipt_missing_returns_none(tmp_path: Path) -> None:
    assert load_receipt(tmp_path / "receipts", "nobody-admitted-this") is None


def test_load_receipt_corrupt_json_fails_closed(tmp_path: Path) -> None:
    receipts_dir = tmp_path / "receipts"
    receipts_dir.mkdir(parents=True)
    (receipts_dir / "computer-control-mcp.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ReceiptIntegrityError):
        load_receipt(receipts_dir, "computer-control-mcp")


def test_revoke_flips_flag_and_is_immediately_visible(tmp_path: Path) -> None:
    executable = _fake_executable(tmp_path)
    merkle = _RecordingMerkle()
    receipts_dir = tmp_path / "receipts"
    admit_third_party(
        receipts_dir, merkle.log,
        server="computer-control-mcp", cmd=[str(executable)], cwd=None,
        env_extra={"DISPLAY": ":99"}, env_passthrough=[],
        executable_path=executable, package="computer-control-mcp",
        version="0.3.10", license_name="MIT",
        dependency_inventory=["mcp"], static_scan_verdict="clean",
        xvfb_only=True, admitted_by="operator:tomas",
    )

    revoked = revoke_third_party(
        receipts_dir, merkle.log, server="computer-control-mcp",
        revoked_by="operator:tomas",
    )
    assert revoked.revoked is True
    assert revoked.revoked_by == "operator:tomas"

    reloaded = load_receipt(receipts_dir, "computer-control-mcp")
    assert reloaded is not None
    assert reloaded.revoked is True
    assert merkle.calls[-1]["action"] == "sentinel.receipt_revoked"


def test_revoke_unknown_server_raises(tmp_path: Path) -> None:
    merkle = _RecordingMerkle()
    with pytest.raises(FileNotFoundError):
        revoke_third_party(
            tmp_path / "receipts", merkle.log,
            server="nobody-admitted-this", revoked_by="operator:tomas",
        )
