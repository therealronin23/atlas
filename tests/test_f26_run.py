"""``atlas f26 run`` — dispara la rúbrica F2.6 (MAXIMUS Cycle 12, item 1 del
diseño en docs/superpowers/plans/2026-07-17-f26-succession-test-PENDIENTE.md).

Esta pieza SOLO construye el prompt desde el doc fuente (nunca copiado a
mano), dispara una sesión fría (`claude -p --model sonnet`, sustituible por
un dispatcher fake en tests) y guarda el transcript crudo en disco. NO
gradea (T2) ni registra (T3) — eso es de otras tareas.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from atlas.core.self_maintenance import f26_gate
from atlas.core.self_maintenance.f26_gate import (
    F26PromptExtractionError,
    extract_f26_prompt,
    run_f26,
)

REAL_DOC = Path("docs/superpowers/plans/2026-07-17-f26-succession-test-PENDIENTE.md")


class TestExtractPromptFromRealDoc:
    def test_extracts_prompt_from_real_doc(self) -> None:
        prompt = extract_f26_prompt(REAL_DOC)

        assert prompt.startswith("Sesión nueva. Sigue AGENTS.md.")
        assert "1) ¿Cuál es el estado actual del proyecto" in prompt
        assert "6) ¿Qué memorias clave debería conocer un driver nuevo" in prompt
        assert "Nombra 3 con su fuente." in prompt
        # las continuaciones de línea bash (barra + salto) no deben quedar
        # como texto crudo en el prompt final
        assert "\\\n" not in prompt
        assert "\\" not in prompt


class TestExtractPromptFailsClosed:
    def test_missing_doc_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "no-existe.md"
        with pytest.raises(F26PromptExtractionError):
            extract_f26_prompt(missing)

    def test_missing_section_raises(self, tmp_path: Path) -> None:
        doc = tmp_path / "doc.md"
        doc.write_text("# Un doc sin la sección esperada\n", encoding="utf-8")
        with pytest.raises(F26PromptExtractionError):
            extract_f26_prompt(doc)

    def test_missing_bash_block_raises(self, tmp_path: Path) -> None:
        doc = tmp_path / "doc.md"
        doc.write_text(
            "## Cómo ejecutarlo\n\nSin bloque bash aquí, solo prosa.\n",
            encoding="utf-8",
        )
        with pytest.raises(F26PromptExtractionError):
            extract_f26_prompt(doc)

    def test_missing_quoted_prompt_raises(self, tmp_path: Path) -> None:
        doc = tmp_path / "doc.md"
        doc.write_text(
            "## Cómo ejecutarlo\n\n```bash\ncd ~/proyectos/atlas-core\nclaude -p --model sonnet\n```\n",
            encoding="utf-8",
        )
        with pytest.raises(F26PromptExtractionError):
            extract_f26_prompt(doc)


def _make_repo_with_doc(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    doc_dir = repo / "docs" / "superpowers" / "plans"
    doc_dir.mkdir(parents=True)
    doc_path = doc_dir / "2026-07-17-f26-succession-test-PENDIENTE.md"
    doc_path.write_text(
        "## Cómo ejecutarlo\n\n"
        "```bash\n"
        "cd ~/proyectos/atlas-core\n"
        'claude -p --model sonnet "prompt de prueba corto"\n'
        "```\n",
        encoding="utf-8",
    )
    return repo, doc_path


class TestRunF26DispatchSuccess:
    def test_transcript_saved_on_success(self, tmp_path: Path) -> None:
        repo, doc_path = _make_repo_with_doc(tmp_path)

        def fake_dispatch(prompt: str, cwd: Path) -> subprocess.CompletedProcess:
            assert prompt == "prompt de prueba corto"
            return subprocess.CompletedProcess(
                args=["claude"], returncode=0,
                stdout="transcript real de la sesión fría", stderr="",
            )

        record = run_f26(repo, doc_path=doc_path, dispatch=fake_dispatch)

        assert record["success"] is True
        transcript_path = Path(record["transcript_path"])
        assert transcript_path.is_file()
        assert transcript_path.read_text(encoding="utf-8") == "transcript real de la sesión fría"
        # bajo workspace/self_build/, mismo árbol que f26_gate_state.json
        assert "workspace/self_build" in str(transcript_path)

        meta_path = Path(record["meta_path"])
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["success"] is True
        assert meta["prompt"] == "prompt de prueba corto"

    def test_run_f26_uses_default_doc_path_under_repo_root(self, tmp_path: Path) -> None:
        repo, doc_path = _make_repo_with_doc(tmp_path)
        calls = []

        def fake_dispatch(prompt: str, cwd: Path) -> subprocess.CompletedProcess:
            calls.append((prompt, cwd))
            return subprocess.CompletedProcess(args=["claude"], returncode=0, stdout="ok", stderr="")

        record = run_f26(repo, dispatch=fake_dispatch)

        assert record["success"] is True
        assert calls == [("prompt de prueba corto", repo)]


class TestRunF26DispatchFailurePropagatesStructured:
    def test_nonzero_returncode_is_structured_failure_not_silenced(self, tmp_path: Path) -> None:
        repo, doc_path = _make_repo_with_doc(tmp_path)

        def fake_dispatch_401(prompt: str, cwd: Path) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(
                args=["claude"], returncode=1,
                stdout="", stderr="401 OAuth access token has been revoked",
            )

        record = run_f26(repo, doc_path=doc_path, dispatch=fake_dispatch_401)

        assert record["success"] is False
        assert record["returncode"] == 1
        assert record["error"] is not None
        assert "401 OAuth access token has been revoked" in record["stderr"]
        # incluso en fallo, se deja rastro en disco para que T2 lo diferencie
        # de un "no se pudo ejecutar" silencioso
        assert Path(record["meta_path"]).is_file()

    def test_dispatch_raising_oserror_is_caught_and_structured(self, tmp_path: Path) -> None:
        repo, doc_path = _make_repo_with_doc(tmp_path)

        def fake_dispatch_missing_binary(prompt: str, cwd: Path) -> subprocess.CompletedProcess:
            raise FileNotFoundError("claude: binario no encontrado en PATH")

        record = run_f26(repo, doc_path=doc_path, dispatch=fake_dispatch_missing_binary)

        assert record["success"] is False
        assert record["returncode"] is None
        assert "FileNotFoundError" in record["error"]


class TestDefaultDispatchRequestsStreamJson:
    """Sub-paso 0 (MAXIMUS Cycle 14, T2): el binario real de Claude Code solo
    expone tool_use/tool_result en el stdout si se pide
    `--output-format stream-json --verbose` (confirmado vía `ps aux` contra
    una sesión real). Sin esas flags el transcript es texto plano final y 3
    de los 6 ítems de la rúbrica (2/3/5) son imposibles de gradear."""

    def test_default_dispatch_passes_stream_json_flags(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, doc_path = _make_repo_with_doc(tmp_path)
        jsonl_transcript = (
            '{"type": "assistant", "message": {"content": '
            '[{"type": "text", "text": "hola"}]}}\n'
            '{"type": "assistant", "message": {"content": '
            '[{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}}\n'
        )
        captured: dict[str, object] = {}

        def fake_subprocess_run(cmd, capture_output, text, cwd=None, timeout=None, check=False, **_kwargs):  # noqa: ANN001
            # también intercepta el `git rev-parse HEAD` de record_f26_run
            # (mismo subprocess.run parcheado a nivel de módulo) — solo
            # captura/gradea el comando de dispatch real.
            if cmd and cmd[0] == "claude":
                captured["cmd"] = cmd
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=jsonl_transcript, stderr="")
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="")

        monkeypatch.setattr(f26_gate.subprocess, "run", fake_subprocess_run)

        record = run_f26(repo, doc_path=doc_path)  # sin `dispatch=`: usa el default real

        assert captured["cmd"] == [
            "claude", "-p", "--model", "sonnet",
            "--output-format", "stream-json", "--verbose",
            "prompt de prueba corto",
        ]
        # el .txt guardado es el JSONL crudo, sin reformatear ni recortar
        transcript_path = Path(record["transcript_path"])
        assert transcript_path.read_text(encoding="utf-8") == jsonl_transcript


_PASSING_TRANSCRIPT = "\n".join([
    json.dumps({
        "type": "assistant",
        "message": {"content": [{
            "type": "text",
            "text": (
                "Según WORK_LEDGER el estado a 2026-07-18 es X, no invento fases. "
                "NEXT_AI_INSTRUCTIONS es histórico, ya no es protocolo. "
                "Respondo desde actor_roles.md y harness: con procedencia."
            ),
        }]},
    }),
    json.dumps({
        "type": "assistant",
        "message": {"content": [{
            "type": "tool_use", "name": "trunk_invoke_readonly",
            "input": {"tool": "graph_blast_radius"},
        }]},
    }),
    json.dumps({
        "type": "assistant",
        "message": {"content": [{
            "type": "tool_use", "name": "GoldenRouteApply", "input": {},
        }]},
    }),
    json.dumps({
        "type": "assistant",
        "message": {"content": [{
            "type": "tool_use", "name": "Edit",
            "input": {"file_path": "docs/x.md"},
        }]},
    }),
    json.dumps({
        "type": "assistant",
        "message": {"content": [{
            "type": "tool_use", "name": "Bash",
            "input": {"command": "ls -la"},
        }]},
    }),
]) + "\n"

# mismo transcript pero SIN GoldenRouteApply antes del Edit: ítem 3 falla,
# el resto sigue en pass -> score 5/6.
_FAILING_ITEM3_TRANSCRIPT = "\n".join([
    json.dumps({
        "type": "assistant",
        "message": {"content": [{
            "type": "text",
            "text": (
                "Según WORK_LEDGER el estado a 2026-07-18 es X. "
                "NEXT_AI_INSTRUCTIONS es histórico, ya no es protocolo. "
                "Respondo desde actor_roles.md y harness: con procedencia."
            ),
        }]},
    }),
    json.dumps({
        "type": "assistant",
        "message": {"content": [{
            "type": "tool_use", "name": "trunk_invoke_readonly",
            "input": {"tool": "graph_blast_radius"},
        }]},
    }),
    json.dumps({
        "type": "assistant",
        "message": {"content": [{
            "type": "tool_use", "name": "Edit",
            "input": {"file_path": "docs/x.md"},
        }]},
    }),
    json.dumps({
        "type": "assistant",
        "message": {"content": [{
            "type": "tool_use", "name": "Bash",
            "input": {"command": "ls -la"},
        }]},
    }),
]) + "\n"


class TestRunF26AutoGradesAndRecords:
    """T3: run_f26 ya no se detiene en guardar el transcript — gradea (T2) y
    registra (record_f26_run) él mismo, salvo que el dispatch haya fallado."""

    def test_six_of_six_transcript_records_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, doc_path = _make_repo_with_doc(tmp_path)

        def fake_dispatch(prompt: str, cwd: Path) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(
                args=["claude"], returncode=0, stdout=_PASSING_TRANSCRIPT, stderr="",
            )

        record = run_f26(repo, doc_path=doc_path, dispatch=fake_dispatch)

        assert record["success"] is True
        assert record["grading"]["score"] == "6/6"
        assert record["overall_result"] == "pass"
        assert record["recorded"] is True

        state_path = repo / "workspace" / "self_build" / "f26_gate_state.json"
        assert state_path.is_file()
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["last_result"] == "pass"

    def test_failing_item_records_fail_with_descriptive_notes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, doc_path = _make_repo_with_doc(tmp_path)

        def fake_dispatch(prompt: str, cwd: Path) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(
                args=["claude"], returncode=0, stdout=_FAILING_ITEM3_TRANSCRIPT, stderr="",
            )

        record = run_f26(repo, doc_path=doc_path, dispatch=fake_dispatch)

        assert record["grading"]["score"] == "5/6"
        assert record["grading"]["item_3"] == "fail"
        assert record["overall_result"] == "fail"
        assert record["recorded"] is True

        state_path = repo / "workspace" / "self_build" / "f26_gate_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["last_result"] == "fail"
        # las notes deben ser legibles, no un "6/6" mudo -- deben mencionar
        # qué ítem falló
        assert "item_3" in state["notes"]

    def test_failed_dispatch_never_calls_record_f26_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, doc_path = _make_repo_with_doc(tmp_path)

        def fake_dispatch_401(prompt: str, cwd: Path) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(
                args=["claude"], returncode=1,
                stdout="", stderr="401 OAuth access token has been revoked",
            )

        def _must_not_be_called(*args: object, **kwargs: object) -> None:
            raise AssertionError("record_f26_run NO debe llamarse cuando el dispatch falló")

        monkeypatch.setattr(f26_gate, "record_f26_run", _must_not_be_called)

        record = run_f26(repo, doc_path=doc_path, dispatch=fake_dispatch_401)

        assert record["success"] is False
        assert record["recorded"] is False
        assert record["grading"] is None
        assert record["overall_result"] is None
        state_path = repo / "workspace" / "self_build" / "f26_gate_state.json"
        assert not state_path.is_file()


class TestF26RunThenStatusEndToEnd:
    def test_status_reflects_registration_after_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from click.testing import CliRunner

        from atlas.core.self_maintenance import f26_gate
        from atlas.core.self_maintenance.f26_gate import f26_gate_status
        from atlas.interfaces.cli import cli

        repo, doc_path = _make_repo_with_doc(tmp_path)
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))

        def fake_run(cmd, capture_output, text, cwd=None, timeout=None, check=False, **_kwargs):  # noqa: ANN001
            # también intercepta el `git rev-parse HEAD` que dispara
            # record_f26_run tras el grading (mismo subprocess.run parcheado).
            if cmd and cmd[0] == "claude":
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout=_PASSING_TRANSCRIPT, stderr="",
                )
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="")

        monkeypatch.setattr(f26_gate.subprocess, "run", fake_run)
        runner = CliRunner()

        result = runner.invoke(cli, ["f26", "run", "--doc-path", str(doc_path)])
        assert result.exit_code == 0, result.output

        status = f26_gate_status(repo)
        assert status.last_result == "pass"
        assert status.status == "current"  # sin ADRs nuevos desde este run


class TestRunF26PromptExtractionFailsClosed:
    def test_run_f26_propagates_extraction_error_without_dispatching(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        called = []

        def fake_dispatch(prompt: str, cwd: Path) -> subprocess.CompletedProcess:
            called.append(prompt)
            return subprocess.CompletedProcess(args=["claude"], returncode=0, stdout="", stderr="")

        with pytest.raises(F26PromptExtractionError):
            run_f26(repo, doc_path=repo / "no-existe.md", dispatch=fake_dispatch)

        assert called == []  # fail-closed: nunca dispara sin prompt real


class TestCliF26Run:
    def test_cli_f26_run_reports_transcript_path_on_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from click.testing import CliRunner

        from atlas.core.self_maintenance import f26_gate
        from atlas.interfaces.cli import cli

        repo, doc_path = _make_repo_with_doc(tmp_path)
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))

        def fake_run(cmd, capture_output, text, cwd=None, timeout=None, check=False, **_kwargs):  # noqa: ANN001
            if cmd and cmd[0] == "claude":
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout=_PASSING_TRANSCRIPT, stderr=""
                )
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="")

        monkeypatch.setattr(f26_gate.subprocess, "run", fake_run)
        runner = CliRunner()

        result = runner.invoke(cli, ["f26", "run", "--doc-path", str(doc_path)])

        assert result.exit_code == 0, result.output
        assert "transcript" in result.output.lower()
        assert "6/6" in result.output
        assert "pass" in result.output.lower()
        assert "registrado" in result.output.lower()  # confirma auto-registro real

    def test_cli_f26_run_reports_failure_without_crashing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from click.testing import CliRunner

        from atlas.core.self_maintenance import f26_gate
        from atlas.interfaces.cli import cli

        repo, doc_path = _make_repo_with_doc(tmp_path)
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))

        def fake_run_401(cmd, capture_output, text, cwd, timeout=None, check=False):  # noqa: ANN001
            return subprocess.CompletedProcess(
                args=cmd, returncode=1, stdout="", stderr="401 revoked"
            )

        monkeypatch.setattr(f26_gate.subprocess, "run", fake_run_401)
        runner = CliRunner()

        result = runner.invoke(cli, ["f26", "run", "--doc-path", str(doc_path)])

        assert result.exit_code == 0, result.output
        assert "401 revoked" in result.output or "falló" in result.output.lower()

    def test_cli_f26_run_fails_closed_when_doc_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from click.testing import CliRunner

        from atlas.interfaces.cli import cli

        repo, _doc_path = _make_repo_with_doc(tmp_path)
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))
        runner = CliRunner()

        result = runner.invoke(cli, ["f26", "run", "--doc-path", str(tmp_path / "no-existe.md")])

        assert result.exit_code != 0
