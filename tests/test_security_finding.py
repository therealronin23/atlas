"""Tests ADR-043 Fase 1 — SecurityFinding + PoCReproductionVerifier.

Sin subprocesos reales, sin LayeredIsolationSandbox.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from atlas.core.verify import CostTier, Verdict
from atlas.security.authorization import (
    AuthorizationGrant,
    AuthorizationVerifier,
    Capability,
    HMACSigner,
    SecurityFinding,
    PoCReproductionVerifier,
    TargetSpec,
)

KEY = b"test-key-finding"
ISSUER = "test-issuer"
TARGET = "192.168.10.1"


def _future() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()


def _past() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()


def _finding() -> SecurityFinding:
    script = "print('poc')"
    import hashlib
    return SecurityFinding(
        id="CVE-TEST-001",
        target=TARGET,
        capability=Capability.EXPLOIT_POC,
        description="test finding",
        poc_script=script,
        evidence_hash=hashlib.sha256(script.encode()).hexdigest(),
    )


def _valid_grant(*, key: bytes = KEY) -> AuthorizationGrant:
    return AuthorizationGrant.issue(
        target=TargetSpec(value=TARGET, kind="host"),
        capability=Capability.EXPLOIT_POC,
        expires_at=_future(),
        issuer=ISSUER,
        signer=HMACSigner(key),
    )


def _verifier(key: bytes = KEY) -> AuthorizationVerifier:
    return AuthorizationVerifier(hmac_key=key)


@dataclass
class _SandboxResult:
    success: bool
    exit_code: int
    stdout: str = ""
    stderr: str = ""


class FakeSandbox:
    def __init__(self, *, success: bool, exit_code: int, stdout: str = "", stderr: str = "") -> None:
        self._result = _SandboxResult(success=success, exit_code=exit_code, stdout=stdout, stderr=stderr)
        self.call_count = 0

    def execute(self, code: str, **kwargs) -> _SandboxResult:
        self.call_count += 1
        return self._result


# ---------------------------------------------------------------------------
# caso 1: firma inválida → FAIL, sandbox no invocado
# ---------------------------------------------------------------------------

def test_invalid_signature_denied_no_sandbox() -> None:
    sandbox = FakeSandbox(success=True, exit_code=0)
    call_count_holder: list[int] = []

    def factory() -> FakeSandbox:
        call_count_holder.append(1)
        return sandbox

    bad_grant = AuthorizationGrant(
        target=TargetSpec(value=TARGET, kind="host"),
        capability=Capability.EXPLOIT_POC,
        expires_at=_future(),
        issuer=ISSUER,
        algo="hmac-sha256",
        signature="deadbeef",
    )
    verifier = PoCReproductionVerifier(_verifier(), factory)
    evidence = verifier.verify(_finding(), bad_grant)

    assert evidence.verdict is Verdict.FAIL
    assert call_count_holder == []  # sandbox_factory nunca llamado


# ---------------------------------------------------------------------------
# caso 2: grant caducado → FAIL, sandbox no invocado
# ---------------------------------------------------------------------------

def test_expired_grant_denied_no_sandbox() -> None:
    call_count_holder: list[int] = []

    def factory() -> FakeSandbox:
        call_count_holder.append(1)
        return FakeSandbox(success=True, exit_code=0)

    expired_grant = AuthorizationGrant.issue(
        target=TargetSpec(value=TARGET, kind="host"),
        capability=Capability.EXPLOIT_POC,
        expires_at=_past(),
        issuer=ISSUER,
        signer=HMACSigner(KEY),
    )
    verifier = PoCReproductionVerifier(_verifier(), factory)
    evidence = verifier.verify(_finding(), expired_grant)

    assert evidence.verdict is Verdict.FAIL
    assert call_count_holder == []


# ---------------------------------------------------------------------------
# caso 3: grant válido + sandbox success=True, exit_code=0 → PASS
# ---------------------------------------------------------------------------

def test_valid_grant_sandbox_success_pass() -> None:
    sandbox = FakeSandbox(success=True, exit_code=0, stdout="exploit ok")
    verifier = PoCReproductionVerifier(_verifier(), lambda: sandbox)
    evidence = verifier.verify(_finding(), _valid_grant())

    assert evidence.verdict is Verdict.PASS
    assert sandbox.call_count == 1
    assert evidence.total_cost == CostTier.SANDBOX


# ---------------------------------------------------------------------------
# caso 4: grant válido + sandbox success=False → FAIL
# ---------------------------------------------------------------------------

def test_valid_grant_sandbox_failure_fail() -> None:
    sandbox = FakeSandbox(success=False, exit_code=1, stderr="exploit crashed")
    verifier = PoCReproductionVerifier(_verifier(), lambda: sandbox)
    evidence = verifier.verify(_finding(), _valid_grant())

    assert evidence.verdict is Verdict.FAIL
    assert sandbox.call_count == 1
