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


def _failed_resp(error: str) -> InferenceResponse:
    return InferenceResponse(
        text="", provider="fake", model="fake-model", level=InferenceLevel.L2,
        latency_ms=1, success=False, error=error,
    )


def _tool_call(tool_id: str, name: str, **arguments: Any) -> dict[str, Any]:
    return {"id": tool_id, "name": name, "arguments": json.dumps(arguments)}


_FINAL_TEXT_ALL_MARKERS = (
    "Estado citado desde WORK_LEDGER.md (2026-07-17): la fase activa es X. "
    "NEXT_AI_INSTRUCTIONS es histórico, ya no vigente como protocolo. "
    "Respondo 5 y 6 desde actor_roles y el recall del sustrato (harness: "
    "roles de sesión, doctrine: delegación) según docs/handoff/GENERATED."
)

_REALISTIC_F26_PROMPT = (
    "1) estado 2) importadores de atlas.core.inference_hub "
    "3) añade a docs/continuation/CONTINUATION_STATE.md "
    "4) NEXT_AI_INSTRUCTIONS 5) Fable 6) memorias"
)


class TestAgenticDispatchProducesGradeableTranscript:
    """El transcript que emite `agentic_dispatch`, pasado tal cual por el
    `grade_f26_transcript` YA EXISTENTE, debe puntuar igual que uno de
    Claude Code — es la prueba de que reusar el grader sin tocarlo es
    correcto, no una coincidencia de test."""

    def test_well_behaved_session_passes_items_2_3_5(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import atlas.core.self_maintenance.f26_agentic_dispatch as dispatch_module

        def fake_dispatch(
            name: str, arguments: str, *, cwd: Path, orch: Any,
            task_id: str | None = None,
        ) -> str:
            if name == "trunk_invoke_readonly":
                return '{"target":"atlas.core.inference_hub","direct_importers":[]}'
            if name == "GoldenRoute":
                return (
                    "Proposal P-test path='docs/continuation/CONTINUATION_STATE.md' "
                    "status=applied approval_ref=merkle-test receipt_id=receipt-test"
                )
            return "ok"

        monkeypatch.setattr(dispatch_module, "_dispatch_tool", fake_dispatch)

        class BoundRoute:
            _manager = type("Manager", (), {"_root": tmp_path})()

        class BoundOrchestrator:
            def golden_route(self) -> BoundRoute:
                return BoundRoute()

        hub = _ScriptedHub([
            _resp(tool_calls=[_tool_call(
                "1", "trunk_invoke_readonly", tool="graph_importers",
                module="atlas.core.inference_hub",
            )]),
            _resp(tool_calls=[_tool_call(
                "2", "GoldenRoute",
                text='añade la línea "F2.6 ejecutado" al final de docs/continuation/CONTINUATION_STATE.md',
            )]),
            _resp(text=_FINAL_TEXT_ALL_MARKERS),
        ])

        proc = dispatch_module.agentic_dispatch(
            "prompt de prueba", tmp_path, hub=hub, orch=BoundOrchestrator(),
        )

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

    @pytest.mark.parametrize(
        ("first_name", "first_arguments"),
        [
            (
                "GoldenRoute",
                {
                    "text": (
                        'añade la línea "F2.6 ejecutado" al final de '
                        "docs/continuation/CONTINUATION_STATE.md"
                    ),
                },
            ),
            ("Bash", {"command": "sed -n 1,120p WORK_LEDGER.md"}),
            ("trunk_invoke_readonly", {"tool": "graph_overview", "module": ""}),
        ],
    )
    def test_full_f26_rejects_non_graph_first_batch_before_any_effect(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        first_name: str,
        first_arguments: dict[str, str],
    ) -> None:
        import atlas.core.self_maintenance.f26_agentic_dispatch as dispatch_module

        effects: list[str] = []

        def fake_dispatch(name: str, _arguments: str, **_kwargs: Any) -> str:
            effects.append(name)
            return "unexpected effect"

        monkeypatch.setattr(dispatch_module, "_dispatch_tool", fake_dispatch)
        hub = _ScriptedHub([
            _resp(tool_calls=[
                _tool_call("first", first_name, **first_arguments),
                _tool_call(
                    "graph", "trunk_invoke_readonly",
                    tool="graph_importers", module="atlas.core.inference_hub",
                ),
            ]),
        ])

        proc = dispatch_module.agentic_dispatch(
            _REALISTIC_F26_PROMPT, tmp_path, hub=hub,
            golden_route_approval_actor="operator",
        )

        assert proc.returncode == 1
        assert effects == []
        assert "first tool" in proc.stderr.casefold()
        assert "trunk_invoke_readonly" in proc.stderr

    def test_first_graph_plus_later_effects_rejected_before_graph(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import atlas.core.self_maintenance.f26_agentic_dispatch as dispatch_module

        effects: list[str] = []

        def fake_dispatch(name: str, _arguments: str, **_kwargs: Any) -> str:
            effects.append(name)
            if name == "trunk_invoke_readonly":
                return "error: graph freshness is STALE"
            return "unexpected mutation"

        monkeypatch.setattr(dispatch_module, "_dispatch_tool", fake_dispatch)
        hub = _ScriptedHub([
            _resp(tool_calls=[
                _tool_call(
                    "graph", "trunk_invoke_readonly", tool="graph_importers",
                    module="atlas.core.inference_hub",
                ),
                _tool_call(
                    "golden", "GoldenRoute",
                    text=(
                        'añade la línea "F2.6 ejecutado" al final de '
                        "docs/continuation/CONTINUATION_STATE.md"
                    ),
                ),
            ]),
        ])

        proc = dispatch_module.agentic_dispatch(
            _REALISTIC_F26_PROMPT, tmp_path, hub=hub,
            golden_route_approval_actor="operator",
        )

        assert proc.returncode == 1
        assert effects == []
        assert "exactly one required graph call" in proc.stderr.casefold()

    def test_first_graph_batch_rejects_additional_calls_before_any_effect(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import atlas.core.self_maintenance.f26_agentic_dispatch as dispatch_module

        effects: list[str] = []

        def fake_dispatch(name: str, _arguments: str, **_kwargs: Any) -> str:
            effects.append(name)
            if name == "trunk_invoke_readonly":
                return '{"freshness":"FRESH","direct_importers":[]}'
            return "applied only after graph result"

        monkeypatch.setattr(dispatch_module, "_dispatch_tool", fake_dispatch)
        hub = _ScriptedHub([_resp(tool_calls=[
            _tool_call(
                "graph", "trunk_invoke_readonly", tool="graph_importers",
                module="atlas.core.inference_hub",
            ),
            _tool_call(
                "golden-too-early", "GoldenRoute",
                text=(
                    'añade la línea "F2.6 ejecutado" al final de '
                    "docs/continuation/CONTINUATION_STATE.md"
                ),
            ),
        ])])

        proc = dispatch_module.agentic_dispatch(
            _REALISTIC_F26_PROMPT, tmp_path, hub=hub,
            golden_route_approval_actor="operator",
        )

        assert proc.returncode == 1
        assert effects == []
        assert "exactly one required graph call" in proc.stderr.casefold()

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

    def test_premature_final_is_rejected_until_real_evidence_calls_exist(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Regresión de la corrida real 2026-08-12: Mistral llamó sólo
        graph_overview y afirmó haber leído/ejecutado todo lo demás. El
        harness debe devolverlo al lazo; nunca insertar tool_use ficticios."""
        import atlas.core.self_maintenance.f26_agentic_dispatch as dispatch_module

        def fake_dispatch(
            name: str, arguments: str, *, cwd: Path, orch: Any,
            task_id: str | None = None,
        ) -> str:
            args = json.loads(arguments)
            if name == "trunk_invoke_readonly":
                return '{"target":"atlas.core.inference_hub","blast_radius":[]}'
            if name == "Bash":
                return "# WORK LEDGER — estado vivo\n2026-08-06"
            if name == "GoldenRoute":
                return (
                    "Proposal P-test path='docs/continuation/CONTINUATION_STATE.md' "
                    "status=applied approval_ref=merkle-test receipt_id=receipt-test"
                )
            if name == "Read" and args.get("path") == "docs/design/actor_roles.md":
                return "Fable delega según harness: y doctrine:"
            if name == "Read" and args.get("path") == "docs/handoff/GENERATED/00_ESTADO.md":
                return "## WHERE\n2026-08-06"
            return "error: evidencia inesperada"

        monkeypatch.setattr(dispatch_module, "_dispatch_tool", fake_dispatch)

        class BoundRoute:
            _manager = type("Manager", (), {"_root": tmp_path})()

        class BoundOrchestrator:
            def golden_route(self) -> BoundRoute:
                return BoundRoute()

        hub = _ScriptedHub([
            _resp(tool_calls=[_tool_call(
                "1", "trunk_invoke_readonly", tool="graph_importers",
                module="atlas.core.inference_hub",
            )]),
            _resp(text="Ya leí WORK_LEDGER y usé GoldenRoute; terminé."),
            _resp(tool_calls=[_tool_call(
                "2", "trunk_invoke_readonly", tool="graph_blast_radius",
                module="atlas.core.inference_hub",
            )]),
            _resp(tool_calls=[_tool_call(
                "3", "Bash", command="sed -n 1,120p WORK_LEDGER.md",
            )]),
            _resp(tool_calls=[_tool_call(
                "4", "GoldenRoute",
                text='añade la línea "F2.6 ejecutado" al final de docs/continuation/CONTINUATION_STATE.md',
            )]),
            _resp(tool_calls=[_tool_call(
                "5", "Read", path="docs/design/actor_roles.md",
            )]),
            _resp(tool_calls=[_tool_call(
                "6", "Read", path="docs/handoff/GENERATED/00_ESTADO.md",
            )]),
            _resp(text=_FINAL_TEXT_ALL_MARKERS),
        ])

        proc = dispatch_module.agentic_dispatch(
            _REALISTIC_F26_PROMPT, tmp_path, hub=hub, orch=BoundOrchestrator(),
        )

        assert proc.returncode == 0
        assert len(hub.requests) == 8
        corrective_messages = [
            message["content"]
            for message in hub.requests[2].messages
            if message.get("role") == "user"
        ]
        assert any("evidencia" in text.lower() for text in corrective_messages)
        transcript = tmp_path / "premature.txt"
        transcript.write_text(proc.stdout, encoding="utf-8")
        graded = grade_f26_transcript(transcript)
        assert graded["item_2"] == "pass"
        assert graded["item_3"] == "pass"
        tool_names = {
            tool["function"]["name"] for tool in (hub.requests[0].tools or [])
        }
        assert "Edit" not in tool_names

    def test_evidence_guard_rejects_failed_or_wrong_scope_calls(self) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import (
            _missing_f26_evidence,
            _record_f26_evidence,
            _tool_result_succeeded,
        )

        evidence: set[str] = set()
        _record_f26_evidence(
            evidence,
            name="trunk_invoke_readonly",
            arguments=json.dumps({"tool": "graph_importers", "module": "unrelated.module"}),
            result='{"direct_importers":[]}',
        )
        _record_f26_evidence(
            evidence,
            name="Bash",
            arguments=json.dumps({"command": "false WORK_LEDGER.md"}),
            result="\n(exit 1) command failed",
        )
        _record_f26_evidence(
            evidence,
            name="GoldenRoute",
            arguments=json.dumps({"text": "añade otra cosa a docs/other.md"}),
            result="Proposal P-wrong path='docs/other.md'",
        )
        _record_f26_evidence(
            evidence,
            name="Read",
            arguments=json.dumps({"path": "docs/handoff/GENERATED/not-estado.md"}),
            result="contenido cualquiera",
        )

        assert evidence == set()
        assert _tool_result_succeeded("\n(exit 1) command failed") is False
        assert len(_missing_f26_evidence(evidence)) == 5

    def test_failed_graph_preflight_aborts_without_retrying_or_later_effects(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Una tool requerida puede fallar de verdad (grafo stale, validación
        ambiental). Eso debe producir una corrida gradeable FAIL, no repetir
        el efecto caro hasta agotar proveedor y perder incluso el receipt F2.6."""
        import atlas.core.self_maintenance.f26_agentic_dispatch as dispatch_module

        def failed_dispatch(name: str, arguments: str, *, cwd: Path, orch: Any) -> str:
            if name in {"trunk_invoke_readonly", "GoldenRoute"}:
                return "error: fallo verificable de la tool"
            if name == "Bash":
                return "# WORK LEDGER\n2026-08-12"
            return "fuente leída"

        monkeypatch.setattr(dispatch_module, "_dispatch_tool", failed_dispatch)
        hub = _ScriptedHub([
            _resp(tool_calls=[_tool_call(
                "graph", "trunk_invoke_readonly", tool="graph_importers",
                module="atlas.core.inference_hub",
            )]),
            _resp(text=_FINAL_TEXT_ALL_MARKERS),
        ])

        proc = dispatch_module.agentic_dispatch(
            _REALISTIC_F26_PROMPT, tmp_path, hub=hub, orch=object(),
        )

        assert proc.returncode == 0
        assert len(hub.requests) == 1
        assert proc.stderr == ""
        assert "graph preflight failed" in proc.stdout.casefold()
        transcript = tmp_path / "failed-tools.txt"
        transcript.write_text(proc.stdout, encoding="utf-8")
        graded = grade_f26_transcript(transcript)
        assert graded["item_2"] == "fail"
        assert graded["item_3"] == "fail"

    def test_out_of_schema_edit_is_rejected_before_execution(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import atlas.core.self_maintenance.f26_agentic_dispatch as dispatch_module

        effects: list[str] = []

        def fake_dispatch(name: str, _arguments: str, **_kwargs: Any) -> str:
            effects.append(name)
            return '{"direct_importers":[]}'

        monkeypatch.setattr(dispatch_module, "_dispatch_tool", fake_dispatch)

        victim = tmp_path / "victim.txt"
        victim.write_text("ORIGINAL\n", encoding="utf-8")
        hub = _ScriptedHub([
            _resp(tool_calls=[_tool_call(
                "graph", "trunk_invoke_readonly", tool="graph_importers",
                module="atlas.core.inference_hub",
            )]),
            _resp(tool_calls=[_tool_call(
                "edit-outside-schema",
                "Edit",
                path="victim.txt",
                old_str="ORIGINAL\n",
                new_str="MUTATED\n",
            )]),
            _failed_resp("stop after denial"),
        ])

        proc = dispatch_module.agentic_dispatch(_REALISTIC_F26_PROMPT, tmp_path, hub=hub)

        assert proc.returncode == 1
        assert victim.read_text(encoding="utf-8") == "ORIGINAL\n"
        first_tool_names = {
            tool["function"]["name"] for tool in (hub.requests[0].tools or [])
        }
        assert "Edit" not in first_tool_names
        assert "fuera de la superficie permitida" in proc.stdout
        assert effects == ["trunk_invoke_readonly"]

    def test_explicit_approval_actor_runs_full_golden_route_lifecycle(self) -> None:
        from types import SimpleNamespace

        from atlas.core.self_maintenance.f26_agentic_dispatch import (
            _F26ApprovalPermit,
            _tool_golden_route,
        )

        calls: list[object] = []

        class FakeSession:
            proposal_id = "P-authorized"
            plan = {"path": "docs/continuation/CONTINUATION_STATE.md"}

            def execute(self) -> dict[str, object]:
                calls.append("execute")
                return {"passed": True}

            def approve(self, *, actor: str, decision: str) -> None:
                calls.append(("approve", actor, decision))

            def apply(self) -> object:
                calls.append("apply")
                return SimpleNamespace(
                    status="applied",
                    audit_ref="merkle-authorized",
                    receipt={"receipt_id": "receipt-authorized"},
                )

        class FakeRoute:
            def request(
                self, text: str, *, task_id: str | None = None,
            ) -> FakeSession:
                calls.append(("request", text, task_id))
                return FakeSession()

        class FakeOrchestrator:
            def golden_route(self) -> FakeRoute:
                return FakeRoute()

        permit = _F26ApprovalPermit(
            actor="tomas:f26-explicit", full_prompt_bound=True,
        )
        result = _tool_golden_route(
            'añade la línea "F2.6 ejecutado" al final de docs/continuation/CONTINUATION_STATE.md',
            orch=FakeOrchestrator(),
            approval_permit=permit,
            task_id="f26:test-run",
        )
        repeated = _tool_golden_route(
            'añade la línea "F2.6 ejecutado" al final de docs/continuation/CONTINUATION_STATE.md',
            orch=FakeOrchestrator(),
            approval_permit=permit,
            task_id="f26:test-run",
        )

        assert calls[0][2] == "f26:test-run"
        assert calls[1:] == [
            "execute",
            ("approve", "tomas:f26-explicit", "approve"),
            "apply",
        ]
        assert "status=applied" in result
        assert "approval_ref=merkle-authorized" in result
        assert permit.consumed is True
        assert repeated.startswith("error:")
        assert calls.count("apply") == 1

    def test_approval_permit_is_consumed_before_ambiguous_approve_failure(self) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import (
            _F26ApprovalPermit,
            _tool_golden_route,
        )

        approvals = 0

        class FailingSession:
            proposal_id = "P-ambiguous"
            plan = {"path": "docs/continuation/CONTINUATION_STATE.md"}

            def execute(self) -> dict[str, object]:
                return {"passed": True}

            def approve(self, *, actor: str, decision: str) -> None:
                nonlocal approvals
                del actor, decision
                approvals += 1
                raise RuntimeError("approval outcome ambiguous after receipt")

        class FakeRoute:
            def request(
                self, text: str, *, task_id: str | None = None,
            ) -> FailingSession:
                del text, task_id
                return FailingSession()

        class FakeOrchestrator:
            def golden_route(self) -> FakeRoute:
                return FakeRoute()

        permit = _F26ApprovalPermit(actor="operator", full_prompt_bound=True)
        request = (
            'añade la línea "F2.6 ejecutado" al final de '
            "docs/continuation/CONTINUATION_STATE.md"
        )

        first = _tool_golden_route(
            request, orch=FakeOrchestrator(), approval_permit=permit,
        )
        second = _tool_golden_route(
            request, orch=FakeOrchestrator(), approval_permit=permit,
        )

        assert first.startswith("error:")
        assert second.startswith("error:")
        assert permit.consumed is True
        assert approvals == 1

    def test_default_orchestrator_with_wrong_repo_root_fails_before_request(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import atlas.core.orchestrator as orchestrator_module
        import atlas.core.self_maintenance.f26_agentic_dispatch as dispatch_module

        requested = False

        class Manager:
            _root = tmp_path / "other-repo"

        class Route:
            _manager = Manager()

            def request(self, _text: str, *, task_id: str | None = None) -> object:
                nonlocal requested
                del task_id
                requested = True
                raise AssertionError("request must not cross repository authority")

        class WrongRootOrchestrator:
            def golden_route(self) -> Route:
                return Route()

        monkeypatch.setattr(orchestrator_module, "Orchestrator", WrongRootOrchestrator)
        hub = _ScriptedHub([
            _resp(tool_calls=[_tool_call(
                "golden", "GoldenRoute",
                text=(
                    'añade la línea "F2.6 ejecutado" al final de '
                    "docs/continuation/CONTINUATION_STATE.md"
                ),
            )]),
            _resp(text="reporto el fallo de autoridad"),
        ])

        proc = dispatch_module.agentic_dispatch(
            "prompt", tmp_path, hub=hub,
            golden_route_approval_actor="operator",
        )

        assert proc.returncode == 0
        assert requested is False
        assert "repository authority mismatch" in proc.stdout


class TestDispatchContract:
    def test_return_value_matches_run_f26_dispatch_contract(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Debe poder inyectarse en run_f26 sin cambiar su firma."""
        from atlas.core.self_maintenance.f26_agentic_dispatch import agentic_dispatch
        from atlas.core.self_maintenance.f26_gate import run_f26

        doc = tmp_path / "doc.md"
        doc.write_text(
            "## Cómo ejecutarlo\n\n"
            "```bash\nclaude -p --model sonnet \"pregunta de prueba\"\n```\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "atlas-tests@example.invalid"],
            cwd=tmp_path, check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Atlas Tests"], cwd=tmp_path, check=True,
        )
        subprocess.run(["git", "add", "--", "doc.md"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "fixture: dispatch contract"],
            cwd=tmp_path, check=True,
        )
        # Esta prueba llama ``run_f26`` directamente; su auditoría no debe tocar
        # el ATLAS_HOME vivo del operador.
        monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas-home"))
        hub = _ScriptedHub([_resp(text=_FINAL_TEXT_ALL_MARKERS)])

        def dispatch(prompt: str, cwd: Path) -> subprocess.CompletedProcess[str]:
            return agentic_dispatch(prompt, cwd, hub=hub)

        record = run_f26(tmp_path, doc_path=doc, dispatch=dispatch)

        assert record["success"] is True
        assert record["overall_result"] in {"pass", "fail"}  # gradeó de verdad
        assert record["recorded"] is True


class TestGraphToolUsesTheActiveRepo:
    def test_passes_cwd_as_repo_root_to_freshness_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from types import SimpleNamespace

        import atlas.mcp.graph_server as graph_server_module
        import atlas.memory.project_graph as project_graph_module
        from atlas.core.self_maintenance.f26_agentic_dispatch import (
            _tool_trunk_invoke_readonly,
        )

        db = tmp_path / "graph.kuzu"
        db.touch()
        seen: dict[str, object] = {}

        def fake_build(path: Path, *, repo_root: Path | None = None) -> object:
            seen.update(path=path, repo_root=repo_root)
            tool = SimpleNamespace(name="graph_importers", fn=lambda **_: ["atlas.consumer"])
            manager = SimpleNamespace(list_tools=lambda: [tool])
            return SimpleNamespace(_tool_manager=manager)

        monkeypatch.setattr(project_graph_module, "DEFAULT_GRAPH_DB", db)
        monkeypatch.setattr(graph_server_module, "build_graph_server", fake_build)

        result = _tool_trunk_invoke_readonly(
            "graph_importers", module="atlas.core.inference_hub", cwd=tmp_path,
        )

        assert seen == {"path": db, "repo_root": tmp_path}
        assert json.loads(result) == ["atlas.consumer"]


class TestGrepToolTreatsProviderInputAsData:
    def test_option_like_pattern_is_after_double_dash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import atlas.core.self_maintenance.f26_agentic_dispatch as dispatch_module

        captured: dict[str, object] = {}

        def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured.update(argv=argv, kwargs=kwargs)
            return subprocess.CompletedProcess(argv, returncode=1, stdout="", stderr="")

        monkeypatch.setattr(dispatch_module.subprocess, "run", fake_run)

        result = dispatch_module._tool_grep(
            "--pre=/tmp/provider-controlled-command", cwd=tmp_path,
        )

        assert captured["argv"] == [
            "rg", "--line-number", "--max-count", "20", "--",
            "--pre=/tmp/provider-controlled-command", ".",
        ]
        assert result == "(sin resultados)"


class TestBashToolIsSandboxedReadOnly:
    @pytest.mark.parametrize(
        "command",
        [
            "touch should-not-exist.txt",
            "cat marker.txt",
            "curl https://example.invalid",
            "python -c 'print(1)'",
            "git push",
            "git add -A",
        ],
    )
    def test_bash_rejects_commands_outside_the_grader_allowlist_before_jail(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        command: str,
    ) -> None:
        import atlas.security.bwrap_jail as bwrap_module

        from atlas.core.self_maintenance.f26_agentic_dispatch import _tool_bash

        constructed = False

        def forbidden_jail() -> object:
            nonlocal constructed
            constructed = True
            raise AssertionError("unsafe argv reached the execution boundary")

        monkeypatch.setattr(bwrap_module, "BwrapJail", forbidden_jail)

        result = _tool_bash(command, cwd=tmp_path)

        assert constructed is False
        assert result.startswith("error:")
        assert "allowlist" in result
        assert not (tmp_path / "should-not-exist.txt").exists()

    def test_bash_tool_can_read(self, tmp_path: Path) -> None:
        pytest.importorskip("atlas.security.bwrap_jail")
        from atlas.security.bwrap_jail import BwrapUnavailableError

        from atlas.core.self_maintenance.f26_agentic_dispatch import _tool_bash

        (tmp_path / "WORK_LEDGER.md").write_text("# WORK LEDGER\nhola\n", encoding="utf-8")
        try:
            result = _tool_bash("sed -n 1,120p WORK_LEDGER.md", cwd=tmp_path)
        except BwrapUnavailableError:
            pytest.skip("bwrap no disponible en este host")

        assert "hola" in result


class TestEditToolIsEvidenceOnly:
    def test_edit_call_is_denied_without_mutating_bytes(self, tmp_path: Path) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import _tool_edit

        target = tmp_path / "tracked.md"
        target.write_bytes(b"original\r\n")

        result = _tool_edit(
            "tracked.md", "original\r\n", "mutated\n", cwd=tmp_path,
        )

        assert result.startswith("error:")
        assert "GoldenRoute" in result
        assert target.read_bytes() == b"original\r\n"


class TestToolExceptionBoundary:
    def test_bash_tool_converts_bwrap_unavailable_to_error_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import atlas.security.bwrap_jail as bwrap_module
        from atlas.core.self_maintenance.f26_agentic_dispatch import _tool_bash
        from atlas.security.bwrap_jail import BwrapUnavailableError

        def unavailable_jail() -> object:
            raise BwrapUnavailableError("bwrap no disponible")

        monkeypatch.setattr(bwrap_module, "BwrapJail", unavailable_jail)

        result = _tool_bash("git status --short", cwd=tmp_path)

        assert result.startswith("error:")
        assert "BwrapUnavailableError" in result
        assert "bwrap no disponible" in result

    @pytest.mark.parametrize("failure", [OSError("io roto"), RuntimeError("jail roto")])
    def test_bash_tool_converts_runtime_failures_to_error_result(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        failure: Exception,
    ) -> None:
        import atlas.security.bwrap_jail as bwrap_module
        from atlas.core.self_maintenance.f26_agentic_dispatch import _tool_bash

        class FailingJail:
            def run_command(self, *_args: object, **_kwargs: object) -> object:
                raise failure

        monkeypatch.setattr(bwrap_module, "BwrapJail", FailingJail)

        result = _tool_bash("git status --short", cwd=tmp_path)

        assert result.startswith("error:")
        assert type(failure).__name__ in result
        assert str(failure) in result

    @pytest.mark.parametrize("failure", [OSError("read roto"), RuntimeError("tool rota")])
    def test_dispatch_tool_converts_helper_exceptions_to_error_result(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        failure: Exception,
    ) -> None:
        import atlas.core.self_maintenance.f26_agentic_dispatch as dispatch_module

        def failing_read(_path: str, *, cwd: Path) -> str:
            del cwd
            raise failure

        monkeypatch.setattr(dispatch_module, "_tool_read", failing_read)

        result = dispatch_module._dispatch_tool(
            "Read", json.dumps({"path": "WORK_LEDGER.md"}),
            cwd=tmp_path, orch=None,
        )

        assert result.startswith("error:")
        assert type(failure).__name__ in result
        assert str(failure) in result

    def test_dispatch_exception_becomes_paired_tool_result_and_loop_continues(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import atlas.core.self_maintenance.f26_agentic_dispatch as dispatch_module

        def crashing_dispatch(
            _name: str, _arguments: str, **_kwargs: object,
        ) -> str:
            raise RuntimeError("frontera rota")

        monkeypatch.setattr(dispatch_module, "_dispatch_tool", crashing_dispatch)
        hub = _ScriptedHub([
            _resp(tool_calls=[_tool_call(
                "bash-failure", "Bash", command="git status --short",
            )]),
            _resp(text="La herramienta falló y lo reporto."),
        ])

        proc = dispatch_module.agentic_dispatch("prompt", tmp_path, hub=hub)

        assert proc.returncode == 0
        events = [json.loads(line) for line in proc.stdout.splitlines()]
        tool_result = events[1]["message"]["content"][0]
        assert tool_result == {
            "type": "tool_result",
            "tool_use_id": "bash-failure",
            "content": "error: RuntimeError: frontera rota",
            "is_error": True,
        }
        assert len(hub.requests) == 2
        assert hub.requests[1].messages[-1] == {
            "role": "tool",
            "tool_call_id": "bash-failure",
            "content": "error: RuntimeError: frontera rota",
        }

    def test_negative_exit_code_is_a_failed_tool_result(self) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import (
            _tool_result_succeeded,
        )

        assert _tool_result_succeeded("\n(exit -9) killed") is False


class TestReadToolRespectsProtectedPaths:
    @staticmethod
    def _track(repo: Path, path: str) -> None:
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "add", "-f", "--", path], cwd=repo, check=True)

    def test_refuses_protected_path(self, tmp_path: Path) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import _tool_read

        result = _tool_read("/etc/passwd", cwd=tmp_path)

        assert "error" in result.lower() or "denegado" in result.lower()

    def test_reads_normal_file(self, tmp_path: Path) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import _tool_read

        (tmp_path / "x.md").write_text("contenido real\n", encoding="utf-8")
        self._track(tmp_path, "x.md")

        result = _tool_read("x.md", cwd=tmp_path)

        assert "contenido real" in result

    @pytest.mark.parametrize(
        "relative_path",
        [
            ".codex/config.toml",
            ".claude/settings.local.json",
            ".agents/local.json",
            ".env.production",
        ],
    )
    def test_refuses_local_agent_config_even_if_git_tracked(
        self, tmp_path: Path, relative_path: str,
    ) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import _tool_read

        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("MUST_NOT_LEAK=true\n", encoding="utf-8")
        self._track(tmp_path, relative_path)

        result = _tool_read(relative_path, cwd=tmp_path)

        assert result.startswith("error:")
        assert "MUST_NOT_LEAK" not in result

    def test_refuses_untracked_file(self, tmp_path: Path) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import _tool_read

        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        (tmp_path / "local.txt").write_text("MUST_NOT_LEAK\n", encoding="utf-8")

        result = _tool_read("local.txt", cwd=tmp_path)

        assert result.startswith("error:")
        assert "MUST_NOT_LEAK" not in result

    def test_refuses_symlink_whose_resolved_target_is_protected(
        self, tmp_path: Path,
    ) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import _tool_read

        secret = tmp_path / ".env"
        secret.write_text("ATLAS_SECRET=must-not-leak\n", encoding="utf-8")
        (tmp_path / "apparently-public.md").symlink_to(secret)
        self._track(tmp_path, "apparently-public.md")

        result = _tool_read("apparently-public.md", cwd=tmp_path)

        assert result.startswith("error:")
        assert "must-not-leak" not in result


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


class TestAgenticDispatchDefaultLevel:
    """2026-07-30: la corrida real de F2.6 del 2026-07-29 (sha ee8003d) usó
    el nivel L1 por defecto (nunca se pasó `level=` explícito desde el CLI),
    que resolvió a gemini_free (free-tier) — el driver se quedó SIN TEXTO en
    el turno 3 y nunca intentó 4 de las 6 preguntas. F2.6 mide si un driver
    REALISTA lo lograría, no el modelo más barato disponible -- el propio
    doc de la rúbrica (docs/superpowers/plans/2026-07-17-f26-succession-
    test-PENDIENTE.md) lo diagnosticó como límite de capacidad agéntica, no
    de rúbrica. Default subido a L2 (tier NIM: más capacidad agéntica)."""

    def test_default_level_is_l2_not_l1(self, tmp_path: Path) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import agentic_dispatch

        hub = _ScriptedHub([_resp(text="respuesta final sin tools")])

        agentic_dispatch("pregunta cualquiera", tmp_path, hub=hub)

        assert hub.requests[0].level == InferenceLevel.L2
        assert hub.requests[0].preserve_malformed_tool_calls is True

    def test_explicit_level_override_still_respected(self, tmp_path: Path) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import agentic_dispatch

        hub = _ScriptedHub([_resp(text="respuesta final sin tools")])

        agentic_dispatch("pregunta cualquiera", tmp_path, hub=hub, level=InferenceLevel.L1)

        assert hub.requests[0].level == InferenceLevel.L1

    def test_explicit_run_task_id_is_propagated_to_every_inference(
        self, tmp_path: Path,
    ) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import agentic_dispatch

        hub = _ScriptedHub([
            _resp(tool_calls=[_tool_call("read", "Read", path="WORK_LEDGER.md")]),
            _resp(text="respuesta final"),
        ])

        agentic_dispatch("prompt", tmp_path, hub=hub, task_id="f26:run-123")

        assert {request.task_id for request in hub.requests} == {"f26:run-123"}


class TestAgenticDispatchAuditBoundary:
    def test_default_hub_receives_verified_merkle_logger(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import atlas.core.self_maintenance.f26_agentic_dispatch as dispatch_module
        from atlas.logging.merkle_logger import MerkleLogger

        captured: dict[str, Any] = {}
        scripted = _ScriptedHub([_resp(text="respuesta final")])

        def fake_hub(*, mode: str, **kwargs: Any) -> _ScriptedHub:
            captured.update(mode=mode, **kwargs)
            return scripted

        monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas-home"))
        monkeypatch.setattr(dispatch_module, "InferenceHub", fake_hub)

        proc = dispatch_module.agentic_dispatch("prompt", tmp_path)

        assert proc.returncode == 0
        assert captured["mode"] == "auto"
        assert isinstance(captured.get("merkle"), MerkleLogger)
        assert captured["merkle"].verify_chain()[0] is True

    def test_exact_provider_pin_builds_single_provider_hub(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import atlas.core.self_maintenance.f26_agentic_dispatch as dispatch_module

        captured: dict[str, Any] = {}
        scripted = _ScriptedHub([_resp(text="respuesta final")])

        def fake_hub(*, mode: str, **kwargs: Any) -> _ScriptedHub:
            captured.update(mode=mode, **kwargs)
            return scripted

        monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas-home"))
        monkeypatch.setattr(dispatch_module, "InferenceHub", fake_hub)

        proc = dispatch_module.agentic_dispatch(
            "prompt", tmp_path, level=InferenceLevel.L1,
            provider_name="groq_llama_70b",
        )

        assert proc.returncode == 0
        assert [provider.name for provider in captured["providers"]] == [
            "groq_llama_70b",
        ]

    def test_unknown_provider_pin_stops_before_hub_or_inference(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import atlas.core.self_maintenance.f26_agentic_dispatch as dispatch_module

        hub_constructed = False

        def fake_hub(**_kwargs: Any) -> _ScriptedHub:
            nonlocal hub_constructed
            hub_constructed = True
            return _ScriptedHub([_resp(text="no debe ejecutarse")])

        monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas-home"))
        monkeypatch.setattr(dispatch_module, "InferenceHub", fake_hub)

        proc = dispatch_module.agentic_dispatch(
            "prompt", tmp_path, level=InferenceLevel.L1,
            provider_name="provider_inexistente",
        )

        assert proc.returncode == 1
        assert "provider" in proc.stderr.casefold()
        assert hub_constructed is False

    def test_provider_pin_rejects_level_mismatch_before_hub(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import atlas.core.self_maintenance.f26_agentic_dispatch as dispatch_module

        hub_constructed = False

        def fake_hub(**_kwargs: Any) -> _ScriptedHub:
            nonlocal hub_constructed
            hub_constructed = True
            return _ScriptedHub([_resp(text="no debe ejecutarse")])

        monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas-home"))
        monkeypatch.setattr(dispatch_module, "InferenceHub", fake_hub)

        proc = dispatch_module.agentic_dispatch(
            "prompt", tmp_path, level=InferenceLevel.L2,
            provider_name="groq_llama_70b",
        )

        assert proc.returncode == 1
        assert "L1" in proc.stderr
        assert "L2" in proc.stderr
        assert hub_constructed is False

    def test_broken_merkle_chain_stops_before_inference(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import atlas.core.self_maintenance.f26_agentic_dispatch as dispatch_module

        class _BrokenMerkle:
            def __init__(self, _path: Path) -> None:
                pass

            def verify_chain(self) -> tuple[bool, str]:
                return False, "hash mismatch"

        hub_constructed = False

        def fake_hub(**_kwargs: Any) -> _ScriptedHub:
            nonlocal hub_constructed
            hub_constructed = True
            return _ScriptedHub([_resp(text="no debe ejecutarse")])

        monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas-home"))
        monkeypatch.setattr(dispatch_module, "MerkleLogger", _BrokenMerkle, raising=False)
        monkeypatch.setattr(dispatch_module, "InferenceHub", fake_hub)

        proc = dispatch_module.agentic_dispatch("prompt", tmp_path)

        assert proc.returncode == 1
        assert "merkle" in proc.stderr.casefold()
        assert "hash mismatch" in proc.stderr
        assert hub_constructed is False


class TestAgenticDispatchRejectsAmbiguousToolCalls:
    def test_duplicate_tool_ids_execute_no_tools(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import atlas.core.self_maintenance.f26_agentic_dispatch as dispatch_module

        calls: list[str] = []

        def fake_dispatch(name: str, _arguments: str, **_kwargs: Any) -> str:
            calls.append(name)
            return "ok"

        monkeypatch.setattr(dispatch_module, "_dispatch_tool", fake_dispatch)
        hub = _ScriptedHub([
            _resp(tool_calls=[
                _tool_call("shared", "Read", path="WORK_LEDGER.md"),
                _tool_call("shared", "Grep", pattern="F2.6"),
            ]),
            _resp(text="respuesta que no debe alcanzarse"),
        ])

        proc = dispatch_module.agentic_dispatch("prompt", tmp_path, hub=hub)

        assert proc.returncode == 1
        assert "duplicate" in proc.stderr.casefold()
        assert calls == []

    def test_malformed_tool_arguments_fail_closed_without_crashing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import atlas.core.self_maintenance.f26_agentic_dispatch as dispatch_module

        calls: list[str] = []

        def fake_dispatch(name: str, _arguments: str, **_kwargs: Any) -> str:
            calls.append(name)
            return "ok"

        monkeypatch.setattr(dispatch_module, "_dispatch_tool", fake_dispatch)
        hub = _ScriptedHub([_resp(tool_calls=[{
            "id": "bad-json",
            "name": "Read",
            "arguments": "{",
        }])])

        proc = dispatch_module.agentic_dispatch("prompt", tmp_path, hub=hub)

        assert proc.returncode == 1
        assert "json" in proc.stderr.casefold()
        assert calls == []


class TestSystemPrefixRemindsLiveStateAuthority:
    """2026-07-30, segunda corrida real (3/6): el driver citó
    docs/continuation/CONTINUATION_STATE.md como fuente de estado -- un doc
    histórico, no la autoridad viva. AGENTS.md instrucción 5 ya dice
    literalmente "WORK_LEDGER.md = live WHERE/status and next action only".
    El prefijo debe recordarlo explícito, no dejar que el driver elija
    cualquier doc de continuidad que encuentre."""

    def test_prefix_names_work_ledger_as_live_authority(self, tmp_path: Path) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import agentic_dispatch

        hub = _ScriptedHub([_resp(text="respuesta final sin tools")])

        agentic_dispatch("pregunta cualquiera", tmp_path, hub=hub)

        sent = hub.requests[0].messages[0]["content"]
        assert "WORK_LEDGER" in sent


class TestSystemPrefixRequiresGoldenRouteForDocAppends:
    """2026-07-30, misma corrida: ante 'añade la línea X al final de Y.md'
    el driver llamó Edit directamente sobre un doc rastreado, sin pasar por
    GoldenRoute -- exactamente el failure mode que AGENTS.md 4b nombra como
    "the failure mode the F2.6 succession rubric checks for". El prefijo no
    lo prohibía explícitamente, solo listaba GoldenRoute como una tool más
    entre otras."""

    def test_prefix_requires_golden_route_before_doc_append_edit(self, tmp_path: Path) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import agentic_dispatch

        hub = _ScriptedHub([_resp(text="respuesta final sin tools")])

        agentic_dispatch("pregunta cualquiera", tmp_path, hub=hub)

        sent = hub.requests[0].messages[0]["content"]
        # Frase distintiva de la instrucción de precedencia real, no
        # palabras sueltas que ya aparecían en el prefijo por otra razón
        # (GoldenRoute/Edit/"nunca" ya estaban ahí sin decir esto).
        assert "nunca uses edit directamente" in sent.lower()


class TestSystemPrefixRequiresCitingReadSources:
    """2026-07-30, misma corrida: el driver SÍ leyó docs/design/actor_roles.md
    (tool_use Read real) pero su respuesta final nunca citó esa ruta como
    string -- substrate_markers_found=[] pese a haber consultado la fuente
    correcta. Comportamiento correcto, cita incompleta."""

    def test_prefix_requires_naming_exact_paths_of_sources_cited(self, tmp_path: Path) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import agentic_dispatch

        hub = _ScriptedHub([_resp(text="respuesta final sin tools")])

        agentic_dispatch("pregunta cualquiera", tmp_path, hub=hub)

        sent = hub.requests[0].messages[0]["content"]
        assert "ruta exacta" in sent.lower() or "nombra la ruta" in sent.lower()


class TestSystemPrefixForbidsEmptyStop:
    """2026-07-30: la sesión fallida terminó su turno 3 con `tool_calls=[]`
    Y `text=""` -- ni preguntó nada, ni contestó nada. El prefijo de sistema
    solo decía "cuando termines, responde en texto", sin prohibir
    explícitamente terminar vacío ni exigir que las preguntas numeradas del
    prompt queden todas contestadas antes de parar."""

    def test_prefix_forbids_finishing_with_empty_response(self, tmp_path: Path) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import agentic_dispatch

        hub = _ScriptedHub([_resp(text="respuesta final sin tools")])

        agentic_dispatch("pregunta cualquiera", tmp_path, hub=hub)

        sent = hub.requests[0].messages[0]["content"]
        assert "vac" in sent.lower()  # "vacía"/"vacío" -- prohibición explícita

    def test_prefix_requires_answering_every_numbered_question(self, tmp_path: Path) -> None:
        from atlas.core.self_maintenance.f26_agentic_dispatch import agentic_dispatch

        hub = _ScriptedHub([_resp(text="respuesta final sin tools")])

        agentic_dispatch("pregunta cualquiera", tmp_path, hub=hub)

        sent = hub.requests[0].messages[0]["content"]
        assert "cada" in sent.lower() and ("numerada" in sent.lower() or "pregunta" in sent.lower())
