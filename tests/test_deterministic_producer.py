"""
ADR-048 fase C — DeterministicProducer (arnés). Transforms puros, invariante AST,
diff unificado. Sin red, sin git.
"""

from __future__ import annotations

from atlas.core.deterministic_producer import (
    DEFAULT_TRANSFORMS,
    DeterministicProducer,
    Transform,
    detect_transforms,
)
from atlas.core.verify import (
    ArtifactKind,
    CostTier,
    UnifiedDiffVerifier,
    UniversalVerifier,
    Verdict,
)
from atlas.router.cascade import ArtifactKind as _Kind  # noqa: F401
from atlas.router.cascade import TaskSpec


def _spec(path: str, source: str) -> TaskSpec:
    return TaskSpec(
        intent=f"limpia {path}",
        kind=ArtifactKind.PATCH,
        metadata={"target_path": path, "source": source},
    )


class TestTransforms:
    def test_strips_trailing_whitespace(self) -> None:
        out = DeterministicProducer().produce(_spec("x.py", "a = 1   \nb = 2\n"))
        assert "transforms_applied" in out.metadata
        assert "strip_trailing_whitespace" in out.metadata["transforms_applied"]
        assert "diff" in out.payload and out.payload["diff"]

    def test_adds_final_newline(self) -> None:
        out = DeterministicProducer().produce(_spec("x.py", "a = 1"))
        assert "ensure_final_newline" in out.metadata["transforms_applied"]

    def test_collapses_eof_blank_lines(self) -> None:
        names = detect_transforms("x.py", "a = 1\n\n\n\n")
        assert "collapse_eof_blank_lines" in names

    def test_clean_file_yields_empty_diff(self) -> None:
        out = DeterministicProducer().produce(_spec("x.py", "a = 1\n"))
        assert out.payload["diff"] == ""
        assert out.metadata["transforms_applied"] == []


class TestInvariant:
    def test_non_python_skips_ast_check(self) -> None:
        # markdown con whitespace: se limpia aunque no sea Python parseable
        names = detect_transforms("README.md", "# Title   \n\ntext")
        assert "strip_trailing_whitespace" in names

    def test_transform_that_breaks_ast_is_discarded(self) -> None:
        # Un transform malicioso que rompe el AST nunca se aplica sobre .py.
        breaker = Transform("breaker", lambda s: s + "\ndef (:\n")
        names = detect_transforms("x.py", "a = 1\n", (breaker,))
        assert names == ()

    def test_breaker_allowed_on_non_python(self) -> None:
        breaker = Transform("breaker", lambda s: s + "garbage")
        names = detect_transforms("notes.txt", "hi", (breaker,))
        assert names == ("breaker",)


class TestProducerContract:
    def test_is_cheapest_mechanical(self) -> None:
        p = DeterministicProducer()
        assert p.cost is CostTier.SHAPE  # ast.parse > regex de forma del diff
        assert p.producer_id == "deterministic"

    def test_diff_passes_unified_verifier(self) -> None:
        out = DeterministicProducer().produce(_spec("x.py", "a = 1  \nb=2"))
        # SHAPE producer > STATIC verifier → la regla asimétrica aplica directo.
        ev = UniversalVerifier([UnifiedDiffVerifier()]).verify(out)
        assert ev.verdict is Verdict.PASS

    def test_deterministic_same_input_same_diff(self) -> None:
        a = DeterministicProducer().produce(_spec("x.py", "a = 1   \n"))
        b = DeterministicProducer().produce(_spec("x.py", "a = 1   \n"))
        assert a.payload["diff"] == b.payload["diff"]

    def test_allowed_paths_stamped(self) -> None:
        out = DeterministicProducer().produce(_spec("pkg/x.py", "a=1  "))
        assert out.metadata["allowed_paths"] == ["pkg/x.py"]


def test_default_transforms_have_stable_names() -> None:
    assert [t.name for t in DEFAULT_TRANSFORMS] == [
        "strip_trailing_whitespace",
        "ensure_final_newline",
        "collapse_eof_blank_lines",
    ]
