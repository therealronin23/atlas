"""
Tests del modulo de capabilities (ADR-020).
Valida emision de tokens via CapabilityIssuer y comportamiento del AtlasExecutor.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from atlas.governance.permission_profile import PermissionLevel, PermissionProfile
from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.ast_guard import ASTGuard
from atlas.security.capabilities import (
    CapabilityDenied,
    CapabilityIssuer,
    ExecCapability,
    NetworkCapability,
    ReadCapability,
    WriteCapability,
)
from atlas.security.executor import AtlasExecutor, ExecutorError, NetworkResponse
from atlas.security.sandbox import LayeredIsolationSandbox, OperationalMode, SandboxResult
from atlas.security.ssrf_bridge import SSRFBridge


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "atlas-test"
    (ws / "tmp").mkdir(parents=True)
    (ws / "projects").mkdir()
    (ws / "memory").mkdir()
    (ws / "config").mkdir()
    return ws


@pytest.fixture
def permission_profile(workspace: Path) -> PermissionProfile:
    perms_file = workspace / "config" / "permissions.yaml"
    perms_file.write_text(
        "workspace:\n"
        "  auto_write:\n    - tmp/\n"
        "  confirm_write:\n    - projects/\n    - memory/\n"
        "  read_only:\n    - config/governance.json\n"
        "  read_extended: []\n"
        "absolute_blocks:\n  - ~/.ssh/\n  - /etc/\n  - /root/\n"
        "system_read_allowed:\n  - /sys/class/hwmon/\n"
        "telegram:\n  authorized_chat_ids: []\n"
        "shell_allowlist:\n  - echo\n  - cat\n  - ls\n"
    )
    return PermissionProfile(perms_file, workspace)


@pytest.fixture
def issuer(permission_profile: PermissionProfile) -> CapabilityIssuer:
    return CapabilityIssuer(permission_profile, SSRFBridge())


@pytest.fixture
def merkle(workspace: Path) -> MerkleLogger:
    log_dir = workspace / "memory" / "merkle"
    log_dir.mkdir(parents=True, exist_ok=True)
    return MerkleLogger(log_dir)


@pytest.fixture
def sandbox(workspace: Path) -> LayeredIsolationSandbox:
    return LayeredIsolationSandbox(workspace)


@pytest.fixture
def executor(
    issuer: CapabilityIssuer,
    merkle: MerkleLogger,
    sandbox: LayeredIsolationSandbox,
) -> AtlasExecutor:
    return AtlasExecutor(issuer, merkle, sandbox, ASTGuard())


# ===========================================================================
# CapabilityIssuer — validacion en emision
# ===========================================================================


class TestIssueRead:

    def test_workspace_path_ok(self, issuer: CapabilityIssuer, workspace: Path) -> None:
        cap = issuer.issue_read(workspace / "projects" / "test.py")
        assert isinstance(cap, ReadCapability)
        assert cap.path == (workspace / "projects" / "test.py").resolve()
        assert cap.level == PermissionLevel.AUTO

    def test_blocked_path_denied(self, issuer: CapabilityIssuer) -> None:
        with pytest.raises(CapabilityDenied) as exc:
            issuer.issue_read("/etc/passwd")
        assert "bloqueo absoluto" in str(exc.value).lower()

    def test_outside_workspace_denied(self, issuer: CapabilityIssuer, tmp_path: Path) -> None:
        outside = tmp_path / "elsewhere" / "file.txt"
        outside.parent.mkdir(parents=True)
        outside.write_text("x")
        with pytest.raises(CapabilityDenied):
            issuer.issue_read(outside)

    def test_zero_max_bytes_denied(self, issuer: CapabilityIssuer, workspace: Path) -> None:
        with pytest.raises(CapabilityDenied):
            issuer.issue_read(workspace / "tmp" / "x.txt", max_bytes=0)


class TestIssueWrite:

    def test_tmp_write_auto(self, issuer: CapabilityIssuer, workspace: Path) -> None:
        cap = issuer.issue_write(workspace / "tmp" / "out.txt")
        assert cap.level == PermissionLevel.AUTO

    def test_projects_write_confirm(self, issuer: CapabilityIssuer, workspace: Path) -> None:
        cap = issuer.issue_write(workspace / "projects" / "code.py")
        assert cap.level == PermissionLevel.CONFIRM

    def test_governance_write_blocked(
        self, issuer: CapabilityIssuer, workspace: Path
    ) -> None:
        with pytest.raises(CapabilityDenied) as exc:
            issuer.issue_write(workspace / "config" / "governance.json")
        assert "inmutable" in str(exc.value).lower()

    def test_etc_write_blocked(self, issuer: CapabilityIssuer) -> None:
        with pytest.raises(CapabilityDenied):
            issuer.issue_write("/etc/hosts")


class TestIssueNetwork:

    def test_allowlisted_domain_ok(self, issuer: CapabilityIssuer) -> None:
        cap = issuer.issue_network("https://api.groq.com/v1/chat/completions")
        assert cap.domain == "api.groq.com"
        assert cap.method == "GET"

    def test_localhost_denied(self, issuer: CapabilityIssuer) -> None:
        with pytest.raises(CapabilityDenied) as exc:
            issuer.issue_network("http://localhost:8080/x")
        assert "ssrf" in str(exc.value).lower() or "bloqueado" in str(exc.value).lower()

    def test_private_ip_denied(self, issuer: CapabilityIssuer) -> None:
        with pytest.raises(CapabilityDenied):
            issuer.issue_network("http://192.168.1.1/admin")

    def test_random_domain_denied(self, issuer: CapabilityIssuer) -> None:
        with pytest.raises(CapabilityDenied):
            issuer.issue_network("https://evil.example.com/x")


class TestIssueExec:

    def test_allowlisted_command_ok(
        self, issuer: CapabilityIssuer, workspace: Path
    ) -> None:
        cap = issuer.issue_exec("echo", args=("hola",), working_dir=workspace / "tmp")
        assert cap.command == "echo"
        assert cap.args == ("hola",)

    def test_not_allowlisted_denied(self, issuer: CapabilityIssuer) -> None:
        with pytest.raises(CapabilityDenied):
            issuer.issue_exec("rm")

    def test_timeout_out_of_range_denied(
        self, issuer: CapabilityIssuer, workspace: Path
    ) -> None:
        with pytest.raises(CapabilityDenied):
            issuer.issue_exec("echo", working_dir=workspace / "tmp", timeout_s=0)
        with pytest.raises(CapabilityDenied):
            issuer.issue_exec("echo", working_dir=workspace / "tmp", timeout_s=9999)

    def test_working_dir_outside_workspace_denied(
        self, issuer: CapabilityIssuer
    ) -> None:
        with pytest.raises(CapabilityDenied):
            issuer.issue_exec("echo", working_dir="/etc")


class TestImmutability:

    def test_read_capability_frozen(self, issuer: CapabilityIssuer, workspace: Path) -> None:
        cap = issuer.issue_read(workspace / "tmp" / "x.txt")
        with pytest.raises(ValidationError):
            cap.max_bytes = 999  # type: ignore[misc]

    def test_network_capability_frozen(self, issuer: CapabilityIssuer) -> None:
        cap = issuer.issue_network("https://api.groq.com/x")
        with pytest.raises(ValidationError):
            cap.url = "https://other.com"  # type: ignore[misc]


# ===========================================================================
# AtlasExecutor — IO real con tokens
# ===========================================================================


class TestExecuteRead:

    def test_reads_file(
        self, executor: AtlasExecutor, issuer: CapabilityIssuer, workspace: Path
    ) -> None:
        f = workspace / "tmp" / "data.txt"
        f.write_text("hola mundo")
        cap = issuer.issue_read(f)
        out = executor.execute_read(cap)
        assert out == b"hola mundo"

    def test_truncates_at_max_bytes(
        self, executor: AtlasExecutor, issuer: CapabilityIssuer, workspace: Path
    ) -> None:
        f = workspace / "tmp" / "big.bin"
        f.write_bytes(b"A" * 1000)
        cap = issuer.issue_read(f, max_bytes=10)
        out = executor.execute_read(cap)
        assert len(out) == 10
        assert out == b"A" * 10

    def test_nonexistent_path_errors(
        self, executor: AtlasExecutor, issuer: CapabilityIssuer, workspace: Path
    ) -> None:
        # La capability se emite OK (path es validable aunque no exista).
        # El error sucede al ejecutar.
        cap = issuer.issue_read(workspace / "tmp" / "ghost.txt")
        with pytest.raises(ExecutorError):
            executor.execute_read(cap)

    def test_logs_to_merkle(
        self,
        executor: AtlasExecutor,
        issuer: CapabilityIssuer,
        workspace: Path,
        merkle: MerkleLogger,
    ) -> None:
        f = workspace / "tmp" / "audit.txt"
        f.write_text("x")
        executor.execute_read(issuer.issue_read(f))
        ok, _ = merkle.verify_chain()
        assert ok


class TestExecuteWrite:

    def test_writes_file(
        self, executor: AtlasExecutor, issuer: CapabilityIssuer, workspace: Path
    ) -> None:
        path = workspace / "tmp" / "out.bin"
        n = executor.execute_write(issuer.issue_write(path), b"abc")
        assert n == 3
        assert path.read_bytes() == b"abc"

    def test_rejects_data_over_max_bytes(
        self, executor: AtlasExecutor, issuer: CapabilityIssuer, workspace: Path
    ) -> None:
        cap = issuer.issue_write(workspace / "tmp" / "x.bin", max_bytes=5)
        with pytest.raises(ExecutorError):
            executor.execute_write(cap, b"123456")

    def test_append_mode(
        self, executor: AtlasExecutor, issuer: CapabilityIssuer, workspace: Path
    ) -> None:
        path = workspace / "tmp" / "log.txt"
        path.write_text("a")
        cap = issuer.issue_write(path, append=True)
        executor.execute_write(cap, b"b")
        assert path.read_bytes() == b"ab"


class TestExecuteNetwork:

    def test_get_request(
        self, executor: AtlasExecutor, issuer: CapabilityIssuer
    ) -> None:
        cap = issuer.issue_network("https://api.groq.com/ping")
        fake_resp = MagicMock()
        fake_resp.read.return_value = b'{"ok":true}'
        fake_resp.headers = {"Content-Type": "application/json"}
        fake_resp.getcode.return_value = 200
        fake_resp.__enter__.return_value = fake_resp
        fake_resp.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=fake_resp):
            result = executor.execute_network(cap)

        assert isinstance(result, NetworkResponse)
        assert result.status_code == 200
        assert result.body == b'{"ok":true}'

    def test_truncates_oversized_response(
        self, executor: AtlasExecutor, issuer: CapabilityIssuer
    ) -> None:
        cap = issuer.issue_network("https://api.groq.com/big", max_response_bytes=10)
        fake_resp = MagicMock()
        fake_resp.read.return_value = b"A" * 20
        fake_resp.headers = {}
        fake_resp.getcode.return_value = 200
        fake_resp.__enter__.return_value = fake_resp
        fake_resp.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=fake_resp):
            result = executor.execute_network(cap)

        assert result.truncated is True
        assert len(result.body) == 10


class TestExecuteExec:

    def test_echo_runs(
        self, executor: AtlasExecutor, issuer: CapabilityIssuer, workspace: Path
    ) -> None:
        cap = issuer.issue_exec(
            "echo", args=("hola",), working_dir=workspace / "tmp", timeout_s=5,
        )
        result = executor.execute_exec(cap)
        assert isinstance(result, SandboxResult)
        assert result.success is True
        assert "hola" in result.stdout

    def test_ast_guard_blocks_dangerous_code(
        self, executor: AtlasExecutor, issuer: CapabilityIssuer, workspace: Path
    ) -> None:
        # Capability con codigo malicioso (eval). AST Guard debe rechazarlo.
        cap = issuer.issue_exec(
            "echo",  # comando "host" valido segun allowlist
            args=(),
            working_dir=workspace / "tmp",
            code="eval('1+1')",
        )
        with pytest.raises(ExecutorError) as exc:
            executor.execute_exec(cap)
        assert "ast guard" in str(exc.value).lower()


class TestExecutorTypeGuards:

    def test_execute_read_rejects_wrong_token(
        self, executor: AtlasExecutor, issuer: CapabilityIssuer, workspace: Path
    ) -> None:
        write_cap = issuer.issue_write(workspace / "tmp" / "x")
        with pytest.raises(ExecutorError):
            executor.execute_read(write_cap)  # type: ignore[arg-type]

    def test_execute_write_rejects_non_bytes(
        self, executor: AtlasExecutor, issuer: CapabilityIssuer, workspace: Path
    ) -> None:
        cap = issuer.issue_write(workspace / "tmp" / "x")
        with pytest.raises(ExecutorError):
            executor.execute_write(cap, "string en vez de bytes")  # type: ignore[arg-type]
