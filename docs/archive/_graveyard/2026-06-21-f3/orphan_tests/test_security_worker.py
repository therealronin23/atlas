"""Tests unitarios SecurityWorker (ADR-043/046).

Sin subprocesos reales, sin LayeredIsolationSandbox.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from atlas.core.verify import ArtifactKind, Verdict
from atlas.core.security_worker import SecurityTask, SecurityWorker
from atlas.security.authorization import (
    AuthorizationGrant,
    AuthorizationVerifier,
    Capability,
    HMACSigner,
    SecurityFinding,
    TargetSpec,
    verifier_for,
)

KEY = b"test-key-worker"
ISSUER = "test-issuer"
TARGET = "10.0.0.1"


def _future() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()


def _finding() -> SecurityFinding:
    script = "print('scan')"
    return SecurityFinding(
        id="CVE-WORKER-001",
        target=TARGET,
        capability=Capability.SCAN,
        description="worker test finding",
        poc_script=script,
        evidence_hash=hashlib.sha256(script.encode()).hexdigest(),
    )


def _valid_grant() -> AuthorizationGrant:
    return AuthorizationGrant.issue(
        target=TargetSpec(value=TARGET, kind="host"),
        capability=Capability.SCAN,
        expires_at=_future(),
        issuer=ISSUER,
        signer=HMACSigner(KEY),
    )


@dataclass
class _SandboxResult:
    success: bool
    exit_code: int
    stdout: str = ""
    stderr: str = ""


class FakeSandbox:
    def __init__(self, *, success: bool, exit_code: int) -> None:
        self._result = _SandboxResult(success=success, exit_code=exit_code)
        self.call_count = 0

    def execute(self, code: str, **kwargs) -> _SandboxResult:
        self.call_count += 1
        return self._result


def _worker(sandbox: FakeSandbox) -> tuple[SecurityWorker, list[FakeSandbox]]:
    invoked: list[FakeSandbox] = []

    def factory() -> FakeSandbox:
        invoked.append(sandbox)
        return sandbox

    auth = AuthorizationVerifier(hmac_key=KEY)
    w = SecurityWorker("w-test", auth, factory)
    return w, invoked


# ---------------------------------------------------------------------------
# caso 1: grant válido + sandbox success → Artifact PASS, sandbox invocado
# ---------------------------------------------------------------------------

def test_valid_grant_sandbox_pass() -> None:
    sandbox = FakeSandbox(success=True, exit_code=0)
    worker, invoked = _worker(sandbox)
    task = SecurityTask(finding=_finding(), grant=_valid_grant())

    artifact = worker.produce(task)

    assert artifact.kind == ArtifactKind.SECURITY_FINDING_RESULT
    assert artifact.payload["evidence"]["verdict"] == Verdict.PASS.value
    assert len(invoked) == 1  # sandbox_factory fue invocado


# ---------------------------------------------------------------------------
# caso 2: grant inválido (firma mala) → Artifact FAIL, sandbox no invocado
# ---------------------------------------------------------------------------

def test_invalid_grant_fail_no_sandbox() -> None:
    sandbox = FakeSandbox(success=True, exit_code=0)
    worker, invoked = _worker(sandbox)

    bad_grant = AuthorizationGrant(
        target=TargetSpec(value=TARGET, kind="host"),
        capability=Capability.SCAN,
        expires_at=_future(),
        issuer=ISSUER,
        algo="hmac-sha256",
        signature="deadbeef",
    )
    task = SecurityTask(finding=_finding(), grant=bad_grant)

    artifact = worker.produce(task)

    assert artifact.kind == ArtifactKind.SECURITY_FINDING_RESULT
    evidence = artifact.payload["evidence"]
    assert evidence["verdict"] == Verdict.FAIL.value
    auth_check = next(c for c in evidence["checks"] if c["name"] == "authorization")
    assert auth_check["passed"] is False
    assert len(invoked) == 0  # sandbox no invocado
