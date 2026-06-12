"""
Cableado capa 2 → orchestrator (ADR-042): el codegen proposer produce vía
CascadeRouter (L0→L1) con UnifiedDiffVerifier, y deja evidencia en Merkle.
Hub fake inyectado: sin red, sin subprocesos reales.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from atlas.core.inference_hub import InferenceLevel, InferenceResponse
from atlas.core.orchestrator import Orchestrator
from atlas.core.self_maintenance import CodegenTarget


class _ScriptedHub:
    """Devuelve respuestas pre-escritas en orden; registra cada request."""

    def __init__(self, script: list[InferenceResponse]) -> None:
        self._script = list(script)
        self.calls: list[Any] = []

    def infer(self, request: Any) -> InferenceResponse:
        self.calls.append(request)
        if len(self._script) > 1:
            return self._script.pop(0)
        return self._script[0]


def _resp(text: str) -> InferenceResponse:
    return InferenceResponse(
        text=text, provider="mock", model="m", level=InferenceLevel.L1,
        latency_ms=1, success=True, tokens_used=1, mode="live",
    )


_PATH = "src/atlas/demo.py"
_DIFF = (
    f"--- a/{_PATH}\n"
    f"+++ b/{_PATH}\n"
    "@@ -1,1 +1,1 @@\n"
    "-old = 1\n"
    "+old = 2\n"
)
_TARGET = CodegenTarget(goal="sube old a 2", path=_PATH)


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
    return Orchestrator(workspace=tmp_path / "atlas")


def _wire(orch: Orchestrator, hub: _ScriptedHub) -> tuple[Any, list[str]]:
    """Inyecta hub fake y captura los propose hacia ColdUpdate (sin git real)."""
    orch._inference_hub = hub  # type: ignore[assignment]
    proposed: list[str] = []
    manager = orch.cold_update()
    manager.propose = (  # type: ignore[method-assign]
        lambda intent, patch_path, **kw: (
            proposed.append(Path(patch_path).read_text(encoding="utf-8")),
            SimpleNamespace(id="cold-1"),
        )[1]
    )
    return orch.maintenance_codegen_proposer(), proposed


def _cascade_records(orch: Orchestrator) -> list[dict[str, Any]]:
    return [
        r.to_dict() for r in orch._merkle.tail(50)
        if r.to_dict()["action"] == "cascade.route"
    ]


class TestCodegenCascade:
    def test_valid_l0_diff_proposed_with_evidence(self, orch: Orchestrator) -> None:
        hub = _ScriptedHub([_resp(_DIFF)])
        proposer, proposed = _wire(orch, hub)
        result = proposer.propose_patch(_TARGET)
        assert result is not None and result.id == "cold-1"
        assert proposed and proposed[0].startswith(f"--- a/{_PATH}")
        assert len(hub.calls) == 1  # L0 bastó: no escaló
        assert hub.calls[0].level is InferenceLevel.L0
        assert hub.calls[0].temperature == 0.0

        records = _cascade_records(orch)
        assert len(records) == 1 and records[0]["result"] == "success"
        assert records[0]["payload"]["verified"] is True
        assert records[0]["payload"]["escalations"] == 0

    def test_garbage_l0_escalates_to_l1(self, orch: Orchestrator) -> None:
        hub = _ScriptedHub([_resp("No puedo ayudarte con eso."), _resp(_DIFF)])
        proposer, proposed = _wire(orch, hub)
        result = proposer.propose_patch(_TARGET)
        assert result is not None
        assert proposed
        assert [c.level for c in hub.calls] == [InferenceLevel.L0, InferenceLevel.L1]

        record = _cascade_records(orch)[0]
        assert record["payload"]["escalations"] == 1
        assert record["payload"]["attempts"][0]["verdict"] == "fail"
        assert record["payload"]["attempts"][1]["verdict"] == "pass"

    def test_out_of_scope_diff_fails_cascade_before_proposer(self, orch: Orchestrator) -> None:
        # El diff toca otro fichero: UnifiedDiffVerifier lo tumba en ambos
        # rungs y _generate devuelve "" — ColdUpdate ni se entera.
        evil = _DIFF.replace(_PATH, "src/atlas/secrets.py")
        hub = _ScriptedHub([_resp(evil)])
        proposer, proposed = _wire(orch, hub)
        result = proposer.propose_patch(_TARGET)
        assert result is None
        assert proposed == []

        record = _cascade_records(orch)[0]
        assert record["result"] == "failure"
        assert record["payload"]["verified"] is False
        assert len(record["payload"]["attempts"]) == 2  # L0 y L1 intentados

    def test_context_propagated_to_hub(self, orch: Orchestrator) -> None:
        hub = _ScriptedHub([_resp(_DIFF)])
        proposer, _ = _wire(orch, hub)
        proposer.propose_patch(
            CodegenTarget(goal="sube old a 2", path=_PATH, context="contenido actual")
        )
        assert hub.calls[0].context == "contenido actual"
        assert hub.calls[0].task_id == "codegen.patch"
