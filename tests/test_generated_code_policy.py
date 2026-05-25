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
