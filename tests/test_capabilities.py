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

    def test_git_push_denied(self, issuer: CapabilityIssuer, workspace: Path) -> None:
        with pytest.raises(CapabilityDenied) as exc:
            issuer.issue_exec("git", args=("push", "origin", "main"), working_dir=workspace / "tmp")
        assert "prohibido" in str(exc.value).lower() or "push" in str(exc.value).lower()

    def test_evaluate_shell_git_push_blocked(self, issuer: CapabilityIssuer) -> None:
        """SEC-01: git push no debe pasar evaluate_shell_command."""
        decision = issuer.profile.evaluate_shell_command("git push origin main")
        assert not decision.allowed
        assert "push" in decision.reason.lower() or "prohibido" in decision.reason.lower()

    def test_git_status_allowed(self, issuer: CapabilityIssuer, workspace: Path) -> None:
        cap = issuer.issue_exec("git", args=("status",), working_dir=workspace / "tmp")
        assert cap.command == "git"
        assert cap.level.value == "auto"

    # SEC-01 `-C` retarget (grounding del repo de código propio) ----------

    def test_git_dash_C_to_inspect_root_allowed(
        self, workspace: Path, tmp_path: Path,
    ) -> None:
        """`git -C <repo>` permitido SOLO si el path == git_inspect_root y el
        subcomando es read-only."""
        repo = tmp_path / "code-repo"
        repo.mkdir()
        perms = workspace / "config" / "permissions.yaml"
        perms.write_text(
            "workspace:\n  auto_write:\n    - tmp/\n  read_extended: []\n"
            "absolute_blocks: []\nsystem_read_allowed: []\n"
            "telegram:\n  authorized_chat_ids: []\nshell_allowlist:\n  - echo\n"
        )
        profile = PermissionProfile(perms, workspace, git_inspect_root=repo)
        d = profile.evaluate_shell_command(f"git -C {repo} log --oneline -10")
        assert d.allowed, d.reason

    def test_git_dash_C_arbitrary_path_blocked(
        self, workspace: Path, tmp_path: Path,
    ) -> None:
        """`git -C <otra-ruta>` rechazado aunque el subcomando sea read-only."""
        repo = tmp_path / "code-repo"
        other = tmp_path / "elsewhere"
        repo.mkdir()
        other.mkdir()
        perms = workspace / "config" / "permissions.yaml"
        perms.write_text(
            "workspace:\n  auto_write:\n    - tmp/\n  read_extended: []\n"
            "absolute_blocks: []\nsystem_read_allowed: []\n"
            "telegram:\n  authorized_chat_ids: []\nshell_allowlist:\n  - echo\n"
        )
        profile = PermissionProfile(perms, workspace, git_inspect_root=repo)
        d = profile.evaluate_shell_command(f"git -C {other} log")
        assert not d.allowed
        assert "repo de atlas" in d.reason.lower()

    def test_git_dash_C_without_inspect_root_blocked(
        self, permission_profile: PermissionProfile, tmp_path: Path,
    ) -> None:
        """Sin git_inspect_root configurado, ningún `-C` pasa."""
        d = permission_profile.evaluate_shell_command(f"git -C {tmp_path} log")
        assert not d.allowed

    def test_git_dash_C_apply_blocked(
        self, workspace: Path, tmp_path: Path,
    ) -> None:
        """`git -C <repo> apply` rechazado: -C nunca para subcomandos mutantes."""
        repo = tmp_path / "code-repo"
        repo.mkdir()
        perms = workspace / "config" / "permissions.yaml"
        perms.write_text(
            "workspace:\n  auto_write:\n    - tmp/\n  read_extended: []\n"
            "absolute_blocks: []\nsystem_read_allowed: []\n"
            "telegram:\n  authorized_chat_ids: []\nshell_allowlist:\n  - echo\n"
        )
        profile = PermissionProfile(perms, workspace, git_inspect_root=repo)
        d = profile.evaluate_shell_command(f"git -C {repo} apply patch.diff")
        assert not d.allowed

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
        cap = issuer.issue_write(path)
        n = executor.execute_write(cap, b"abc")
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
        issuer.profile.mark_confirmed(f"exec:echo hola")
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
        issuer.profile.mark_confirmed("exec:echo")
        with pytest.raises(ExecutorError) as exc:
            executor.execute_exec(cap)
        msg = str(exc.value).lower()
        assert "ast guard" in msg or "generated code policy" in msg

    def test_confirm_write_blocked_until_marked(
        self, executor: AtlasExecutor, issuer: CapabilityIssuer, workspace: Path
    ) -> None:
        cap = issuer.issue_write(workspace / "projects" / "x.py")
        with pytest.raises(ExecutorError) as exc:
            executor.execute_write(cap, b"x")
        assert "confirmacion" in str(exc.value).lower()
        issuer.profile.mark_confirmed(f"write:{cap.path}")
        assert executor.execute_write(cap, b"x") == 1

    def test_clearance_allows_write_after_task_approval(
        self, executor: AtlasExecutor, issuer: CapabilityIssuer, workspace: Path
    ) -> None:
        cap = issuer.issue_write(
            workspace / "projects" / "y.py",
            clearance="task:abc-123",
        )
        with pytest.raises(ExecutorError):
            executor.execute_write(cap, b"y")
        issuer.profile.mark_confirmed("task:abc-123")
        assert executor.execute_write(cap, b"y") == 1


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


# ===========================================================================
# SEC-2: re-validacion defensiva en el sink
# ===========================================================================


class TestSinkSSRFRevalidation:
    """NetworkCapability construida directamente (sin issuer) con URL SSRF
    debe ser bloqueada por el chequeo defensivo dentro de execute_network."""

    def test_link_local_metadata_blocked_at_sink(
        self, merkle: MerkleLogger, sandbox: LayeredIsolationSandbox, workspace: Path
    ) -> None:
        """169.254.169.254 (AWS metadata) bloqueada aunque la cap se construya
        directamente eludiendo el issuer."""
        # La capability se construye a mano: NO pasa por CapabilityIssuer.
        cap = NetworkCapability(
            url="http://169.254.169.254/latest/meta-data/",
            method="GET",
            domain="169.254.169.254",
        )
        perms_file = workspace / "config" / "permissions.yaml"
        perms_file.write_text(
            "workspace:\n  auto_write:\n    - tmp/\n  confirm_write: []\n"
            "  read_only: []\n  read_extended: []\n"
            "absolute_blocks: []\nsystem_read_allowed: []\n"
            "telegram:\n  authorized_chat_ids: []\n"
            "shell_allowlist: []\n"
        )
        profile = PermissionProfile(perms_file, workspace)
        # El issuer propio usa SSRFBridge con blocklist por defecto.
        issuer_local = CapabilityIssuer(profile, SSRFBridge())
        exec_local = AtlasExecutor(issuer_local, merkle, sandbox)

        with pytest.raises(ExecutorError, match="SSRF check bloqueado"):
            exec_local.execute_network(cap)


class TestSinkExecRevalidation:
    """ExecCapability construida directamente con comando fuera del perfil
    debe ser rechazada en execute_exec por la re-validacion del sink."""

    def test_out_of_profile_command_blocked_at_sink(
        self, merkle: MerkleLogger, sandbox: LayeredIsolationSandbox, workspace: Path
    ) -> None:
        """rm no esta en la shell_allowlist del fixture; una cap construida
        a mano con ese comando debe fallar en la re-validacion."""
        # permissions.yaml solo permite echo/cat/ls (como en el fixture base)
        perms_file = workspace / "config" / "permissions.yaml"
        perms_file.write_text(
            "workspace:\n  auto_write:\n    - tmp/\n  confirm_write: []\n"
            "  read_only: []\n  read_extended: []\n"
            "absolute_blocks: []\nsystem_read_allowed: []\n"
            "telegram:\n  authorized_chat_ids: []\n"
            "shell_allowlist:\n  - echo\n  - ls\n"
        )
        profile = PermissionProfile(perms_file, workspace)
        issuer_local = CapabilityIssuer(profile, SSRFBridge())
        exec_local = AtlasExecutor(issuer_local, merkle, sandbox)

        # Construida directamente — bypasea issue_exec y su validacion
        cap = ExecCapability(
            command="rm",
            args=("-rf", "/tmp/evil"),
            working_dir=workspace / "tmp",
            timeout_s=5,
            level=PermissionLevel.AUTO,
        )
        with pytest.raises(ExecutorError, match="re-validacion del sink"):
            exec_local.execute_exec(cap)
