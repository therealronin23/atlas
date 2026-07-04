"""Paso 3 del roadmap "juicio real para autoauditoría" (tras PreflightGate y
BatchPremortemGate). Incidente real que motiva esto: 9 YAML regenerados sin
commit hicieron fallar 38 propuestas legítimas de bump de dependencias durante
una semana — el worktree se construyó desde HEAD (que tenía una versión
vieja/vacía de un archivo) mientras la carpeta de trabajo real tenía la
versión buena SIN COMMITEAR, y nadie razonó el PORQUÉ del fallo.

RootCauseClassifier: barato antes que caro. Primero un chequeo determinista
(gratis, sin LLM) contra el estado real de git — exactamente el que habría
detectado el incidente. Solo si no hay evidencia clara cae a un LLM barato
que razona sobre el texto del fallo (mismo patrón dual-LLM que analyst.py /
batch_premortem.py).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from atlas.core.git_env import clean_git_env
from atlas.core.inference_hub import InferenceLevel, InferenceResponse
from atlas.core.self_maintenance.root_cause_classifier import (
    RootCauseClassifier,
    RootCauseVerdict,
)


class FakeHub:
    """Hub falso: mismo patrón que test_batch_premortem.py."""

    def __init__(self, *, verdict_text: str | None) -> None:
        self._verdict_text = verdict_text
        self.calls: list[str] = []

    def infer(self, request: Any) -> InferenceResponse:
        self.calls.append(request.task_id or "")
        text = self._verdict_text if self._verdict_text is not None else ""
        return InferenceResponse(
            text=text, provider="fake", model="fake",
            level=InferenceLevel.L1, latency_ms=1, success=self._verdict_text is not None,
        )


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True,
        env=clean_git_env(),
    )


def _init_repo_with_committed_file(tmp_path: Path, rel_path: str, content: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "test")
    file_path = repo / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content)
    _run_git(repo, "add", rel_path)
    _run_git(repo, "commit", "-q", "-m", "initial commit")
    return repo


class TestDeterministicAmbiental:
    def test_dirty_file_mentioned_in_pytest_output_classifies_ambiental(self, tmp_path: Path) -> None:
        rel = "docs/design/seeded/subagents_seeded.yaml"
        repo = _init_repo_with_committed_file(tmp_path, rel, "version: 1\n")
        # modifica SIN commitear -> diverge de HEAD, igual que el incidente real
        (repo / rel).write_text("version: 2\n")

        hub = FakeHub(verdict_text=None)  # si se llamara, fallaría el patrón fail-open; no debe llamarse
        classifier = RootCauseClassifier(hub=hub, repo_root=repo)
        pytest_summary = f"FAILED test_x - schema mismatch in {rel}"
        verdict = classifier.classify(pytest_summary=pytest_summary, mypy_summary="")

        assert verdict.classification == "ambiental"
        assert verdict.used_llm is False
        assert rel in verdict.evidence_paths
        assert hub.calls == []  # chequeo determinista es gratis: nunca llama al LLM


class TestFallsBackToLlm:
    def test_clean_file_mentioned_falls_back_to_llm(self, tmp_path: Path) -> None:
        rel = "src/foo.py"
        repo = _init_repo_with_committed_file(tmp_path, rel, "x = 1\n")
        # sin modificar: limpio, comiteado

        hub = FakeHub(verdict_text=json.dumps(
            {"classification": "causado_por_diff", "reason": "el cambio rompe la firma"}
        ))
        classifier = RootCauseClassifier(hub=hub, repo_root=repo)
        pytest_summary = f"FAILED test_y - AttributeError in {rel}"
        verdict = classifier.classify(pytest_summary=pytest_summary, mypy_summary="")

        assert verdict.used_llm is True
        assert verdict.classification == "causado_por_diff"
        assert verdict.reason == "el cambio rompe la firma"
        assert "root_cause_classifier" in hub.calls

    def test_no_recognizable_path_falls_back_to_llm(self, tmp_path: Path) -> None:
        repo = _init_repo_with_committed_file(tmp_path, "src/foo.py", "x = 1\n")
        hub = FakeHub(verdict_text=json.dumps(
            {"classification": "unknown", "reason": "sin evidencia suficiente"}
        ))
        classifier = RootCauseClassifier(hub=hub, repo_root=repo)
        verdict = classifier.classify(
            pytest_summary="FAILED test_z - assertion error, no path here",
            mypy_summary="",
        )

        assert verdict.used_llm is True
        assert verdict.classification == "unknown"
        assert hub.calls == ["root_cause_classifier"]


class TestLlmFailOpen:
    def test_unparseable_llm_response_is_unknown_and_does_not_crash(self, tmp_path: Path) -> None:
        repo = _init_repo_with_committed_file(tmp_path, "src/foo.py", "x = 1\n")
        hub = FakeHub(verdict_text="lo siento, no puedo ayudar con eso")
        classifier = RootCauseClassifier(hub=hub, repo_root=repo)
        verdict = classifier.classify(
            pytest_summary="FAILED test_z - some error, no path here",
            mypy_summary="",
        )

        assert verdict.classification == "unknown"
        assert verdict.used_llm is True


class TestGitDiffFails:
    def test_repo_not_a_git_repo_falls_back_to_llm_without_crashing(self, tmp_path: Path) -> None:
        not_a_repo = tmp_path / "not_a_repo"
        not_a_repo.mkdir()
        rel = "src/foo.py"
        hub = FakeHub(verdict_text=json.dumps(
            {"classification": "causado_por_diff", "reason": "confirmado por LLM"}
        ))
        classifier = RootCauseClassifier(hub=hub, repo_root=not_a_repo)
        verdict = classifier.classify(
            pytest_summary=f"FAILED test_w - error in {rel}",
            mypy_summary="",
        )

        assert verdict.used_llm is True
        assert verdict.classification == "causado_por_diff"


class TestToDictRoundtrip:
    def test_to_dict_roundtrip(self) -> None:
        verdict = RootCauseVerdict(
            classification="ambiental",
            reason="motivo",
            evidence_paths=["a.py", "b.yaml"],
            used_llm=False,
        )
        d = verdict.to_dict()
        assert d == {
            "classification": "ambiental",
            "reason": "motivo",
            "evidence_paths": ["a.py", "b.yaml"],
            "used_llm": False,
        }
