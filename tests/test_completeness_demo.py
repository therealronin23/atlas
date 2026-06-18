"""Tests anchoring the completeness reference implementation in the suite.

The demo (`docs/demo/completeness_demo.py`) is the paper's reproducible
evidence. These tests guard each adversarial scenario against regression.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_DEMO = Path(__file__).resolve().parent.parent / "docs" / "demo" / "completeness_demo.py"


def _load_demo():
    spec = importlib.util.spec_from_file_location("completeness_demo", _DEMO)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Register before exec: dataclass field introspection looks the module up in
    # sys.modules via cls.__module__ (fails with NoneType otherwise).
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_demo_main_returns_zero():
    assert _load_demo().main() == 0


def test_honest_session_has_no_omission():
    demo = _load_demo()
    assert demo.run_session("honest", demo.OperatorBehaviour()) == []


def test_silent_omission_is_detected():
    demo = _load_demo()
    assert demo.run_session("omit", demo.OperatorBehaviour(omit_seqs={2})) == [2]


def test_faked_ack_is_rejected_so_omission_surfaces():
    demo = _load_demo()
    # Bogus STH / inclusion proof is rejected, so the omission still surfaces.
    assert demo.run_session("fake", demo.OperatorBehaviour(fake_ack_seqs={2})) == [2]


def test_log_rewrite_is_caught_by_consistency_proof():
    demo = _load_demo()
    # Tampering a past entry breaks append-only consistency from that point on.
    gaps = demo.run_session("rewrite", demo.OperatorBehaviour(rewrite_at_seq=3))
    assert 3 in gaps


def test_forgery_attempt_is_rejected():
    demo = _load_demo()
    # Operator has only the public key; a forged request fails verification.
    assert demo.run_forgery_scenario() is True


def test_network_attribution_distinguishes_omission_from_loss():
    demo = _load_demo()
    # seq=2 (receipt, no inclusion) is attributable; seq=4 (no receipt) is not.
    assert demo.run_network_attribution_scenario() is True


def test_output_inspection_omission_detected():
    demo = _load_demo()
    # seq=2 output inspection omitted → seq=2 surfaces in gaps (cascade expected).
    assert demo.run_output_inspection_scenario() is True


def test_shadow_routing_transparent_to_protocol():
    demo = _load_demo()
    # seq=2 routed to shadow_passive → all 6 checks still pass, no gaps.
    # The shadow model commits real entries; decision="shadow_passive" is
    # auditable in the log but does not create any omission from the subject's view.
    assert demo.run_shadow_routing_scenario() is True
