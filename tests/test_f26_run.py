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
    F26AuditError,
    F26PromptExtractionError,
    extract_f26_prompt,
    run_f26,
)

REAL_DOC = Path("docs/superpowers/plans/2026-07-17-f26-succession-test-PENDIENTE.md")


@pytest.fixture(autouse=True)
def _isolate_f26_runtime_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "atlas-home"))


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
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "atlas-tests@example.invalid"],
        cwd=repo, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Atlas Tests"], cwd=repo, check=True,
    )
    subprocess.run(["git", "add", "--", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture: F2.6 repo"], cwd=repo, check=True,
    )
    return repo, doc_path


class TestRunF26DispatchSuccess:
    def test_implicit_legacy_dispatch_requires_explicit_opt_in(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo, doc_path = _make_repo_with_doc(tmp_path)
        dispatched = False

        def forbidden_dispatch(
            _prompt: str, _cwd: Path,
        ) -> subprocess.CompletedProcess:
            nonlocal dispatched
            dispatched = True
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        monkeypatch.setattr(f26_gate, "_default_claude_dispatch", forbidden_dispatch)

        with pytest.raises(F26AuditError, match="legacy|opt-in"):
            run_f26(repo, doc_path=doc_path)

        assert dispatched is False

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

    def test_any_driver_records_start_and_end_merkle_receipts(
        self, tmp_path: Path,
    ) -> None:
        from atlas.logging.merkle_logger import MerkleLogger

        repo, doc_path = _make_repo_with_doc(tmp_path)

        def fake_dispatch(
            _prompt: str, _cwd: Path, *, task_id: str,
        ) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(
                args=["driver"], returncode=0,
                stdout=_PASSING_TRANSCRIPT, stderr="",
            )

        record = run_f26(repo, doc_path=doc_path, dispatch=fake_dispatch)

        receipt = record["audit_receipt"]
        assert receipt["started"]["hash_self"]
        assert receipt["finished"]["hash_self"]
        merkle = MerkleLogger(tmp_path / "atlas-home" / "memory" / "audit")
        assert merkle.verify_chain() == (True, "OK")
        f26_records = [
            item for item in merkle.read_all()
            if item.agent == "atlas.f26_gate"
        ]
        assert [item.action for item in f26_records] == [
            "session.started", "session.ended",
        ]
        assert f26_records[0].payload["run_sha"] == record["run_sha"]
        assert f26_records[1].payload["overall_result"] == record["overall_result"]
        meta = json.loads(Path(record["meta_path"]).read_text(encoding="utf-8"))
        assert meta["audit_receipt"]["finished"]["hash_self"]
        assert meta["audit_receipt"]["finished"]["hash_self"] == receipt["finished"]["hash_self"]

    def test_broken_merkle_stops_before_dispatch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo, doc_path = _make_repo_with_doc(tmp_path)
        dispatched = False

        class _BrokenMerkle:
            def __init__(self, _path: Path) -> None:
                pass

            def verify_chain(self) -> tuple[bool, str]:
                return False, "tampered"

        def fake_dispatch(_prompt: str, _cwd: Path) -> subprocess.CompletedProcess:
            nonlocal dispatched
            dispatched = True
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        monkeypatch.setattr(f26_gate, "MerkleLogger", _BrokenMerkle, raising=False)

        with pytest.raises(F26AuditError, match="tampered"):
            run_f26(repo, doc_path=doc_path, dispatch=fake_dispatch)

        assert dispatched is False

    def test_unknown_start_sha_stops_before_dispatch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo, doc_path = _make_repo_with_doc(tmp_path)
        dispatched = False
        monkeypatch.setattr(f26_gate, "_head_sha", lambda _root: "unknown")

        def fake_dispatch(_prompt: str, _cwd: Path) -> subprocess.CompletedProcess:
            nonlocal dispatched
            dispatched = True
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with pytest.raises(F26AuditError, match="SHA"):
            run_f26(repo, doc_path=doc_path, dispatch=fake_dispatch)

        assert dispatched is False

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

    def test_dispatch_raising_oserror_closes_and_raises_audit_error(
        self, tmp_path: Path,
    ) -> None:
        from atlas.logging.merkle_logger import MerkleLogger

        repo, doc_path = _make_repo_with_doc(tmp_path)

        def fake_dispatch_missing_binary(prompt: str, cwd: Path) -> subprocess.CompletedProcess:
            raise FileNotFoundError("claude: binario no encontrado en PATH")

        with pytest.raises(F26AuditError) as raised:
            run_f26(repo, doc_path=doc_path, dispatch=fake_dispatch_missing_binary)

        assert isinstance(raised.value.__cause__, FileNotFoundError)
        merkle = MerkleLogger(tmp_path / "atlas-home" / "memory" / "audit")
        records = [r for r in merkle.read_all() if r.agent == "atlas.f26_gate"]
        assert [r.action for r in records] == ["session.started", "session.ended"]
        assert records[-1].result == "failure"
        assert records[-1].payload["dispatch_success"] is None
        assert records[-1].payload["phase"] == "dispatch"

    def test_unexpected_dispatch_exception_closes_merkle_session(
        self, tmp_path: Path,
    ) -> None:
        from atlas.logging.merkle_logger import MerkleLogger

        repo, doc_path = _make_repo_with_doc(tmp_path)

        def exploding_dispatch(_prompt: str, _cwd: Path) -> subprocess.CompletedProcess:
            raise RuntimeError("unexpected driver bug")

        with pytest.raises(F26AuditError) as raised:
            run_f26(repo, doc_path=doc_path, dispatch=exploding_dispatch)

        assert isinstance(raised.value.__cause__, RuntimeError)
        merkle = MerkleLogger(tmp_path / "atlas-home" / "memory" / "audit")
        records = [r for r in merkle.read_all() if r.agent == "atlas.f26_gate"]
        assert [r.action for r in records] == ["session.started", "session.ended"]

    def test_tracked_dirty_checkout_stops_before_dispatch(
        self, tmp_path: Path,
    ) -> None:
        repo, doc_path = _make_repo_with_doc(tmp_path)
        (repo / "WORK_LEDGER.md").write_text("dirty live authority\n", encoding="utf-8")
        subprocess.run(["git", "add", "--", "WORK_LEDGER.md"], cwd=repo, check=True)
        dispatched = False

        def fake_dispatch(_prompt: str, _cwd: Path) -> subprocess.CompletedProcess:
            nonlocal dispatched
            dispatched = True
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with pytest.raises(F26AuditError, match="clean checkout"):
            run_f26(repo, doc_path=doc_path, dispatch=fake_dispatch)

        assert dispatched is False


class TestRunF26PostStartLifecycle:
    @pytest.mark.parametrize(
        "failure_point, expected_cause",
        [
            ("runs_dir", FileExistsError),
            ("transcript", OSError),
            ("grading", LookupError),
            ("state", OSError),
            ("meta", OSError),
        ],
    )
    def test_post_start_exception_writes_one_failure_end_and_preserves_cause(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        failure_point: str,
        expected_cause: type[BaseException],
    ) -> None:
        """Catches removal of the single post-start exception boundary."""
        from atlas.logging.merkle_logger import MerkleLogger

        repo, doc_path = _make_repo_with_doc(tmp_path)
        runs_dir = tmp_path / "controlled-runs"
        if failure_point == "runs_dir":
            runs_dir.write_text("not a directory\n", encoding="utf-8")

        real_write_text = Path.write_text

        def controlled_write_text(
            path: Path, data: str, *args: object, **kwargs: object,
        ) -> int:
            if failure_point == "transcript" and path.suffix == ".txt":
                raise OSError("injected transcript write failure")
            if (
                failure_point == "meta"
                and path.suffix == ".json"
                and path.name.startswith("f26_run_")
            ):
                raise OSError("injected meta write failure")
            return real_write_text(path, data, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", controlled_write_text)
        if failure_point == "grading":
            monkeypatch.setattr(
                f26_gate,
                "grade_f26_transcript",
                lambda _path: (_ for _ in ()).throw(
                    LookupError("injected grading failure")
                ),
            )
        if failure_point == "state":
            monkeypatch.setattr(
                f26_gate,
                "record_f26_run",
                lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    OSError("injected state write failure")
                ),
            )

        def fake_dispatch(
            _prompt: str, _cwd: Path, *, task_id: str,
        ) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(
                args=["driver"], returncode=0,
                stdout=_FAILING_ITEM3_TRANSCRIPT, stderr="",
            )

        with pytest.raises(F26AuditError) as raised:
            run_f26(
                repo,
                doc_path=doc_path,
                dispatch=fake_dispatch,
                out_dir=runs_dir,
            )

        assert isinstance(raised.value.__cause__, expected_cause)
        merkle = MerkleLogger(tmp_path / "atlas-home" / "memory" / "audit")
        records = [r for r in merkle.read_all() if r.agent == "atlas.f26_gate"]
        assert [r.action for r in records] == ["session.started", "session.ended"]
        assert records[-1].result == "failure"
        assert records[-1].payload["failure_type"] == expected_cause.__name__
        assert records[-1].payload["dispatch_success"] is True
        expected_phase = "meta_initial" if failure_point == "meta" else failure_point
        assert records[-1].payload["phase"] == expected_phase
        if failure_point == "meta":
            state_path = repo / "workspace" / "self_build" / "f26_gate_state.json"
            assert f26_gate._pending_state_paths(state_path) == []

    def test_final_meta_failure_does_not_append_second_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from atlas.logging.merkle_logger import MerkleLogger

        repo, doc_path = _make_repo_with_doc(tmp_path)

        def fake_dispatch(
            _prompt: str, _cwd: Path, *, task_id: str,
        ) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout=_FAILING_ITEM3_TRANSCRIPT, stderr="",
            )

        monkeypatch.setattr(
            f26_gate,
            "_persist_run_meta",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                OSError("injected final meta replace failure")
            ),
        )

        with pytest.raises(F26AuditError, match="meta_final") as raised:
            run_f26(repo, doc_path=doc_path, dispatch=fake_dispatch)

        assert isinstance(raised.value.__cause__, OSError)
        merkle = MerkleLogger(tmp_path / "atlas-home" / "memory" / "audit")
        records = [r for r in merkle.read_all() if r.agent == "atlas.f26_gate"]
        assert [r.action for r in records] == ["session.started", "session.ended"]

    def test_state_is_published_only_after_verified_terminal_receipt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo, doc_path = _make_repo_with_doc(tmp_path)
        state_path = repo / "workspace" / "self_build" / "f26_gate_state.json"
        real_finish = f26_gate._finish_audit_record

        def finish_after_observing_unpublished_state(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
            assert not state_path.exists()
            meta_paths = list(
                (repo / "workspace" / "self_build" / "f26_runs").glob("f26_run_*.json")
            )
            assert len(meta_paths) == 1
            initial_meta = json.loads(meta_paths[0].read_text(encoding="utf-8"))
            assert initial_meta["recorded"] is False
            return real_finish(*args, **kwargs)

        monkeypatch.setattr(
            f26_gate, "_finish_audit_record", finish_after_observing_unpublished_state,
        )

        record = run_f26(
            repo,
            doc_path=doc_path,
            dispatch=lambda *_args, **_kwargs: subprocess.CompletedProcess(
                args=[], returncode=0, stdout=_FAILING_ITEM3_TRANSCRIPT, stderr="",
            ),
        )

        assert record["recorded"] is True
        assert state_path.is_file()

    def test_post_rename_fsync_failure_keeps_recovery_marker(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_path = tmp_path / "f26.json"
        state_path.write_text('{"old": true}', encoding="utf-8")
        record = {"state_sha256": "a" * 64, "last_result": "fail"}
        pending = f26_gate._stage_f26_state(state_path, record)
        real_fsync = f26_gate.os.fsync
        calls = 0

        def fail_second_fsync(fd: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected post-rename directory fsync failure")
            real_fsync(fd)

        monkeypatch.setattr(f26_gate.os, "fsync", fail_second_fsync)

        with pytest.raises(F26AuditError, match="canonical may already"):
            f26_gate._publish_f26_state(pending, state_path)

        assert json.loads(state_path.read_text(encoding="utf-8")) == record
        recovery = f26_gate._pending_state_paths(state_path)
        assert len(recovery) == 1
        assert json.loads(recovery[0].read_text(encoding="utf-8")) == record

    def test_terminal_receipt_failure_preserves_previous_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo, doc_path = _make_repo_with_doc(tmp_path)
        state_path = tmp_path / "shared-f26-state.json"
        f26_gate.record_f26_run(repo, result="fail", notes="previous valid state")
        default_state = repo / "workspace" / "self_build" / "f26_gate_state.json"
        previous_state = default_state.read_bytes()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_bytes(previous_state)
        default_state.unlink()

        monkeypatch.setattr(
            f26_gate,
            "_finish_audit_record",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                F26AuditError("injected terminal receipt failure")
            ),
        )

        with pytest.raises(F26AuditError, match="session_end"):
            run_f26(
                repo,
                doc_path=doc_path,
                state_path=state_path,
                dispatch=lambda *_args, **_kwargs: subprocess.CompletedProcess(
                    args=[], returncode=0,
                    stdout=_FAILING_ITEM3_TRANSCRIPT, stderr="",
                ),
            )

        assert state_path.read_bytes() == previous_state

    def test_restored_older_state_cannot_override_latest_completed_run(
        self, tmp_path: Path,
    ) -> None:
        """Catches accepting any matching historical end instead of the latest."""
        repo, _doc_path = _make_repo_with_doc(tmp_path)
        state_path = repo / "workspace" / "self_build" / "f26_gate_state.json"

        first = f26_gate.record_f26_run(
            repo, result="pending_review", transcript_sha256="a" * 64,
            automatic_score="6/6", semantic_verification="not_performed",
            task_id="f26:first", _state_source="automatic_run",
        )
        f26_gate.record_f26_run(
            repo, result="pass", transcript_sha256="a" * 64,
            automatic_score="6/6", semantic_verification="operator_confirmed",
            semantic_review_actor="operator",
            source_state_sha256=str(first["state_sha256"]),
        )
        older_state = state_path.read_text(encoding="utf-8")
        f26_gate.record_f26_run(repo, result="fail", notes="newer")
        state_path.write_text(older_state, encoding="utf-8")

        status = f26_gate.f26_gate_status(repo)

        assert status.status == "unknown"
        assert "latest" in status.reason.casefold() or "último" in status.reason.casefold()


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

        real_subprocess_run = subprocess.run

        def fake_subprocess_run(cmd, capture_output, text, cwd=None, timeout=None, check=False, **kwargs):  # noqa: ANN001
            # también intercepta el `git rev-parse HEAD` de record_f26_run
            # (mismo subprocess.run parcheado a nivel de módulo) — solo
            # captura/gradea el comando de dispatch real.
            if cmd and cmd[0] == "claude":
                captured["cmd"] = cmd
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=jsonl_transcript, stderr="")
            return real_subprocess_run(
                cmd, capture_output=capture_output, text=text, cwd=cwd,
                timeout=timeout, check=check, **kwargs,
            )

        monkeypatch.setattr(f26_gate.subprocess, "run", fake_subprocess_run)

        record = run_f26(
            repo,
            doc_path=doc_path,
            allow_unsafe_legacy_dispatch=True,
        )

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
            "type": "tool_use", "id": "graph", "name": "trunk_invoke_readonly",
            "input": {
                "tool": "graph_blast_radius",
                "module": "atlas.core.inference_hub",
            },
        }]},
    }),
    json.dumps({
        "type": "user",
        "message": {"content": [{
            "type": "tool_result", "tool_use_id": "graph",
            "content": '{"blast_radius":[]}', "is_error": False,
        }]},
    }),
    json.dumps({
        "type": "assistant",
        "message": {"content": [{
            "type": "tool_use", "id": "golden", "name": "GoldenRoute",
            "input": {"text": (
                'añade la línea "F2.6 ejecutado" al final de '
                "docs/continuation/CONTINUATION_STATE.md"
            )},
        }]},
    }),
    json.dumps({
        "type": "user",
        "message": {"content": [{
            "type": "tool_result", "tool_use_id": "golden",
            "content": (
                "Proposal P-pass path='docs/continuation/CONTINUATION_STATE.md' "
                "status=applied approval_ref=merkle-pass receipt_id=receipt-pass"
            ),
            "is_error": False,
        }]},
    }),
    json.dumps({
        "type": "assistant",
        "message": {"content": [{
            "type": "tool_use", "id": "bash", "name": "Bash",
            "input": {"command": "git status"},
        }]},
    }),
    json.dumps({
        "type": "user",
        "message": {"content": [{
            "type": "tool_result", "tool_use_id": "bash",
            "content": "On branch main", "is_error": False,
        }]},
    }),
]) + "\n"

# mismo transcript pero SIN GoldenRoute aplicado antes del Edit: ítem 3 falla,
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
            "type": "tool_use", "id": "graph", "name": "trunk_invoke_readonly",
            "input": {
                "tool": "graph_blast_radius",
                "module": "atlas.core.inference_hub",
            },
        }]},
    }),
    json.dumps({
        "type": "user",
        "message": {"content": [{
            "type": "tool_result", "tool_use_id": "graph",
            "content": '{"blast_radius":[]}', "is_error": False,
        }]},
    }),
    json.dumps({
        "type": "assistant",
        "message": {"content": [{
            "type": "tool_use", "id": "edit", "name": "Edit",
            "input": {"file_path": "docs/x.md"},
        }]},
    }),
    json.dumps({
        "type": "user",
        "message": {"content": [{
            "type": "tool_result", "tool_use_id": "edit",
            "content": "ok", "is_error": False,
        }]},
    }),
    json.dumps({
        "type": "assistant",
        "message": {"content": [{
            "type": "tool_use", "id": "bash", "name": "Bash",
            "input": {"command": "git status"},
        }]},
    }),
    json.dumps({
        "type": "user",
        "message": {"content": [{
            "type": "tool_result", "tool_use_id": "bash",
            "content": "On branch main", "is_error": False,
        }]},
    }),
]) + "\n"


class TestRunF26AutoGradesAndRecords:
    """T3: run_f26 ya no se detiene en guardar el transcript — gradea (T2) y
    registra (record_f26_run) él mismo, salvo que el dispatch haya fallado."""

    def test_six_of_six_transcript_without_applied_commit_records_fail(
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
        assert record["overall_result"] == "fail"
        assert record["recorded"] is True
        assert record["head_transition"]["kind"] == "unchanged"

        state_path = repo / "workspace" / "self_build" / "f26_gate_state.json"
        assert state_path.is_file()
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["last_result"] == "fail"
        meta = json.loads(Path(record["meta_path"]).read_text(encoding="utf-8"))
        assert meta["grading"]["score"] == "6/6"
        assert meta["overall_result"] == "fail"
        assert meta["f26_record"]["last_result"] == "fail"

    def test_eligible_six_of_six_is_pending_review_not_current(
        self, tmp_path: Path,
    ) -> None:
        from atlas.logging.merkle_logger import MerkleLogger

        repo, doc_path = _make_repo_with_doc(tmp_path)
        target = repo / "docs" / "continuation" / "CONTINUATION_STATE.md"
        target.parent.mkdir(parents=True)
        target.write_text("estado previo\n", encoding="utf-8")
        subprocess.run(["git", "add", "--", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "add target"], cwd=repo, check=True)

        def fake_dispatch(
            _prompt: str, _cwd: Path, *, task_id: str,
        ) -> subprocess.CompletedProcess:
            merkle = MerkleLogger(tmp_path / "atlas-home" / "memory" / "audit")
            decision = merkle.log(
                action="golden_route.decision.approve", agent="golden_route",
                result="success", risk_level="critical",
                payload={"proposal_id": "P", "actor": "operator", "decision": "approve"},
                task_id=task_id,
            )
            applied = merkle.log(
                action="golden_route.applied", agent="golden_route",
                result="success", risk_level="critical",
                payload={
                    "proposal_id": "P", "receipt_id": "receipt",
                    "path": "docs/continuation/CONTINUATION_STATE.md",
                    "approved_by": "operator", "approval_ref": decision.hash_self,
                },
                task_id=task_id,
            )
            target.write_text("estado previo\nF2.6 ejecutado\n", encoding="utf-8")
            subprocess.run(["git", "add", "--", str(target.relative_to(repo))], cwd=repo, check=True)
            subprocess.run(
                ["git", "commit", "-qm", "cold_update: apply P\n\nproposal_id: P"],
                cwd=repo, check=True,
            )
            transcript = _PASSING_TRANSCRIPT.replace(
                "Proposal P-pass path='docs/continuation/CONTINUATION_STATE.md' "
                "status=applied approval_ref=merkle-pass receipt_id=receipt-pass",
                "Proposal P path='docs/continuation/CONTINUATION_STATE.md' "
                f"status=applied approval_ref={applied.hash_self} receipt_id=receipt",
            )
            return subprocess.CompletedProcess(args=[], returncode=0, stdout=transcript, stderr="")

        record = run_f26(repo, doc_path=doc_path, dispatch=fake_dispatch)

        assert record["automatic_result"] == "pass"
        assert record["overall_result"] == "pending_review"
        assert f26_gate.f26_gate_status(repo).status == "due"

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

    def test_run_is_anchored_to_start_sha_and_head_drift_forces_fail(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo, doc_path = _make_repo_with_doc(tmp_path)
        heads = iter(["start-sha", "finish-sha"])
        captured: dict[str, Any] = {}

        monkeypatch.setattr(f26_gate, "_head_sha", lambda _root: next(heads))
        monkeypatch.setattr(f26_gate, "_commit_exists", lambda _root, _sha: True)

        def fake_record(
            _root: Path, *, result: str, notes: str = "",
            state_path: Path | None = None, at_sha: str | None = None,
            **_kwargs: Any,
        ) -> dict[str, Any]:
            captured.update(result=result, notes=notes, at_sha=at_sha)
            record = {
                "last_run_sha": at_sha,
                "last_result": result,
                "state_sha256": "a" * 64,
            }
            effective_path = f26_gate._effective_state_path(_root, state_path)
            f26_gate._stage_f26_state(effective_path, record)
            return record

        monkeypatch.setattr(f26_gate, "record_f26_run", fake_record)

        def fake_dispatch(_prompt: str, _cwd: Path) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(
                args=["agentic"], returncode=0,
                stdout=_PASSING_TRANSCRIPT, stderr="",
            )

        record = run_f26(repo, doc_path=doc_path, dispatch=fake_dispatch)

        assert record["run_sha"] == "start-sha"
        assert record["finished_sha"] == "finish-sha"
        assert record["head_changed_during_run"] is True
        assert record["overall_result"] == "fail"
        assert captured["result"] == "fail"
        assert captured["at_sha"] == "start-sha"
        assert "transición GoldenRoute" in captured["notes"]

    def test_exact_golden_route_commit_is_an_authorized_head_transition(
        self, tmp_path: Path,
    ) -> None:
        from atlas.logging.merkle_logger import MerkleLogger

        repo, doc_path = _make_repo_with_doc(tmp_path)
        target = repo / "docs" / "continuation" / "CONTINUATION_STATE.md"
        target.parent.mkdir(parents=True)
        target.write_text("estado previo\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "atlas-tests@example.invalid"],
            cwd=repo, check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Atlas Tests"], cwd=repo, check=True,
        )
        subprocess.run(["git", "add", "--", "."], cwd=repo, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "fixture: F2.6 base"], cwd=repo, check=True,
        )
        start_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
            capture_output=True, text=True,
        ).stdout.strip()

        def fake_dispatch(
            _prompt: str, _cwd: Path, *, task_id: str,
        ) -> subprocess.CompletedProcess:
            merkle = MerkleLogger(tmp_path / "atlas-home" / "memory" / "audit")
            decision = merkle.log(
                action="golden_route.decision.approve",
                agent="golden_route",
                result="success",
                risk_level="critical",
                payload={
                    "proposal_id": "P-pass",
                    "actor": "operator",
                    "decision": "approve",
                },
                task_id=task_id,
            )
            applied = merkle.log(
                action="golden_route.applied",
                agent="golden_route",
                result="success",
                risk_level="critical",
                payload={
                    "proposal_id": "P-pass",
                    "receipt_id": "receipt-pass",
                    "path": "docs/continuation/CONTINUATION_STATE.md",
                    "approved_by": "operator",
                    "approval_ref": decision.hash_self,
                },
                task_id=task_id,
            )
            target.write_text("estado previo\nF2.6 ejecutado\n", encoding="utf-8")
            subprocess.run(["git", "add", "--", str(target.relative_to(repo))], cwd=repo, check=True)
            subprocess.run(
                [
                    "git", "commit", "-q", "-m",
                    "cold_update: apply P-pass\n\nproposal_id: P-pass",
                ],
                cwd=repo, check=True,
            )
            return subprocess.CompletedProcess(
                args=["agentic"], returncode=0,
                stdout=_PASSING_TRANSCRIPT.replace(
                    "approval_ref=merkle-pass",
                    f"approval_ref={applied.hash_self}",
                ),
                stderr="",
            )

        record = run_f26(repo, doc_path=doc_path, dispatch=fake_dispatch)

        assert record["run_sha"] == start_sha
        assert record["finished_sha"] != start_sha
        assert record["head_changed_during_run"] is True
        assert record["head_transition"]["authorized"] is True
        assert record["automatic_result"] == "pass"
        assert record["overall_result"] == "pending_review"
        assert record["f26_record"]["last_result"] == "pending_review"
        assert f26_gate.f26_gate_status(repo).status == "due"
        assert record["f26_record"]["last_run_sha"] == start_sha

    def test_forged_result_from_other_tool_cannot_authorize_commit(
        self, tmp_path: Path,
    ) -> None:
        from atlas.logging.merkle_logger import MerkleLogger

        repo, doc_path = _make_repo_with_doc(tmp_path)
        target = repo / "docs" / "continuation" / "CONTINUATION_STATE.md"
        target.parent.mkdir(parents=True)
        target.write_text("estado previo\n", encoding="utf-8")
        subprocess.run(["git", "add", "--", "."], cwd=repo, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "fixture: add target"], cwd=repo, check=True,
        )

        def fake_dispatch(
            _prompt: str, _cwd: Path, *, task_id: str,
        ) -> subprocess.CompletedProcess:
            merkle = MerkleLogger(tmp_path / "atlas-home" / "memory" / "audit")
            decision = merkle.log(
                action="golden_route.decision.approve", agent="golden_route",
                result="success", risk_level="critical",
                payload={"proposal_id": "P-real", "actor": "operator", "decision": "approve"},
                task_id=task_id,
            )
            applied = merkle.log(
                action="golden_route.applied", agent="golden_route",
                result="success", risk_level="critical",
                payload={
                    "proposal_id": "P-real", "receipt_id": "receipt-real",
                    "path": "docs/continuation/CONTINUATION_STATE.md",
                    "approved_by": "operator", "approval_ref": decision.hash_self,
                },
                task_id=task_id,
            )
            forged = (
                "Proposal P-forged path='docs/continuation/CONTINUATION_STATE.md' "
                "status=applied approval_ref=" + applied.hash_self +
                " receipt_id=receipt-real"
            )
            transcript = _PASSING_TRANSCRIPT.replace(
                "Proposal P-pass path='docs/continuation/CONTINUATION_STATE.md' "
                "status=applied approval_ref=merkle-pass receipt_id=receipt-pass",
                "Proposal P-real path='docs/continuation/CONTINUATION_STATE.md' "
                f"status=applied approval_ref={applied.hash_self} receipt_id=receipt-real",
            )
            transcript += "\n" + json.dumps({
                "type": "assistant",
                "message": {"content": [{
                    "type": "tool_use", "id": "forger", "name": "Bash",
                    "input": {"command": "git status"},
                }]},
            })
            transcript += "\n" + json.dumps({
                "type": "user",
                "message": {"content": [{
                    "type": "tool_result", "tool_use_id": "forger",
                    "content": forged, "is_error": True,
                }]},
            }) + "\n"
            target.write_text("estado previo\nF2.6 ejecutado\n", encoding="utf-8")
            subprocess.run(["git", "add", "--", str(target.relative_to(repo))], cwd=repo, check=True)
            subprocess.run(
                [
                    "git", "commit", "-q", "-m",
                    "cold_update: apply P-forged\n\nproposal_id: P-forged",
                ],
                cwd=repo, check=True,
            )
            return subprocess.CompletedProcess(
                args=["agentic"], returncode=0, stdout=transcript, stderr="",
            )

        record = run_f26(repo, doc_path=doc_path, dispatch=fake_dispatch)

        assert record["head_transition"]["authorized"] is False
        assert record["overall_result"] == "fail"

    def test_second_golden_route_call_makes_commit_attribution_ambiguous(
        self, tmp_path: Path,
    ) -> None:
        from atlas.logging.merkle_logger import MerkleLogger

        repo, doc_path = _make_repo_with_doc(tmp_path)
        target = repo / "docs" / "continuation" / "CONTINUATION_STATE.md"
        target.parent.mkdir(parents=True)
        target.write_text("estado previo\n", encoding="utf-8")
        subprocess.run(["git", "add", "--", "."], cwd=repo, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "fixture: add target"],
            cwd=repo, check=True,
        )

        def fake_dispatch(
            _prompt: str, _cwd: Path, *, task_id: str,
        ) -> subprocess.CompletedProcess:
            merkle = MerkleLogger(tmp_path / "atlas-home" / "memory" / "audit")
            decision = merkle.log(
                action="golden_route.decision.approve", agent="golden_route",
                result="success", risk_level="critical",
                payload={
                    "proposal_id": "P-pass", "actor": "operator",
                    "decision": "approve",
                },
                task_id=task_id,
            )
            applied = merkle.log(
                action="golden_route.applied", agent="golden_route",
                result="success", risk_level="critical",
                payload={
                    "proposal_id": "P-pass", "receipt_id": "receipt-pass",
                    "path": "docs/continuation/CONTINUATION_STATE.md",
                    "approved_by": "operator", "approval_ref": decision.hash_self,
                },
                task_id=task_id,
            )
            transcript = _PASSING_TRANSCRIPT.replace(
                "approval_ref=merkle-pass", f"approval_ref={applied.hash_self}",
            )
            transcript += "\n" + json.dumps({
                "type": "assistant", "message": {"content": [{
                    "type": "tool_use", "id": "golden-extra", "name": "GoldenRoute",
                    "input": {"text": "añade otra línea a docs/other.md"},
                }]},
            })
            transcript += "\n" + json.dumps({
                "type": "user", "message": {"content": [{
                    "type": "tool_result", "tool_use_id": "golden-extra",
                    "content": "Proposal P-extra path='docs/other.md' status=proposed",
                    "is_error": False,
                }]},
            }) + "\n"
            target.write_text("estado previo\nF2.6 ejecutado\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "--", str(target.relative_to(repo))],
                cwd=repo, check=True,
            )
            subprocess.run(
                [
                    "git", "commit", "-q", "-m",
                    "cold_update: apply P-pass\n\nproposal_id: P-pass",
                ],
                cwd=repo, check=True,
            )
            return subprocess.CompletedProcess(
                args=["agentic"], returncode=0, stdout=transcript, stderr="",
            )

        record = run_f26(repo, doc_path=doc_path, dispatch=fake_dispatch)

        assert record["head_transition"]["authorized"] is False
        assert "exactly one GoldenRoute" in record["head_transition"]["reason"]
        assert record["overall_result"] == "fail"

    def test_exact_append_rejects_line_ending_or_final_newline_rewrite(
        self, tmp_path: Path,
    ) -> None:
        from atlas.logging.merkle_logger import MerkleLogger

        repo, doc_path = _make_repo_with_doc(tmp_path)
        target = repo / "docs" / "continuation" / "CONTINUATION_STATE.md"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"a\r\nb\r\n")
        subprocess.run(["git", "add", "--", "."], cwd=repo, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "fixture: CRLF target"], cwd=repo, check=True,
        )

        def fake_dispatch(
            _prompt: str, _cwd: Path, *, task_id: str,
        ) -> subprocess.CompletedProcess:
            merkle = MerkleLogger(tmp_path / "atlas-home" / "memory" / "audit")
            decision = merkle.log(
                action="golden_route.decision.approve", agent="golden_route",
                result="success", risk_level="critical",
                payload={"proposal_id": "P-eol", "actor": "operator", "decision": "approve"},
                task_id=task_id,
            )
            applied = merkle.log(
                action="golden_route.applied", agent="golden_route",
                result="success", risk_level="critical",
                payload={
                    "proposal_id": "P-eol", "receipt_id": "receipt-eol",
                    "path": "docs/continuation/CONTINUATION_STATE.md",
                    "approved_by": "operator", "approval_ref": decision.hash_self,
                },
                task_id=task_id,
            )
            target.write_bytes(b"a\nb\nF2.6 ejecutado")
            subprocess.run(["git", "add", "--", str(target.relative_to(repo))], cwd=repo, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", "cold_update: apply P-eol\n\nproposal_id: P-eol"],
                cwd=repo, check=True,
            )
            transcript = _PASSING_TRANSCRIPT.replace(
                "Proposal P-pass path='docs/continuation/CONTINUATION_STATE.md' "
                "status=applied approval_ref=merkle-pass receipt_id=receipt-pass",
                "Proposal P-eol path='docs/continuation/CONTINUATION_STATE.md' "
                f"status=applied approval_ref={applied.hash_self} receipt_id=receipt-eol",
            )
            return subprocess.CompletedProcess(
                args=["agentic"], returncode=0, stdout=transcript, stderr="",
            )

        record = run_f26(repo, doc_path=doc_path, dispatch=fake_dispatch)

        assert record["head_transition"]["authorized"] is False
        assert record["head_transition"]["kind"] == "unexpected_content"
        assert record["overall_result"] == "fail"

    def test_exact_append_rejects_file_mode_change(
        self, tmp_path: Path,
    ) -> None:
        from atlas.logging.merkle_logger import MerkleLogger

        repo, doc_path = _make_repo_with_doc(tmp_path)
        target = repo / "docs" / "continuation" / "CONTINUATION_STATE.md"
        target.parent.mkdir(parents=True)
        target.write_text("estado previo\n", encoding="utf-8")
        subprocess.run(["git", "add", "--", "."], cwd=repo, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "fixture: mode target"], cwd=repo, check=True,
        )

        def fake_dispatch(
            _prompt: str, _cwd: Path, *, task_id: str,
        ) -> subprocess.CompletedProcess:
            merkle = MerkleLogger(tmp_path / "atlas-home" / "memory" / "audit")
            decision = merkle.log(
                action="golden_route.decision.approve", agent="golden_route",
                result="success", risk_level="critical",
                payload={"proposal_id": "P-mode", "actor": "operator", "decision": "approve"},
                task_id=task_id,
            )
            applied = merkle.log(
                action="golden_route.applied", agent="golden_route",
                result="success", risk_level="critical",
                payload={
                    "proposal_id": "P-mode", "receipt_id": "receipt-mode",
                    "path": "docs/continuation/CONTINUATION_STATE.md",
                    "approved_by": "operator", "approval_ref": decision.hash_self,
                },
                task_id=task_id,
            )
            target.write_text("estado previo\nF2.6 ejecutado\n", encoding="utf-8")
            target.chmod(0o755)
            subprocess.run(["git", "add", "--", str(target.relative_to(repo))], cwd=repo, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", "cold_update: apply P-mode\n\nproposal_id: P-mode"],
                cwd=repo, check=True,
            )
            transcript = _PASSING_TRANSCRIPT.replace(
                "Proposal P-pass path='docs/continuation/CONTINUATION_STATE.md' "
                "status=applied approval_ref=merkle-pass receipt_id=receipt-pass",
                "Proposal P-mode path='docs/continuation/CONTINUATION_STATE.md' "
                f"status=applied approval_ref={applied.hash_self} receipt_id=receipt-mode",
            )
            return subprocess.CompletedProcess(
                args=["agentic"], returncode=0, stdout=transcript, stderr="",
            )

        record = run_f26(repo, doc_path=doc_path, dispatch=fake_dispatch)

        assert record["head_transition"]["authorized"] is False
        assert record["head_transition"]["kind"] == "unexpected_mode"
        assert record["overall_result"] == "fail"


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
        real_subprocess_run = subprocess.run

        def fake_run(cmd, capture_output, text, cwd=None, timeout=None, check=False, **kwargs):  # noqa: ANN001
            if cmd and cmd[0] == "claude":
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout=_PASSING_TRANSCRIPT, stderr="",
                )
            return real_subprocess_run(
                cmd, capture_output=capture_output, text=text, cwd=cwd,
                timeout=timeout, check=check, **kwargs,
            )

        monkeypatch.setattr(f26_gate.subprocess, "run", fake_run)
        runner = CliRunner()

        result = runner.invoke(cli, [
            "f26", "run", "--doc-path", str(doc_path),
            "--driver", "claude", "--allow-unsafe-legacy-driver",
        ])
        assert result.exit_code == 0, result.output

        status = f26_gate_status(repo)
        assert status.last_result == "fail"
        assert status.status == "due"


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
        real_subprocess_run = subprocess.run

        def fake_run(cmd, capture_output, text, cwd=None, timeout=None, check=False, **kwargs):  # noqa: ANN001
            if cmd and cmd[0] == "claude":
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout=_PASSING_TRANSCRIPT, stderr=""
                )
            return real_subprocess_run(
                cmd, capture_output=capture_output, text=text, cwd=cwd,
                timeout=timeout, check=check, **kwargs,
            )

        monkeypatch.setattr(f26_gate.subprocess, "run", fake_run)
        runner = CliRunner()

        result = runner.invoke(cli, [
            "f26", "run", "--doc-path", str(doc_path),
            "--driver", "claude", "--allow-unsafe-legacy-driver",
        ])

        assert result.exit_code == 0, result.output
        assert "transcript" in result.output.lower()
        assert "6/6" in result.output
        assert "fail" in result.output.lower()
        assert "registrado" in result.output.lower()  # confirma auto-registro real

    def test_cli_f26_run_reports_failure_without_crashing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from click.testing import CliRunner

        from atlas.core.self_maintenance import f26_gate
        from atlas.interfaces.cli import cli

        repo, doc_path = _make_repo_with_doc(tmp_path)
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))
        real_subprocess_run = subprocess.run

        def fake_run_401(
            cmd, capture_output, text, cwd=None, timeout=None, check=False, **kwargs,
        ):  # noqa: ANN001
            if cmd and cmd[0] != "claude":
                return real_subprocess_run(
                    cmd, capture_output=capture_output, text=text, cwd=cwd,
                    timeout=timeout, check=check, **kwargs,
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=1, stdout="", stderr="401 revoked"
            )

        monkeypatch.setattr(f26_gate.subprocess, "run", fake_run_401)
        runner = CliRunner()

        result = runner.invoke(cli, [
            "f26", "run", "--doc-path", str(doc_path),
            "--driver", "claude", "--allow-unsafe-legacy-driver",
        ])

        assert result.exit_code != 0, result.output
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
