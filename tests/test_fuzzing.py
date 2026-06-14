"""Tests para src/atlas/security/fuzzing.py (ADR — Familia mutaciones deterministas)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from atlas.core.verify import CostTier, Evidence, Verdict
from atlas.security.authorization import (
    AuthorizationGrant,
    AuthorizationVerifier,
    Capability,
    HMACSigner,
    PoCReproductionVerifier,
    SecurityFinding,
    TargetSpec,
)
from atlas.security.fuzzing import (
    FuzzReport,
    FuzzResult,
    _select_grant,
    fuzz_script,
    run_fuzz_harness,
)

# ---------------------------------------------------------------------------
# Fixtures compartidos
# ---------------------------------------------------------------------------

_KEY = b"test-fuzz-key"
_TARGET = "10.0.0.1"
_ISSUER = "test-issuer"


def _future() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()


def _base_finding(script: str = "exploit(port=80, verbose=True)") -> SecurityFinding:
    return SecurityFinding(
        id="CVE-FUZZ-001",
        target=_TARGET,
        capability=Capability.FUZZ,
        description="base finding for fuzzing",
        poc_script=script,
        evidence_hash=hashlib.sha256(script.encode()).hexdigest(),
    )


def _valid_grant(
    *,
    target: str = _TARGET,
    kind: str = "host",
    capability: Capability = Capability.FUZZ,
    key: bytes = _KEY,
) -> AuthorizationGrant:
    return AuthorizationGrant.issue(
        target=TargetSpec(value=target, kind=kind),
        capability=capability,
        expires_at=_future(),
        issuer=_ISSUER,
        signer=HMACSigner(key),
    )


def _deny_verifier() -> PoCReproductionVerifier:
    """Verifier cuya auth siempre deniega (sin clave válida)."""
    auth = AuthorizationVerifier(hmac_key=b"wrong-key")
    sandbox = MagicMock()
    return PoCReproductionVerifier(auth_verifier=auth, sandbox_factory=lambda: sandbox)


def _pass_verifier() -> PoCReproductionVerifier:
    """Verifier que autentica correctamente y sandbox siempre tiene éxito."""
    auth = AuthorizationVerifier(hmac_key=_KEY)
    sandbox = MagicMock()
    sandbox.execute.return_value = MagicMock(success=True, exit_code=0, stdout="ok", stderr="")
    return PoCReproductionVerifier(auth_verifier=auth, sandbox_factory=lambda: sandbox)


class TestDeterminism:
    def test_same_input_same_output(self) -> None:
        script = "run_exploit(target='192.168.1.1', port=22, verbose=True)"
        assert fuzz_script(script) == fuzz_script(script)

    def test_empty_script_no_crash(self) -> None:
        result = fuzz_script("")
        assert isinstance(result, list)

    def test_payloads_are_strings(self) -> None:
        script = "connect(host='localhost', timeout=30)"
        for p in fuzz_script(script):
            assert isinstance(p, str)


class TestFamily1BoolNumeric:
    def test_flips_true_to_false(self) -> None:
        script = "attack(stealth=True)"
        payloads = fuzz_script(script)
        assert any("False" in p for p in payloads)

    def test_flips_false_to_true(self) -> None:
        script = "attack(stealth=False)"
        payloads = fuzz_script(script)
        assert any("True" in p for p in payloads)

    def test_replaces_zero(self) -> None:
        script = "retry(count=0)"
        payloads = fuzz_script(script)
        # 0 debe mutar a 1 o -1
        assert any(p != script and ("1" in p or "-1" in p) for p in payloads)

    def test_replaces_large_int(self) -> None:
        script = "sleep(99)"
        payloads = fuzz_script(script)
        assert any("2147483647" in p or "-2147483648" in p or p.count("0") > script.count("0") for p in payloads)


class TestFamily2SpecialChars:
    def test_null_byte_injected(self) -> None:
        script = "connect(host='target')"
        payloads = fuzz_script(script)
        assert any("\x00" in p for p in payloads)

    def test_single_quote_injected(self) -> None:
        script = "query(sql='SELECT 1')"
        payloads = fuzz_script(script)
        # comilla simple extra debe aparecer
        assert any(p.count("'") > script.count("'") for p in payloads)

    def test_path_traversal_injected(self) -> None:
        script = "open(path='/etc/hosts')"
        payloads = fuzz_script(script)
        assert any("../" in p for p in payloads)


class TestFamily3BoundaryValues:
    def test_empty_string_boundary(self) -> None:
        script = 'login(user="admin", pass="secret")'
        payloads = fuzz_script(script)
        assert any('""' in p for p in payloads)

    def test_int_max_boundary(self) -> None:
        script = "allocate(size=64)"
        payloads = fuzz_script(script)
        assert any("2147483647" in p for p in payloads)


class TestLimits:
    def test_max_payloads(self) -> None:
        # Script con muchos patrones mutables — no debe superar el límite
        script = (
            "run(True, False, 0, 1, target='host', port=22, "
            "verbose=True, retry=False, timeout=30)"
        )
        payloads = fuzz_script(script)
        assert len(payloads) <= 20

    def test_no_original_in_payloads(self) -> None:
        script = "exploit(target='127.0.0.1', port=8080)"
        payloads = fuzz_script(script)
        assert script not in payloads

    def test_no_duplicates(self) -> None:
        script = "run(True, port=80)"
        payloads = fuzz_script(script)
        assert len(payloads) == len(set(payloads))


# ---------------------------------------------------------------------------
# FuzzResult + FuzzReport dataclasses
# ---------------------------------------------------------------------------


class TestFuzzResultDataclass:
    def test_frozen(self) -> None:
        finding = _base_finding()
        evidence = Evidence(verdict=Verdict.FAIL)
        result = FuzzResult(finding=finding, evidence=evidence)
        with pytest.raises((AttributeError, TypeError)):
            result.finding = finding  # type: ignore[misc]

    def test_fields(self) -> None:
        finding = _base_finding()
        evidence = Evidence(verdict=Verdict.PASS)
        result = FuzzResult(finding=finding, evidence=evidence)
        assert result.finding is finding
        assert result.evidence is evidence


class TestFuzzReportDataclass:
    def test_frozen(self) -> None:
        report = FuzzReport(payloads_generated=3, reproduced_count=1, results=())
        with pytest.raises((AttributeError, TypeError)):
            report.payloads_generated = 0  # type: ignore[misc]

    def test_fields(self) -> None:
        report = FuzzReport(payloads_generated=5, reproduced_count=2, results=())
        assert report.payloads_generated == 5
        assert report.reproduced_count == 2
        assert report.results == ()


# ---------------------------------------------------------------------------
# _select_grant helper
# ---------------------------------------------------------------------------


class TestSelectGrant:
    def test_returns_matching_grant(self) -> None:
        grant = _valid_grant()
        result = _select_grant([grant], _base_finding())
        assert result is grant

    def test_returns_none_when_no_match(self) -> None:
        grant = _valid_grant(target="192.168.99.1")
        result = _select_grant([grant], _base_finding())
        assert result is None

    def test_returns_none_wrong_capability(self) -> None:
        grant = _valid_grant(capability=Capability.SCAN)
        result = _select_grant([grant], _base_finding())
        assert result is None

    def test_empty_list_returns_none(self) -> None:
        assert _select_grant([], _base_finding()) is None


# ---------------------------------------------------------------------------
# run_fuzz_harness
# ---------------------------------------------------------------------------


class TestRunFuzzHarness:
    def test_raises_on_empty_grants(self) -> None:
        with pytest.raises(ValueError):
            run_fuzz_harness(_base_finding(), [], _deny_verifier())

    def test_returns_fuzz_report(self) -> None:
        grant = _valid_grant()
        report = run_fuzz_harness(_base_finding(), [grant], _deny_verifier())
        assert isinstance(report, FuzzReport)

    def test_payloads_generated_matches_fuzz_script(self) -> None:
        script = "exploit(port=80, verbose=True)"
        finding = _base_finding(script)
        grant = _valid_grant()
        report = run_fuzz_harness(finding, [grant], _deny_verifier())
        assert report.payloads_generated == len(fuzz_script(script))

    def test_results_length_matches_payloads(self) -> None:
        grant = _valid_grant()
        report = run_fuzz_harness(_base_finding(), [grant], _deny_verifier())
        assert len(report.results) == report.payloads_generated

    def test_results_are_fuzz_result_instances(self) -> None:
        grant = _valid_grant()
        report = run_fuzz_harness(_base_finding(), [grant], _deny_verifier())
        for r in report.results:
            assert isinstance(r, FuzzResult)

    def test_each_finding_id_contains_base_id(self) -> None:
        grant = _valid_grant()
        report = run_fuzz_harness(_base_finding(), [grant], _deny_verifier())
        for r in report.results:
            assert r.finding.id.startswith("CVE-FUZZ-001-fuzz-")

    def test_fail_closed_no_matching_grant(self) -> None:
        """Grant que no cubre el target → verifier recibe el grant[0] y deniega."""
        wrong_grant = _valid_grant(target="192.168.0.0", kind="cidr")
        # No matchea 10.0.0.1 (diferente red)
        report = run_fuzz_harness(_base_finding(), [wrong_grant], _deny_verifier())
        # Todos deben ser FAIL (denegados por autorización)
        assert all(r.evidence.verdict == Verdict.FAIL for r in report.results)
        assert report.reproduced_count == 0

    def test_reproduced_count_reflects_pass_verdicts(self) -> None:
        grant = _valid_grant()
        report = run_fuzz_harness(_base_finding(), [grant], _pass_verifier())
        assert report.reproduced_count == sum(
            1 for r in report.results if r.evidence.verdict == Verdict.PASS
        )

    def test_all_pass_with_valid_grant_and_pass_sandbox(self) -> None:
        grant = _valid_grant()
        report = run_fuzz_harness(_base_finding(), [grant], _pass_verifier())
        assert report.reproduced_count == report.payloads_generated
        assert report.reproduced_count > 0
