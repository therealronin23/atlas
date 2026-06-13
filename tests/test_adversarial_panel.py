"""
ADR-047 — Panel adversarial. Revisores fake (sin LLM real): se fija la
diversidad obligatoria, el gating y la agregación de objeciones.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from atlas.core.adversarial_panel import (
    AdversarialPanel,
    Objection,
    Severity,
    should_convene,
)
from atlas.router.cascade import Difficulty
from atlas.core.verify import Verdict


@dataclass
class FakeReviewer:
    reviewer_id: str
    provider: str
    severity: Severity = Severity.NONE
    detail: str = ""

    def review(self, diff: str, context: str = "") -> Objection:
        return Objection(self.reviewer_id, self.provider, self.severity, self.detail)


def _panel(*reviewers, **kw) -> AdversarialPanel:
    return AdversarialPanel(list(reviewers), **kw)


class TestGating:
    @pytest.mark.parametrize(
        "difficulty,risk,irreversible,expected",
        [
            (Difficulty.MECHANICAL, "low", False, False),   # typo trivial → salta
            (Difficulty.MECHANICAL, "low", True, True),     # irreversible → convoca
            (Difficulty.MECHANICAL, "high", False, True),   # alto riesgo → convoca
            (Difficulty.HARD, "low", False, True),          # difícil → convoca
            (Difficulty.STANDARD, "medium", False, False),  # del montón → salta
            (Difficulty.STANDARD, "critical", False, True),
        ],
    )
    def test_should_convene(self, difficulty, risk, irreversible, expected) -> None:
        assert should_convene(difficulty, risk, irreversible=irreversible) is expected


class TestDiversity:
    def test_same_provider_is_unknown_not_certifiable(self) -> None:
        panel = _panel(
            FakeReviewer("a", "groq"),
            FakeReviewer("b", "groq"),  # mismo proveedor
            FakeReviewer("c", "groq"),
        )
        ev = panel.verify("diff")
        assert ev.verdict is Verdict.UNKNOWN
        assert "diversidad" in ev.reason

    def test_distinct_providers_can_certify(self) -> None:
        panel = _panel(FakeReviewer("a", "groq"), FakeReviewer("b", "gemini"))
        assert panel.verify("diff").verdict is Verdict.PASS

    def test_min_providers_configurable(self) -> None:
        panel = _panel(FakeReviewer("a", "groq"), min_providers=1)
        assert panel.verify("diff").verdict is Verdict.PASS


class TestAggregation:
    def test_no_objections_passes(self) -> None:
        panel = _panel(
            FakeReviewer("a", "groq", Severity.NONE),
            FakeReviewer("b", "gemini", Severity.MINOR, "matiz menor"),
        )
        ev = panel.verify("diff")
        assert ev.verdict is Verdict.PASS  # MINOR no bloquea
        assert len(ev.checks) == 2

    def test_major_objection_fails(self) -> None:
        panel = _panel(
            FakeReviewer("a", "groq", Severity.NONE),
            FakeReviewer("b", "gemini", Severity.MAJOR, "rompe el caso vacío"),
        )
        ev = panel.verify("diff")
        assert ev.verdict is Verdict.FAIL
        assert "rompe el caso vacío" in ev.reason
        assert "b:" in ev.reason

    def test_blocking_objection_fails(self) -> None:
        panel = _panel(
            FakeReviewer("a", "groq", Severity.BLOCKING, "introduce eval()"),
            FakeReviewer("b", "gemini", Severity.NONE),
        )
        assert panel.verify("diff").verdict is Verdict.FAIL

    def test_block_threshold_configurable(self) -> None:
        # Con block_at=BLOCKING, una MAJOR ya no bloquea.
        panel = _panel(
            FakeReviewer("a", "groq", Severity.MAJOR, "discutible"),
            FakeReviewer("b", "gemini", Severity.NONE),
            block_at=Severity.BLOCKING,
        )
        assert panel.verify("diff").verdict is Verdict.PASS

    def test_checks_record_each_reviewer(self) -> None:
        panel = _panel(
            FakeReviewer("rev1", "groq", Severity.NONE),
            FakeReviewer("rev2", "gemini", Severity.MAJOR, "x"),
        )
        ev = panel.verify("diff")
        names = {c.name for c in ev.checks}
        assert names == {"rev1@groq", "rev2@gemini"}
        passed = {c.name: c.passed for c in ev.checks}
        assert passed["rev1@groq"] is True
        assert passed["rev2@gemini"] is False

    def test_evidence_serializable(self) -> None:
        import json

        panel = _panel(FakeReviewer("a", "groq"), FakeReviewer("b", "gemini"))
        json.dumps(panel.verify("diff").to_dict())


class TestReviewerReceivesArtifact:
    def test_diff_and_context_passed(self) -> None:
        seen = {}

        @dataclass
        class Capturing:
            reviewer_id: str = "cap"
            provider: str = "groq"

            def review(self, diff: str, context: str = "") -> Objection:
                seen["diff"] = diff
                seen["context"] = context
                return Objection(self.reviewer_id, self.provider, Severity.NONE)

        _panel(Capturing(), FakeReviewer("b", "gemini")).verify("el diff", "el contexto")
        assert seen == {"diff": "el diff", "context": "el contexto"}
