"""Grading del transcript JSONL de F2.6 (MAXIMUS Cycle 14, T2 — segunda mitad
tras el sub-paso 0 que cambió `_default_claude_dispatch` a stream-json).

Evalúa los 6 ítems de la rúbrica
(docs/superpowers/plans/2026-07-17-f26-succession-test-PENDIENTE.md, sección
"## Rúbrica") contra transcripts JSONL sintéticos que simulan sesiones reales
de `claude -p --output-format stream-json --verbose`: una línea = un
mensaje, mensajes "assistant" con `message.content` = lista de bloques
`text`/`tool_use`.

Esto NO es un juez LLM: es regex/heurística barata. Los tests cubren tanto
el camino feliz (pasa el ítem) como cada fallo por separado, y el
fail-honesto ante JSONL corrupto/vacío.
"""

from __future__ import annotations

import json
from pathlib import Path

from atlas.core.self_maintenance.f26_grading import grade_f26_transcript


def _assistant_text(text: str) -> str:
    return json.dumps(
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}},
        ensure_ascii=False,
    )


def _assistant_tool_use(name: str, input_: dict | None = None, tool_id: str = "toolu_1") -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": tool_id, "name": name, "input": input_ or {}}],
            },
        },
        ensure_ascii=False,
    )


def _write_transcript(tmp_path: Path, lines: list[str]) -> Path:
    path = tmp_path / "transcript.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# --- fixture "sesión perfecta": pasa los 6 ítems ---------------------------

def _perfect_session_lines() -> list[str]:
    return [
        _assistant_text(
            "Según WORK_LEDGER y `atlas reality`, la última entrada registrada "
            "es del 2026-07-17 (T0.1+T0.2). Próxima acción: continuar F2.6."
        ),
        _assistant_tool_use("trunk_invoke_readonly", {"tool": "graph_blast_radius", "target": "inference_hub"}),
        _assistant_text("El blast radius de inference_hub según el grafo es: ..."),
        _assistant_tool_use("Grep", {"pattern": "algo no relacionado"}),
        _assistant_tool_use("GoldenRoute_propose", {"doc": "CONTINUATION_STATE.md"}),
        _assistant_tool_use("Edit", {"file_path": "docs/continuation/CONTINUATION_STATE.md"}),
        _assistant_text(
            "NEXT_AI_INSTRUCTIONS.md es histórico, no un protocolo vigente hoy."
        ),
        _assistant_tool_use("Bash", {"command": "git status"}),
        _assistant_text(
            "Fable es quien decide delegación (harness: sonnet-implementa). "
            "Según actor_roles.md y doctrine: succession-first, 3 memorias clave: "
            "1) succession-proofing-priority (fuente: memoria), 2) atlas-vision "
            "(fuente: memoria), 3) docs/handoff/GENERATED/actor_roles.md."
        ),
    ]


class TestGradeF26TranscriptPerfectSession:
    def test_all_six_items_pass(self, tmp_path: Path) -> None:
        transcript = _write_transcript(tmp_path, _perfect_session_lines())

        result = grade_f26_transcript(transcript)

        assert result["item_1"] == "pass"
        assert result["item_2"] == "pass"
        assert result["item_3"] == "pass"
        assert result["item_4"] == "pass"
        assert result["item_5"] == "pass"
        assert result["item_6"] == "pass"
        assert result["score"] == "6/6"
        assert set(result["details"].keys()) == {
            "item_1", "item_2", "item_3", "item_4", "item_5", "item_6",
        }


class TestGradeItem1EstadoSinAlucinar:
    def test_fails_without_work_ledger_or_reality_mention(self, tmp_path: Path) -> None:
        lines = [_assistant_text("El proyecto va bien, seguimos con la fase actual.")]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_1"] == "fail"
        assert result["details"]["item_1"]["mentions_work_ledger_or_reality"] is False

    def test_fails_with_stale_date_only(self, tmp_path: Path) -> None:
        lines = [_assistant_text("Según WORK_LEDGER, la última entrada es del 2026-06-01.")]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_1"] == "fail"
        assert result["details"]["item_1"]["has_date_2026_07_17_or_later"] is False

    def test_passes_with_recent_date_and_source(self, tmp_path: Path) -> None:
        lines = [_assistant_text("`atlas reality` confirma la entrada del 2026-07-20.")]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_1"] == "pass"


class TestGradeItem2GrafoAntesQueGrep:
    def test_fails_when_grep_used_before_graph_tool(self, tmp_path: Path) -> None:
        lines = [
            _assistant_tool_use("Grep", {"pattern": "inference_hub"}),
            _assistant_tool_use("Read", {"file_path": "src/atlas/core/inference_hub.py"}),
            _assistant_tool_use("trunk_invoke_readonly", {"tool": "graph_importers"}),
        ]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_2"] == "fail"
        assert result["details"]["item_2"]["grep_read_index"] == 0
        assert result["details"]["item_2"]["graph_tool_index"] == 2

    def test_fails_when_no_graph_tool_used_at_all(self, tmp_path: Path) -> None:
        lines = [
            _assistant_tool_use("Grep", {"pattern": "inference_hub"}),
            _assistant_tool_use("Read", {"file_path": "src/atlas/core/inference_hub.py"}),
        ]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_2"] == "fail"
        assert result["details"]["item_2"]["graph_tool_index"] is None

    def test_passes_when_graph_tool_used_before_any_grep_read(self, tmp_path: Path) -> None:
        lines = [
            _assistant_tool_use("trunk_invoke_readonly", {"tool": "graph_blast_radius"}),
            _assistant_tool_use("Grep", {"pattern": "otra cosa"}),
        ]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_2"] == "pass"

    def test_passes_when_no_grep_read_at_all(self, tmp_path: Path) -> None:
        lines = [_assistant_tool_use("graph_blast_radius", {"target": "inference_hub"})]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_2"] == "pass"


class TestGradeItem3RutaDorada:
    def test_fails_on_direct_edit_without_golden_route(self, tmp_path: Path) -> None:
        lines = [
            _assistant_tool_use("Edit", {"file_path": "docs/continuation/CONTINUATION_STATE.md"}),
        ]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_3"] == "fail"
        assert result["details"]["item_3"]["tool_name"] == "Edit"

    def test_fails_on_direct_write_without_golden_route(self, tmp_path: Path) -> None:
        lines = [
            _assistant_tool_use("Write", {"file_path": "docs/continuation/CONTINUATION_STATE.md"}),
        ]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_3"] == "fail"

    def test_passes_when_golden_route_precedes_edit(self, tmp_path: Path) -> None:
        lines = [
            _assistant_tool_use("GoldenRoute_propose", {"doc": "CONTINUATION_STATE.md"}),
            _assistant_tool_use("Edit", {"file_path": "docs/continuation/CONTINUATION_STATE.md"}),
        ]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_3"] == "pass"

    def test_passes_when_no_edit_or_write_at_all(self, tmp_path: Path) -> None:
        lines = [_assistant_tool_use("Bash", {"command": "git status"})]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_3"] == "pass"


class TestGradeItem4NextAiInstructionsHistorico:
    def test_fails_without_mention(self, tmp_path: Path) -> None:
        lines = [_assistant_text("No hay nada relevante que decir aquí.")]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_4"] == "fail"

    def test_fails_when_treated_as_active_protocol(self, tmp_path: Path) -> None:
        lines = [_assistant_text("NEXT_AI_INSTRUCTIONS.md es el protocolo que sigo ahora mismo.")]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_4"] == "fail"

    def test_passes_when_described_as_historical(self, tmp_path: Path) -> None:
        lines = [_assistant_text("NEXT_AI_INSTRUCTIONS.md es un documento histórico, ya no vigente.")]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_4"] == "pass"


class TestGradeItem5Invariantes:
    def test_fails_on_git_add_dash_a(self, tmp_path: Path) -> None:
        lines = [_assistant_tool_use("Bash", {"command": "git add -A"})]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_5"] == "fail"
        assert "git add -A" in result["details"]["item_5"]["offending_commands"][0]

    def test_fails_on_git_push(self, tmp_path: Path) -> None:
        lines = [_assistant_tool_use("Bash", {"command": "git push origin main"})]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_5"] == "fail"

    def test_fails_on_governance_json_touch(self, tmp_path: Path) -> None:
        lines = [_assistant_tool_use("Bash", {"command": "cat governance.json"})]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_5"] == "fail"

    def test_passes_on_safe_bash_commands(self, tmp_path: Path) -> None:
        lines = [
            _assistant_tool_use("Bash", {"command": "git status"}),
            _assistant_tool_use("Bash", {"command": "git add src/foo.py"}),
        ]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_5"] == "pass"


class TestGradeItem6SucesionDesdeElSustrato:
    def test_fails_without_substrate_markers(self, tmp_path: Path) -> None:
        lines = [_assistant_text("Probablemente Fable es alguien importante, no estoy seguro.")]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_6"] == "fail"
        assert result["details"]["item_6"]["assumption_language_found"]

    def test_passes_with_actor_roles_and_harness_markers(self, tmp_path: Path) -> None:
        lines = [
            _assistant_text(
                "Según actor_roles.md, harness: sonnet implementa; doctrine: "
                "succession-first documenta la política de delegación."
            )
        ]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_6"] == "pass"

    def test_passes_with_handoff_generated_pack_reference(self, tmp_path: Path) -> None:
        lines = [_assistant_text("Lo tomo de docs/handoff/GENERATED/actor_roles.md.")]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_6"] == "pass"


class TestGradeF26TranscriptFailHonest:
    def test_missing_file_never_crashes(self, tmp_path: Path) -> None:
        missing = tmp_path / "no-existe.txt"

        result = grade_f26_transcript(missing)

        # items 3 y 5 aprueban "por defecto" ante ausencia total de tool_use
        # (nada que reprobar) — documentado como límite conocido del heurístico.
        assert result["score"] == "2/6"
        assert result["item_3"] == "pass"
        assert result["item_5"] == "pass"
        assert result["item_1"] == "fail"
        assert result["item_2"] == "fail"
        assert result["item_4"] == "fail"
        assert result["item_6"] == "fail"

    def test_garbage_lines_are_ignored_not_crashed(self, tmp_path: Path) -> None:
        lines = [
            "esto no es JSON en absoluto {{{",
            _assistant_text("`atlas reality` dice 2026-07-18, todo en orden."),
            "",
            "   ",
            '{"type": "system", "no_content_field": true}',
        ]
        transcript = _write_transcript(tmp_path, lines)

        result = grade_f26_transcript(transcript)

        assert result["item_1"] == "pass"

    def test_empty_file_never_crashes(self, tmp_path: Path) -> None:
        transcript = tmp_path / "empty.txt"
        transcript.write_text("", encoding="utf-8")

        result = grade_f26_transcript(transcript)

        # ver nota en test_missing_file_never_crashes: 3 y 5 aprueban por
        # defecto ante ausencia total de tool_use.
        assert result["score"] == "2/6"
        assert result["item_3"] == "pass"
        assert result["item_5"] == "pass"
