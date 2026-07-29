"""Dispatch F2.6 agnóstico de proveedor (2026-07-29).

`_default_claude_dispatch` en f26_gate.py ata F2.6 a una sesión interactiva
de Claude Code. Pero `run_f26()` acepta un `dispatch` inyectable a propósito
("el spec no fija cuál mecanismo") y `grade_f26_transcript` sólo depende de
la FORMA del transcript (JSONL de eventos assistant/tool_use), no de quién lo
generó. Este módulo prueba un dispatch real —bucle de tool-calling de
InferenceHub sobre CUALQUIER proveedor configurado en .env, mismo patrón que
ToolCoder— con herramientas nombradas para que la rúbrica exigente (grafo
antes que grep, GoldenRoute antes que Edit, nunca `git push`/`add -A`) se
evalúe con el MISMO `grade_f26_transcript`, sin tocarlo.

CERO red/LLM real: el hub se sustituye por un fake con respuestas guionadas.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from atlas.core.inference_hub import InferenceLevel, InferenceRequest, InferenceResponse
from atlas.core.self_maintenance.f26_grading import grade_f26_transcript


class _ScriptedHub:
    """Fake de InferenceHub: devuelve una respuesta guionada por llamada,
    en orden. Falla ruidosamente si se piden más turnos de los guionados
    (protege contra que un bug deje el bucle sin condición de parada)."""

    def __init__(self, responses: list[InferenceResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[InferenceRequest] = []

    def infer_for_role(self, role: str, request: InferenceRequest) -> InferenceResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("_ScriptedHub: más turnos de los guionados")
        return self._responses.pop(0)


def _resp(
    *, text: str = "", tool_calls: list[dict[str, Any]] | None = None
) -> InferenceResponse:
    return InferenceResponse(
        text=text, provider="fake", model="fake-model", level=InferenceLevel.L1,
        latency_ms=1, success=True, tool_calls=tool_calls or [],
    )


def _tool_call(tool_id: str, name: str, **arguments: Any) -> dict[str, Any]:
    return {"id": tool_id, "name": name, "arguments": json.dumps(arguments)}


_FINAL_TEXT_ALL_MARKERS = (
    "Estado citado desde WORK_LEDGER.md (2026-07-17): la fase activa es X. "
    "NEXT_AI_INSTRUCTIONS es histórico, ya no vigente como protocolo. "
    "Respondo 5 y 6 desde actor_roles y el recall del sustrato (harness: "
    "roles de sesión, doctrine: delegación) según docs/handoff/GENERATED."
)


class TestAgenticDispatchProducesGradeableTranscript:
    """El transcript que emite `agentic_dispatch`, pasado tal cual por el
    `grade_f26_transcript` YA EXISTENTE, debe puntuar igual que uno de
    Claude Code — es la prueba de que reusar el grader sin tocarlo es
    correcto, no una coincidencia de test."""

    def test_well_behaved_session_passes_items_2_3_5(self, tmp_path: Path) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import agentic_dispatch

        hub = _ScriptedHub([
            _resp(tool_calls=[_tool_call("1", "trunk_invoke_readonly", tool="graph_importers", module="atlas.a")]),
            _resp(tool_calls=[_tool_call("2", "GoldenRoute", text="añade una línea")]),
            _resp(text=_FINAL_TEXT_ALL_MARKERS),
        ])

        proc = agentic_dispatch("prompt de prueba", tmp_path, hub=hub)

        assert isinstance(proc, subprocess.CompletedProcess)
        transcript = tmp_path / "transcript.txt"
        transcript.write_text(proc.stdout, encoding="utf-8")
        graded = grade_f26_transcript(transcript)

        assert graded["item_2"] == "pass", graded["details"]["item_2"]
        assert graded["item_3"] == "pass", graded["details"]["item_3"]
        assert graded["item_5"] == "pass", graded["details"]["item_5"]
        assert graded["item_1"] == "pass", graded["details"]["item_1"]
        assert graded["item_4"] == "pass", graded["details"]["item_4"]
        assert graded["item_6"] == "pass", graded["details"]["item_6"]
        assert graded["score"] == "6/6"

    def test_grep_before_graph_tool_fails_item_2(self, tmp_path: Path) -> None:
        """Comportamiento MALO real: el propio grader (sin tocar) debe
        seguir detectándolo aunque el dispatch sea distinto de Claude."""
        from atlas.core.self_maintenance.f26_agentic_dispatch import agentic_dispatch

        (tmp_path / "WORK_LEDGER.md").write_text("estado\n", encoding="utf-8")
        hub = _ScriptedHub([
            _resp(tool_calls=[_tool_call("1", "Grep", pattern="inference_hub")]),
            _resp(tool_calls=[_tool_call("2", "trunk_invoke_readonly", tool="graph_importers", module="atlas.a")]),
            _resp(text=_FINAL_TEXT_ALL_MARKERS),
        ])

        proc = agentic_dispatch("prompt", tmp_path, hub=hub)
        transcript = tmp_path / "t.txt"
        transcript.write_text(proc.stdout, encoding="utf-8")
        graded = grade_f26_transcript(transcript)

        assert graded["item_2"] == "fail"

    def test_direct_edit_without_golden_route_fails_item_3(self, tmp_path: Path) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import agentic_dispatch

        target = tmp_path / "docs"
        target.mkdir()
        (target / "continuation.md").write_text("x\n", encoding="utf-8")
        hub = _ScriptedHub([
            _resp(tool_calls=[_tool_call(
                "1", "Edit", path="docs/continuation.md", old_str="x\n", new_str="y\n",
            )]),
            _resp(text=_FINAL_TEXT_ALL_MARKERS),
        ])

        proc = agentic_dispatch("prompt", tmp_path, hub=hub)
        transcript = tmp_path / "t.txt"
        transcript.write_text(proc.stdout, encoding="utf-8")
        graded = grade_f26_transcript(transcript)

        assert graded["item_3"] == "fail"


class TestDispatchContract:
    def test_return_value_matches_run_f26_dispatch_contract(self, tmp_path: Path) -> None:
        """Debe poder inyectarse en run_f26 sin cambiar su firma."""
        from atlas.core.self_maintenance.f26_agentic_dispatch import agentic_dispatch
        from atlas.core.self_maintenance.f26_gate import run_f26

        doc = tmp_path / "doc.md"
        doc.write_text(
            "## Cómo ejecutarlo\n\n"
            "```bash\nclaude -p --model sonnet \"pregunta de prueba\"\n```\n",
            encoding="utf-8",
        )
        hub = _ScriptedHub([_resp(text=_FINAL_TEXT_ALL_MARKERS)])

        def dispatch(prompt: str, cwd: Path) -> subprocess.CompletedProcess[str]:
            return agentic_dispatch(prompt, cwd, hub=hub)

        record = run_f26(tmp_path, doc_path=doc, dispatch=dispatch)

        assert record["success"] is True
        assert record["overall_result"] in {"pass", "fail"}  # gradeó de verdad
        assert record["recorded"] is True


class TestBashToolIsSandboxedReadOnly:
    def test_bash_tool_cannot_write_to_the_repo(self, tmp_path: Path) -> None:
        pytest.importorskip("atlas.security.bwrap_jail")
        from atlas.security.bwrap_jail import BwrapUnavailableError

        from atlas.core.self_maintenance.f26_agentic_dispatch import _tool_bash

        try:
            result = _tool_bash("touch should-not-exist.txt", cwd=tmp_path)
        except BwrapUnavailableError:
            pytest.skip("bwrap no disponible en este host")

        assert not (tmp_path / "should-not-exist.txt").exists()
        assert "error" in result.lower() or "read-only" in result.lower() \
            or "permission" in result.lower()

    def test_bash_tool_can_read(self, tmp_path: Path) -> None:
        pytest.importorskip("atlas.security.bwrap_jail")
        from atlas.security.bwrap_jail import BwrapUnavailableError

        from atlas.core.self_maintenance.f26_agentic_dispatch import _tool_bash

        (tmp_path / "marker.txt").write_text("hola\n", encoding="utf-8")
        try:
            result = _tool_bash("cat marker.txt", cwd=tmp_path)
        except BwrapUnavailableError:
            pytest.skip("bwrap no disponible en este host")

        assert "hola" in result


class TestReadToolRespectsProtectedPaths:
    def test_refuses_protected_path(self, tmp_path: Path) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import _tool_read

        result = _tool_read("/etc/passwd", cwd=tmp_path)

        assert "error" in result.lower() or "denegado" in result.lower()

    def test_reads_normal_file(self, tmp_path: Path) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import _tool_read

        (tmp_path / "x.md").write_text("contenido real\n", encoding="utf-8")

        result = _tool_read("x.md", cwd=tmp_path)

        assert "contenido real" in result


class TestGoldenRouteToolUsesSharedStore:
    """`GoldenRoute.for_repo()` crea un store AISLADO — invisible a
    `atlas update status/validate/approve/apply` (advertencia explícita en
    Orchestrator.golden_route()). La tool debe usar el mismo Orchestrator
    real, nunca la fábrica aislada."""

    def test_proposal_is_visible_via_cold_update_manager(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas"))
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path / "repo"))
        monkeypatch.setenv("ATLAS_REPO_ROOT", str(tmp_path / "repo"))
        repo = tmp_path / "repo"
        (repo / "docs").mkdir(parents=True)
        (repo / "docs" / "continuation.md").write_text("línea existente\n", encoding="utf-8")

        from atlas.core.orchestrator import Orchestrator
        from atlas.core.self_maintenance.f26_agentic_dispatch import _tool_golden_route

        orch = Orchestrator(workspace=tmp_path / "atlas")
        result = _tool_golden_route(
            'añade la línea "marca" al final de docs/continuation.md', orch=orch,
        )

        assert "Proposal" in result or "proposal" in result
        proposals = orch.cold_update().list_proposals()
        assert proposals, "la propuesta debe existir en el ColdUpdateManager COMPARTIDO"
