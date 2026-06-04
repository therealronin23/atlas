"""ADR-039 slice 7 — CodegenProposer (patch dirigido, nunca apply solo).

Reglas que estos tests fijan:

- **El humano apunta el objetivo:** no hay contenido no confiable; el generador
  (LLM) se inyecta como callable falso → cero LLM real.
- **Guard de alcance fail-closed:** un patch que toca un fichero distinto del
  apuntado se rechaza; un objetivo fuera de los prefijos permitidos se rechaza
  antes de generar.
- **Entrega a ColdUpdate, nunca aplica:** el patch válido se delega a un
  ``propose`` inyectado con ``origin="self_audit"``; no se toca ColdUpdate real.
- **Tolerante al formato del LLM:** extrae el diff aunque venga en fences ```diff.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atlas.core.self_maintenance import CodegenProposer, CodegenTarget
from atlas.logging.merkle_logger import MerkleLogger


@pytest.fixture
def merkle(tmp_path: Path) -> MerkleLogger:
    return MerkleLogger(tmp_path / "merkle")


def _diff(path: str) -> str:
    return (
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1,1 +1,1 @@\n"
        "-old = 1\n"
        "+old = 2\n"
    )


_TARGET = CodegenTarget(goal="sube old a 2", path="src/atlas/demo.py")


class TestProposePatch:
    def test_valid_patch_delegated_to_coldupdate(self, merkle) -> None:
        seen: dict[str, Any] = {}

        def _propose(intent, patch_path, **kw):
            seen["intent"] = intent
            seen["patch"] = Path(patch_path).read_text(encoding="utf-8")
            seen["kw"] = kw
            return type("P", (), {"id": "cold-7"})()

        proposal = CodegenProposer(
            merkle=merkle,
            generate=lambda t: _diff(t.path),
            propose=_propose,
        ).propose_patch(_TARGET)

        assert proposal.id == "cold-7"
        assert seen["kw"]["origin"] == "self_audit"
        assert seen["kw"]["risk"] == "high"
        assert "src/atlas/demo.py" in seen["intent"]
        assert seen["patch"].startswith("--- a/src/atlas/demo.py")

    def test_extracts_fenced_diff(self, merkle) -> None:
        captured: dict[str, str] = {}

        def _propose(intent, patch_path, **kw):
            captured["patch"] = Path(patch_path).read_text(encoding="utf-8")
            return type("P", (), {"id": "x"})()

        fenced = "Aquí tienes:\n```diff\n" + _diff("src/atlas/demo.py") + "```\n"
        CodegenProposer(
            merkle=merkle, generate=lambda t: fenced, propose=_propose
        ).propose_patch(_TARGET)
        assert captured["patch"].startswith("--- a/src/atlas/demo.py")


class TestScopeGuard:
    def test_patch_touching_other_file_rejected(self, merkle) -> None:
        called: list[Any] = []
        # El LLM intenta editar un fichero distinto del apuntado.
        result = CodegenProposer(
            merkle=merkle,
            generate=lambda t: _diff("src/atlas/secrets.py"),
            propose=lambda *a, **k: called.append(a),
        ).propose_patch(_TARGET)
        assert result is None
        assert called == []

    def test_multi_file_patch_rejected(self, merkle) -> None:
        called: list[Any] = []
        two = _diff("src/atlas/demo.py") + _diff("src/atlas/other.py")
        result = CodegenProposer(
            merkle=merkle, generate=lambda t: two,
            propose=lambda *a, **k: called.append(a),
        ).propose_patch(_TARGET)
        assert result is None
        assert called == []

    def test_target_outside_prefixes_rejected_before_generate(self, merkle) -> None:
        generated: list[str] = []
        result = CodegenProposer(
            merkle=merkle,
            generate=lambda t: generated.append("gen") or _diff(t.path),
            propose=lambda *a, **k: None,
        ).propose_patch(CodegenTarget(goal="x", path="/etc/passwd"))
        assert result is None
        assert generated == []  # ni siquiera se invoca al generador


class TestFailClosed:
    def test_no_diff_in_output(self, merkle) -> None:
        result = CodegenProposer(
            merkle=merkle,
            generate=lambda t: "No puedo ayudarte con eso.",
            propose=lambda *a, **k: 1 / 0,
        ).propose_patch(_TARGET)
        assert result is None

    def test_generator_exception(self, merkle) -> None:
        def _boom(t):
            raise RuntimeError("LLM caído")

        result = CodegenProposer(
            merkle=merkle, generate=_boom, propose=lambda *a, **k: 1 / 0
        ).propose_patch(_TARGET)
        assert result is None


class TestAudit:
    def test_rejection_audited_applied_false(self, merkle) -> None:
        CodegenProposer(
            merkle=merkle,
            generate=lambda t: _diff("src/atlas/secrets.py"),
            propose=lambda *a, **k: None,
        ).propose_patch(_TARGET)
        rec = next(
            r.to_dict() for r in merkle.tail(10)
            if r.to_dict()["action"] == "self_maintenance.codegen_proposer_patch"
        )
        assert rec["result"] == "patch_out_of_scope"
        assert rec["payload"]["applied"] is False
